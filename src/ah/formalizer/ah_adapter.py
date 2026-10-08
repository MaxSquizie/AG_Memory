"""Durable canonical AH writer. WAL is the commit boundary, not a post-write log.

Prepare on a COW core, validate every operation, append one checksummed fsync unit,
then publish. Recovery restores that exact unit, including marker, decision and
proof records. All batch / goal / retraction decisions share the journal lock.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from copy import deepcopy
from typing import Any, Callable, Sequence
from ah.core.journal import JournalChannel, JournalIntegrityError
from ah.core.operations import AHCore
from ah.core.persistence import JsonPersistence
from ah.config import PersistenceSettings
from .canonical_ledger import CanonicalLedger, digest, simultaneous
from .store_interface import AssertionStatus, CommitDecision, CommitResult, JournalRecord, MaterializationMarker, RecoveryReport, Store, StoreOp, TerminalOutcome


class AHStoreAdapter(Store):
    def __init__(self, store: Any, journal: JournalChannel, core: Any = None):
        self._store, self._journal = store, journal
        self._core = core or AHCore(store)
        self._codec = JsonPersistence(journal.path.with_suffix('.snapshot'), PersistenceSettings())
        self._op_handlers: dict[str, Callable] = {}
        from .graph_ops import GRAPH_HANDLERS
        self._op_handlers.update(GRAPH_HANDLERS)
        from .rx_observability import ExperienceIndex
        self._rx_index = ExperienceIndex()
        self.last_rx_diagnostics = ()
        self._core._formalizer_adapter = self
        self.recover_from_head(drain_pending=False)

    @property
    def ledger(self):
        return CanonicalLedger(self._store._state.formalizer_state)

    def prove_node(self,uid,*,point=None,window=None):
        from .goal_queries import prove_node
        with self._journal.atomic(), self._store._lock:
            self._refresh()
            diagnostics=prove_node(self,uid,point=point,window=window) or ()
            return {**self.ledger.query_proposition(uid,point=point,window=window),'diagnostics':list(diagnostics)}

    def query_template(self,template_uid,known_roles,*,point=None,window=None):
        from .goal_queries import prove_instances
        roles={getattr(k,'value',k):getattr(v,'uid',v) for k,v in known_roles.items()}
        with self._journal.atomic(), self._store._lock:
            self._refresh()
            diagnostics=prove_instances(self,template_uid,roles,point=point,window=window) or ()
            result={'answer':'UNKNOWN','conflict_ref':[],'managed':False,'diagnostics':list(diagnostics)}
            for n in self._store.find_hypernodes_by_template(template_uid):
                spec=self.ledger.data['nodes'].get(n.uid)
                if spec is None: continue
                result['managed']=True
                actual=spec.get('proposition',{}).get('actants',{})
                if any(actual.get(k)!=v for k,v in roles.items()): continue
                answer=self.prove_node(n.uid,point=point,window=window)
                result['diagnostics']=sorted(set(result['diagnostics'])|set(answer.get('diagnostics',())))
                result['conflict_ref']=sorted(set(result['conflict_ref'])|set(answer['conflict_ref']))
                if answer['answer']=='YES' or answer['answer']=='NO' and actual==roles:
                    result.update(answer=answer['answer'],node_ref=n.uid,evidence_ref=answer.get('evidence_ref',n.uid))
                    return result
            return result

    def register_op_handler(self, op_type, handler):
        self._op_handlers[op_type] = handler

    def read_cache(self, stage, resource_snapshot):
        if stage not in {'T1','T2','T3'}: raise ValueError('RX_STAGE_INVALID')
        return self.read_cache_snapshot(resource_snapshot)[stage]

    def read_cache_snapshot(self, resource_snapshot, *, lexical_keys=None, limit=4096):
        """Freeze all stage reads against one canonical AH snapshot."""
        with self._journal.atomic(),self._store._lock:
            if type(limit) is not int or not 1 <= limit <= 100000: raise ValueError('RX_LIMIT_INVALID')
            self._refresh(); ledger=self.ledger
            self._rx_index.build(ledger.data['rx_cache'],self._store._state.formalizer_state.get('wal_seq',0))
            rows, diagnostics = self._rx_index.read(ledger,resource_snapshot,lexical_keys,limit)
            self.last_rx_diagnostics = tuple(diagnostics)
            return rows

    def experience_metrics(self):
        with self._journal.atomic(), self._store._lock:
            return self._rx_index.report()

    def append_journal(self, channel, record):
        return self._journal.append(channel, dict(record.payload), run_id=record.run_id)

    def read_global_head(self):
        return self._journal.read_global_head()

    def scan_unprocessed(self, after_seq=0):
        return tuple(JournalRecord(r['channel'],r.get('run_id',''),dict(r['payload']),r['seq']) for r in self._journal.scan_unprocessed(after_seq))

    def _refresh(self):
        current = self._store._state.formalizer_state.get('wal_seq',0)
        if current>self._journal.read_global_head():
            raise JournalIntegrityError('INTEGRITY_ERROR: snapshot is ahead of its journal')
        for r in self._journal.scan_unprocessed(current):
            p=r['payload']
            if p.get('kind') != 'canonical_unit':
                continue
            if digest(p['snapshot']) != p['snapshot_hash']:
                raise JournalIntegrityError('INTEGRITY_ERROR: canonical unit checksum mismatch')
            restored = self._codec.import_payload(p['snapshot'], uid_generator=self._core.uid).core
            CanonicalLedger(restored.store._state.formalizer_state).validate_audit()
            restored.store._state.formalizer_state['wal_seq']=r['seq']
            self._store.replace_from(restored.store)
            self._core.supports.replace_from(restored.supports)
        self.ledger.validate_audit()

    def _draft(self):
        return AHCore(self._store.clone(),self._core.uid,self._core.supports.clone(),self._core.function_registry)

    def _write_unit(self, draft, *, tx_ref, decision=None, terminal=None, extra=None):
        # The live graph is untouched until this single durable unit exists.
        CanonicalLedger(draft.store._state.formalizer_state).validate_audit()
        payload=self._codec.export(draft)
        seq=self._journal.append('canonical',{'kind':'canonical_unit','tx_ref':tx_ref,'snapshot':payload,'snapshot_hash':digest(payload),'decision':decision,'terminal':terminal,'extra':extra})
        draft.store._state.formalizer_state['wal_seq']=seq
        self._store.replace_from(draft.store)
        self._core.supports.replace_from(draft.supports)
        return seq

    def _terminal_records(self):
        out={}
        for r in self._journal.scan_unprocessed(0):
            p=r['payload']
            t=p.get('terminal') if p.get('kind')=='canonical_unit' else p if p.get('kind')=='terminal' else None
            if t:
                aid=t['assertion_id']
                if aid in out and out[aid]['outcome']!=t['outcome']:
                    raise JournalIntegrityError('INTEGRITY_ERROR: conflicting terminal outcomes')
                out[aid]=t
        return out

    def pending_batches(self):
        terminals=self._terminal_records()
        committed=set(self.ledger.data['decisions'])
        found={}
        for r in self._journal.scan_unprocessed(0):
            p=r['payload']
            if p.get('kind')=='BATCH' and 'batch:'+p['batch_hash'] not in terminals and p['batch_hash'] not in committed:
                found.setdefault(p['batch_hash'],r)
        return sorted(found.values(),key=lambda r:r['seq'])

    def _excluded(self, ops, ledger, *, precheck_only=False):
        from .canonical_ledger import incompatible
        fragments=[op.payload for op in ops if op.op_type=='DECLARE_FRAGMENT']
        conflicts=[]; paths=ledger.paths()
        for f in fragments:
            for node,spec in ledger.data['nodes'].items():
                committed={**spec,'node_ref':node}
                if spec.get('function_id')=='NOT':
                    committed['proposition']=ledger.data['nodes'].get(spec['operands'][0],{}).get('proposition')
                rule=incompatible(f,committed,f.get('incompatibility_rules',()))
                if rule is None: continue
                for sid,s in ledger.data['supports'].items():
                    if s['conclusion_ref']!=node or sid not in paths: continue
                    aa=[a for a in ledger.data['assertions'].values() if a['support_record_id']==sid and ledger.evidence_live({'record_id':a['assertion_id']})]
                    if not aa and not f.get('region'):
                        conflicts.append((f,None,{'kind':'COMMITTED','record_id':sid},node,rule))
                    for assertion in aa:
                        if simultaneous(f.get('region'),assertion['region']):
                            conflicts.append((f,None,{'kind':'COMMITTED','record_id':assertion['assertion_id']},node,rule))
        ordered=sorted(fragments,key=lambda f:(f['fragment_id'],f['node_ref']))
        for i,a in enumerate(ordered):
            for b in ordered[i+1:]:
                rule=incompatible(a,b,a.get('incompatibility_rules',()))
                same_witness=a.get('witness_ref') and a.get('witness_ref')==b.get('witness_ref')
                if rule and (same_witness or simultaneous(a.get('region'),b.get('region'))):
                    conflicts.append((a,b,None,None,rule))
        if precheck_only:
            return [{'fragment_ref':a['fragment_id'],
                     'observed_conflict_with':({'fragment_ref':b['fragment_id']} if b else committed),
                     'rule_id':rule} for a,b,committed,node,rule in conflicts]
        excluded=set(); evidence=[]
        for fa,fb,committed,node,rule in conflicts:
            candidates=[]
            for value in (fa,fb):
                if value is None: continue
                excluded.add(value['fragment_id']); value=deepcopy(value)
                value['candidate_record_id']='candidate:'+digest([value['source_tag'],value['fragment_id'],value['content_key'],value['polarity']])
                candidates.append(value)
            refs=[{'kind':'CANDIDATE','record_id':c['candidate_record_id']} for c in candidates]
            if committed: refs.append(committed)
            rid='report:'+digest(sorted(e['record_id'] for e in refs))
            evidence.append({'kind':'CANDIDATE_CANDIDATE' if fb else 'CANDIDATE_COMMITTED','candidates':candidates,'report_id':rid,'evidence_refs':refs,'node_refs':[node] if node else [],'rule_id':rule})
        return excluded,evidence

    def gate_precheck(self, batch_hash, plan_ops, *, run_id):
        """Durable diagnostics only: no candidates, reports or plan filtering."""
        with self._journal.atomic(), self._store._lock:
            self._refresh()
            previous=[r['payload']['precheck_id'] for r in self._journal.scan_unprocessed(0)
                      if r['payload'].get('kind')=='GATE_PRECHECK'
                      and r['payload'].get('batch_hash')==batch_hash]
            if previous: return tuple(previous)
            refs=[]
            for item in self._excluded(plan_ops,self.ledger,precheck_only=True):
                ref='precheck:'+digest([batch_hash,item])
                if ref in refs: continue
                self._journal.append('resolution_log',{'kind':'GATE_PRECHECK',
                    'precheck_id':ref,'batch_hash':batch_hash,**item},run_id=run_id)
                refs.append(ref)
            return tuple(refs)

    def _reports(self, ledger, evidence):
        for e in evidence:
            for c in e['candidates']:
                oid=digest(c['source_tag'])
                observation=ledger.data['observations'].setdefault(oid,{'source_tag':c['source_tag'],'status':'LIVE'})
                ledger.data['candidates'].setdefault(c['candidate_record_id'],{**deepcopy(c),'status':observation['status']})
            ledger.data['reports'].setdefault(e['report_id'],deepcopy(e))

    def _apply(self, draft, ops):
        ledger=CanonicalLedger(draft.store._state.formalizer_state)
        applied=[]; events=[]
        for op in ops:
            p=dict(op.payload)
            if op.op_type=='DECLARE_FRAGMENT':
                ledger.data['observations'].setdefault(digest(p['source_tag']),{'source_tag':p['source_tag'],'status':'LIVE'})
                continue
            if op.op_type=='ADD_ROOT_SUPPORT' or op.op_type=='ADD_DERIVED_SUPPORT':
                if p['conclusion_ref'] not in ledger.data['nodes']: raise ValueError('SUPPORT_CONCLUSION_MISSING')
                if p['kind']=='ROOT' and (op.op_type!='ADD_ROOT_SUPPORT' or not p.get('source_tag')): raise ValueError('INVALID_FACT_GROUND')
                if p['kind']=='ROOT' and ledger.data['observations'].get(digest(p['source_tag']),{}).get('status','LIVE')!='LIVE':
                    raise ValueError('STALE_PLAN: observation is no longer live')
                if p['kind']=='DERIVED':
                    if op.op_type!='ADD_DERIVED_SUPPORT' or any(r not in ledger.paths() for r in p.get('premise_support_refs',())): raise ValueError('GOAL_PREMISES_STALE')
                    if p.get('rule_id')=='AND_ELIMINATION':
                        roots=[ledger.data['nodes'][ledger.data['supports'][r]['conclusion_ref']] for r in p['premise_support_refs']]
                        formula=p.get('formula_ref',p['conclusion_ref'])
                        if len(roots)!=1 or roots[0].get('function_id')!='AND' or formula not in roots[0]['operands']: raise ValueError('DERIVATION_FORM_MISMATCH')
                        if ledger.data['nodes'][p['conclusion_ref']].get('content_key')!=ledger.data['nodes'][formula].get('content_key'): raise ValueError('DERIVATION_FORM_MISMATCH')
                    elif p.get('rule_id') not in {'OR_ELIMINATION','FORALL_INST'} or not p.get('goal_run_id'): raise ValueError('DERIVATION_RULE_INVALID')
                new=p['record_id'] not in ledger.data['supports']
                ledger.add_support(p)
                if new: events.append({'node_id':p['conclusion_ref'],'type':'SUPPORT_ADDED','support_id':p['record_id']})
            elif op.op_type=='ADD_TIME_ASSERTION': ledger.add_assertion(p)
            elif op.op_type=='SUPERSEDE_VERSION':
                continue  # Applied once, before final admission, on this draft.
            elif op.op_type=='LINK_OPEN_TEMPLATE':
                source,target=p['source_t_ref'],p['canonical_t_ref']
                if not p.get('evidence_refs') or not p.get('trigger_ref') or not p.get('resource_snapshot'):
                    raise ValueError('MIGRATION_LINK_INVALID')
                old_nodes={uid for uid,node in ledger.data['nodes'].items()
                           if node.get('template_ref')==source and node.get('semantic_status')=='UNLINKED'}
                old_supports=[s for s in ledger.data['supports'].values()
                              if s['conclusion_ref'] in old_nodes and s.get('source_tag')==p['source_tag']]
                new_nodes={uid for uid,node in ledger.data['nodes'].items()
                           if node.get('template_ref')==target and node.get('semantic_status')=='KNOWN'}
                new_supports=[s for s in ledger.data['supports'].values()
                              if s['conclusion_ref'] in new_nodes and s.get('source_tag')==p['replacement_tag']]
                if not old_supports or not new_supports or not draft.store.has_uid(target) or draft.store.kind_of(target).value!='T':
                    raise ValueError('MIGRATION_LINK_INVALID')
                record={k:v for k,v in p.items() if k!='op_id'}
                old=ledger.data['open_template_links'].get(p['link_id'])
                if old is not None and old!=record: raise ValueError('INTEGRITY_ERROR: migration link changed')
                ledger.data['open_template_links'].setdefault(p['link_id'],record)
            elif op.op_type=='WRITE_COMMITTED_RX':
                if p['support_record_id'] not in ledger.paths() or not set(p['stages'])<={'T1','T2','T3'}:
                    raise ValueError('RX_COMMIT_GROUND_INVALID')
                old=ledger.data['rx_cache'].get(p['record_id'])
                if old and old!={**p,'status':'LIVE'}: raise ValueError('INTEGRITY_ERROR: RX record changed')
                ledger.data['rx_cache'].setdefault(p['record_id'],{**p,'status':'LIVE'})
            elif op.op_type=='SET_IDENTITY_BINDING':
                old=ledger.data['bindings'].get(p['binding_id'])
                if old and old!={**p,'status':'LIVE'}: raise ValueError('IDENTITY_CONFLICT')
                ledger.data['bindings'].setdefault(p['binding_id'],{**p,'status':'LIVE'})
            elif op.op_type=='MATERIALIZE_USAGE_LINK':
                if any(not draft.store.has_uid(p[k]) or draft.store.kind_of(p[k]).value not in {'N','G'} for k in ('node_ref','parent_ref')):
                    raise ValueError('USAGE_LINK_REF_INVALID')
                p.setdefault('status','LIVE')
                if p['kind']=='OPERATOR':
                    parent=ledger.data['nodes'].get(p['parent_ref'],{})
                    position=p.get('position')
                    if not isinstance(position,int) or position<0 or position>=len(parent.get('operands',())) or parent['operands'][position]!=p['node_ref']: raise ValueError('USAGE_LINK_SLOT_INVALID')
                    p['source']='STRUCTURE'
                elif p['kind']!='ATTITUDE' or not p.get('source_tag') or p.get('attitude') not in {'QUOTED','EMBEDDED','HYPOTHETICAL','UNKNOWN'} or ledger.data['nodes'][p['parent_ref']].get('actants',{}).get(p.get('position'))!=p['node_ref']: raise ValueError('USAGE_LINK_INVALID')
                old=ledger.data['usage_links'].get(p['link_id'])
                if old and old!=p: raise ValueError('INTEGRITY_ERROR: usage identity changed')
                ledger.data['usage_links'].setdefault(p['link_id'],p)
            else:
                if op.op_type not in {'ENSURE_ENTITY','ENSURE_TEMPLATE','ENSURE_NODE','ENSURE_FUNCTION','ENSURE_GROUP'}: raise ValueError('LEGACY_MUTATION_NOT_ALLOWED:'+op.op_type)
                handler=self._op_handlers.get(op.op_type)
                if handler is None: raise ValueError('UNKNOWN_MUTATION_OPERATION:'+op.op_type)
                uid=handler(draft,p)
                if uid:
                    applied.append(uid)
                    if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'}:
                        old=ledger.data['nodes'].get(uid)
                        spec={k:v for k,v in p.items() if k not in {'weight'}}
                        if old and old.get('content_key')!=spec.get('content_key'): raise ValueError('INTEGRITY_ERROR: changed node content')
                        ledger.data['nodes'].setdefault(uid,spec)
        return tuple(applied),events

    def commit_transaction(self, plan_ops: Sequence[StoreOp], marker: MaterializationMarker, decision: CommitDecision):
        with self._journal.atomic(), self._store._lock:
            self._refresh()
            terminals=self._terminal_records(); aid='batch:'+decision.batch_hash
            if digest([asdict(o) for o in plan_ops])!=decision.ops_digest: raise JournalIntegrityError('INTEGRITY_ERROR: plan digest mismatch')
            if aid in terminals:
                return CommitResult(self.read_global_head(),(),TerminalOutcome(terminals[aid]['outcome']),True)
            marker_key=digest(asdict(marker))
            previous=self.ledger.data['markers'].get(marker_key)
            if previous:
                if previous!=decision.batch_hash:
                    self.append_terminal(aid,TerminalOutcome.REJECTED_COMMIT_ELIGIBILITY,'pair already committed')
                    return CommitResult(self.read_global_head(),(),TerminalOutcome.REJECTED_COMMIT_ELIGIBILITY)
                self.append_terminal(aid,TerminalOutcome.APPLIED)
                return CommitResult(self.read_global_head(),(),TerminalOutcome.APPLIED,True)
            pending=self.pending_batches()
            match=next((r for r in pending if r['payload']['batch_hash']==decision.batch_hash),None)
            if match is None: raise ValueError('BATCH_NOT_JOURNALED')
            owners=[r['payload'] for r in self._journal.scan_unprocessed(0)
                    if r['payload'].get('kind')=='run_bind'
                    and r['payload'].get('observation_id')==marker.observation_id
                    and r['payload'].get('version')==marker.interpretation_version]
            if not owners or any(p['owner']!=decision.run_id for p in owners):
                self.append_terminal(aid,TerminalOutcome.REJECTED_COMMIT_ELIGIBILITY,'RUN_BINDING_FOREIGN_OWNER')
                return CommitResult(self.read_global_head(),(),TerminalOutcome.REJECTED_COMMIT_ELIGIBILITY)
            if digest([asdict(o) for o in plan_ops])!=decision.ops_digest or digest(match['payload']['ops'])!=digest([asdict(o) for o in plan_ops]):
                raise JournalIntegrityError('INTEGRITY_ERROR: journaled plan changed')
            if pending[0]['seq']!=match['seq']:
                return CommitResult(match['seq'],(),TerminalOutcome.PENDING_ADMISSION_ORDER)
            draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
            stale=any(o.op_type=='SET_IDENTITY_BINDING' and any(p not in ledger.paths() for p in o.payload.get('premise_support_refs',())) for o in plan_ops)
            stale |= any(o.op_type=='ENSURE_ENTITY' and o.payload.get('reference_existing') and not self.has_uid(o.payload['uid']) for o in plan_ops)
            stale |= any(o.op_type=='ADD_ROOT_SUPPORT' and ledger.data['observations'].get(digest(o.payload['source_tag']),{}).get('status','LIVE')!='LIVE' for o in plan_ops)
            if decision.outcome==TerminalOutcome.STALE_SUPERSEDED or stale:
                self.append_terminal(aid,TerminalOutcome.STALE_SUPERSEDED,'STALE_PLAN')
                return CommitResult(self.read_global_head(),(),TerminalOutcome.STALE_SUPERSEDED)
            paths=ledger.paths()
            for op in plan_ops:
                if op.op_type!='LINK_OPEN_TEMPLATE': continue
                p=op.payload
                if not p.get('evidence_refs') or any(sid not in paths or ledger.data['supports'][sid].get('source_tag')!=p.get('source_tag') for sid in p['evidence_refs']):
                    self.append_terminal(aid,TerminalOutcome.STALE_SUPERSEDED,'MIGRATION_EVIDENCE_STALE')
                    return CommitResult(self.read_global_head(),(),TerminalOutcome.STALE_SUPERSEDED)
            retire=[o.payload for o in plan_ops if o.op_type=='SUPERSEDE_VERSION']
            retirement_events=[]
            for p in retire:
                if (not p.get('trigger_ref') or p.get('replacement_tag')!=[marker.observation_id,marker.interpretation_version]
                    or p['source_tag'][0]!=marker.observation_id or not 0<p['source_tag'][1]<marker.interpretation_version
                    or ledger.data['observations'].get(digest(p['source_tag']),{}).get('status')!='LIVE'):
                    self.append_terminal(aid,TerminalOutcome.STALE_SUPERSEDED,'MIGRATION_SOURCE_STALE')
                    return CommitResult(self.read_global_head(),(),TerminalOutcome.STALE_SUPERSEDED)
                retirement_events.extend(ledger.supersede(p['source_tag']))
            if any(o.op_type=='SET_IDENTITY_BINDING' and any(p not in ledger.paths() for p in o.payload.get('premise_support_refs',())) for o in plan_ops):
                self.append_terminal(aid,TerminalOutcome.STALE_SUPERSEDED,'MIGRATION_BINDING_STALE')
                return CommitResult(self.read_global_head(),(),TerminalOutcome.STALE_SUPERSEDED)
            # Retired own-version facts cannot conflict with their replacement.
            # The draft is discarded on complete rejection or any apply error.
            excluded,evidence=self._excluded(plan_ops,ledger)
            all_fragments=set(decision.committed)
            admitted=all_fragments-excluded
            outcome=TerminalOutcome.APPLIED if admitted else TerminalOutcome.REJECTED_CONFLICT_ADMISSION
            D=asdict(replace(decision,outcome=outcome,committed=tuple(sorted(admitted)),excluded=tuple(sorted(excluded)),excluded_evidence=tuple(evidence)))
            D['outcome']=outcome.value
            if not admitted:
                draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state)
                self._reports(ledger,evidence)
                ledger.refresh(before,decision.batch_hash,self.read_global_head()+1)
                t={'assertion_id':aid,'outcome':outcome.value,'excluded_evidence':evidence,
                   'precheck_refs':list(decision.precheck_refs)}
                seq=self._write_unit(draft,tx_ref=decision.batch_hash,terminal=t)
                return CommitResult(seq,(),outcome)
            selected=[o for o in plan_ops if set(o.fragment_refs)&admitted]
            required={d for o in selected for d in o.deps}
            while True:
                more=[o for o in plan_ops if o.payload.get('op_id') in required and o not in selected]
                if not more: break
                selected.extend(more); required.update(d for o in more for d in o.deps)
            keep={id(o) for o in selected}
            applied,events=self._apply(draft,[o for o in plan_ops if id(o) in keep])
            ledger.data['markers'][marker_key]=decision.batch_hash
            ledger.data['decisions'][decision.batch_hash]=D
            ledger.refresh(before,decision.batch_hash,self.read_global_head()+1,[*retirement_events,*events])
            seq=self._write_unit(draft,tx_ref=decision.batch_hash,decision=D)
            self._finish_batch(D)
            return CommitResult(seq,applied,outcome)

    def _finish_batch(self,D):
        aid='batch:'+D['batch_hash']
        if aid in self._terminal_records(): return
        draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
        self._reports(ledger,D.get('excluded_evidence',()))
        ledger.refresh(before,D['batch_hash']+':terminal',self.read_global_head()+1)
        self._write_unit(draft,tx_ref=D['batch_hash']+':terminal',terminal={'assertion_id':aid,'outcome':D['outcome'],'committed':D.get('committed',[]),'excluded':D.get('excluded',[]),'precheck_refs':D.get('precheck_refs',[])})

    def append_terminal(self, assertion_id, outcome, reason=''):
        if outcome in {TerminalOutcome.PENDING_ADMISSION_ORDER,TerminalOutcome.RESOLUTION_ONLY}: raise ValueError('TRANSIENT_OUTCOME_NOT_TERMINAL')
        with self._journal.atomic():
            old=self._terminal_records().get(assertion_id)
            if old:
                if old['outcome']!=outcome.value: raise JournalIntegrityError('INTEGRITY_ERROR: terminal rewrite')
                return self.read_global_head()
            return self._journal.append('resolution_log',{'kind':'terminal','assertion_id':assertion_id,'outcome':outcome.value,'reason':reason})

    def retract(self, assertion_id, new_status=AssertionStatus.SUPERSEDED, reason=''):
        with self._journal.atomic(),self._store._lock:
            self._refresh(); draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
            if assertion_id in ledger.data['assertions']:
                events=ledger.retract(assertion_id=assertion_id)
            elif assertion_id in ledger.data['bindings']:
                events=ledger.retract(binding_id=assertion_id)
            elif assertion_id in ledger.data['supports']:
                s=ledger.data['supports'][assertion_id]
                if s['status']!='LIVE': return False
                s['status']='SUPERSEDED'; events=[{'node_id':s['conclusion_ref'],'type':'SUPPORT_RETRACTED','support_id':assertion_id}]
            else: return False
            tx='retraction:'+digest([assertion_id,reason,len(ledger.data['events'])])
            ledger.refresh(before,tx,self.read_global_head()+1,events)
            self._write_unit(draft,tx_ref=tx,extra={'kind':'RETRACTION','assertion_id':assertion_id,'reason':reason})
            return True

    def retract_observation(self, observation_id, version, *, trigger_ref):
        with self._journal.atomic(),self._store._lock:
            self._refresh(); draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
            old=ledger.data['observations'].get(digest([observation_id,version]))
            if old and old['status']!='LIVE': return
            ledger.data['observations'].setdefault(digest([observation_id,version]),{'source_tag':[observation_id,version]})['status']='RETRACTED'
            events=ledger.retract(source_tag=[observation_id,version])
            tx='retraction:'+trigger_ref
            ledger.refresh(before,tx,self.read_global_head()+1,events)
            self._write_unit(draft,tx_ref=tx,extra={'kind':'RETRACTION','source_tag':[observation_id,version],'trigger_ref':trigger_ref})

    def supersede_observation(self,observation_id,version,*,trigger_ref):
        with self._journal.atomic(),self._store._lock:
            self._refresh(); draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
            oid=digest([observation_id,version]); old=ledger.data['observations'].get(oid)
            if old and old['status']!='LIVE': return
            events=ledger.supersede([observation_id,version])
            tx='supersede:'+trigger_ref
            ledger.refresh(before,tx,self.read_global_head()+1,events)
            self._write_unit(draft,tx_ref=tx,extra={'kind':'SUPERSEDE','source_tag':[observation_id,version],'trigger_ref':trigger_ref})

    def retract_usage_link(self,link_id,*,trigger_ref):
        with self._journal.atomic(),self._store._lock:
            self._refresh(); draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
            link=ledger.data['usage_links'][link_id]
            if link['kind']=='OPERATOR': raise ValueError('RETRACT_OPERATOR_LINK_FORBIDDEN')
            if link['status']!='LIVE': return
            link['status']='SUPERSEDED'; tx='usage-retraction:'+trigger_ref
            ledger.refresh(before,tx,self.read_global_head()+1)
            self._write_unit(draft,tx_ref=tx,extra={'kind':'USAGE_LINK_SUPERSEDED','link_id':link_id,'trigger_ref':trigger_ref})

    def close_report(self,report_id,*,trigger_ref):
        with self._journal.atomic(),self._store._lock:
            self._refresh(); draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state)
            if report_id not in ledger.data['reports']: raise KeyError(report_id)
            if report_id in ledger.data['closed_reports']: return
            tx='clarification:'+trigger_ref
            ledger.data['closed_reports'][report_id]={'report_id':report_id,'closed_by':'CLARIFICATION','tx_ref':tx}
            self._write_unit(draft,tx_ref=tx,extra={'kind':'REPORT_CLOSED','report_id':report_id,'closed_by':'CLARIFICATION','trigger_ref':trigger_ref})

    def rescan_conflicts(self,release,*,trigger_ref):
        from .canonical_ledger import incompatible
        with self._journal.atomic(),self._store._lock:
            self._refresh(); draft=self._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
            evidence=[]
            for sid in sorted(ledger.paths()):
                support=ledger.data['supports'][sid]; uid=support['conclusion_ref']; node=ledger.data['nodes'][uid]
                spec={**node,'node_ref':uid}
                if node.get('function_id')=='NOT': spec['proposition']=ledger.data['nodes'].get(node['operands'][0],{}).get('proposition')
                dated=[a for a in ledger.data['assertions'].values() if a['support_record_id']==sid and ledger.evidence_live({'record_id':a['assertion_id']})]
                for a in dated or [None]: evidence.append((spec,{'kind':'COMMITTED','record_id':a['assertion_id'] if a else sid},a['region'] if a else None,a.get('witness_ref') if a else None))
            created=[]
            for i,(a,ea,wa,shared_a) in enumerate(evidence):
                for b,eb,wb,shared_b in evidence[i+1:]:
                    rule=incompatible(a,b,release.entries('IncompatibilityRules'))
                    if not rule or not (shared_a and shared_a==shared_b or simultaneous(wa,wb)): continue
                    rid='report:'+digest(sorted((ea['record_id'],eb['record_id'])))
                    if rid in ledger.data['reports']: continue
                    ledger.data['reports'][rid]={'report_id':rid,'evidence_refs':[ea,eb],'node_refs':[a['node_ref'],b['node_ref']],'rule_id':rule,'resource_snapshot':release.sha256,'trigger_ref':trigger_ref,'candidates':[]}
                    created.append(rid)
            tx='conflict-scan:'+trigger_ref
            ledger.refresh(before,tx,self.read_global_head()+1)
            self._write_unit(draft,tx_ref=tx,extra={'kind':'CONFLICT_RESCAN','trigger_ref':trigger_ref,'resource_snapshot':release.sha256,'report_ids':created})
            return tuple(created)

    def status_of(self, assertion_id):
        s=self.ledger.data['supports'].get(assertion_id)
        return AssertionStatus(s['status']) if s else None

    def recover_from_head(self, *, drain_pending=True):
        recovered=[]
        with self._journal.atomic(),self._store._lock:
            self._refresh()
            for D in list(self.ledger.data['decisions'].values()):
                if 'batch:'+D['batch_hash'] not in self._terminal_records():
                    self._finish_batch(D); recovered.append(('batch:'+D['batch_hash'],TerminalOutcome(D['outcome'])))
            if drain_pending:
                from .goal_channel import recover as recover_goals
                recover_goals(self)
                for r in self.pending_batches():
                    p=r['payload']; raw=p['decision']; raw['marker']=MaterializationMarker(**raw['marker']); raw['outcome']=TerminalOutcome(raw['outcome'])
                    self.commit_transaction([StoreOp(**o) for o in p['ops']],raw['marker'],CommitDecision(**raw))
        return RecoveryReport(tuple(recovered),self.read_global_head(),False)

    def has_uid(self, uid): return self._store.has_uid(uid)
    def get_element_any_domain(self, uid): return self._store.get_element_any_domain(uid)
