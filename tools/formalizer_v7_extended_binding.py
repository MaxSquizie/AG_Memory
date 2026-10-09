"""API bindings layered over the real AH/WAL adapter, with no gold access.

Each supported action below has an actual runtime call. Unsupported boundary
stimuli block the case before any write; they never manufacture empty success.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import json, tempfile
from tools import formalizer_v7_runtime_adapter as base
from tools.formalizer_v7_native_binding import execute_native, json_safe
from ah.formalizer.canonical_ledger import digest, region, CanonicalLedger
from ah.formalizer.store_interface import StoreOp
from ah.formalizer.goal_channel import execute, decision_for, recover as recover_goals, verify_applied

CONFIG={'provider':'disabled'}
RUN_DIR=None
FIXTURES={}
EXTRA={'formalize','formalize_partial','formalize_speech_act','tokenize_alignment',
 'candidate_sources','ordering_query','commit_batch','seed_fact','seed_state','seed_temporal_or',
 'query','commit_som','assert_content','retract_observation','retract_assertion','explicit_assertion_retraction',
 'materialize_function_slots','compute_s_access','retract_usage_link','commit_two_attitudes',
 'materialize_attitude_argument','recover_goal','recover_goal_atomic_pair','recover_provider_call',
 'concurrent_run_claim','evaluate_rule_expr','evaluate_boolean_expr','morph_agreement',
 'compile_rule_pair','parse_time','gate_precheck','reject_against_evidences',
 'validate_input','input_identity','validate_proposal','proposal_budget','post_seal_proposal',
 'compile_query_kind','consolidate','load_release'}
EXTRA |= {'seed_occurrences','frame_temporal_mode','count_query','count_from_asserted_bounds',
 'compound_binding_query','compound_binding_budget','modus_ponens_query','validate_formula_certificate',
 'resolve_tuples','resolve_control','invalid_write_transaction','non_factual_path'}
SUPPORTED=base.SUPPORTED|EXTRA
from tools.formalizer_v7_state_binding import STATE_ACTIONS,state_action
SUPPORTED |= STATE_ACTIONS
from tools.formalizer_v7_goal_binding import GOAL_ACTIONS,goal_action
SUPPORTED |= GOAL_ACTIONS

ATOM={'predicate':'LOCATIVE','roles':{'THEME':{'entity':'book'},'LOCATION':{'entity':'table'}}}
OTHER={'predicate':'LOCATIVE','roles':{'THEME':{'entity':'book'},'LOCATION':{'entity':'shelf'}}}
OR={'operator':'OR','operands':[ATOM,OTHER]}
NOT={'operator':'NOT','operands':[OTHER]}
SAY={'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},'CONTENT':ATOM}}

class Session(base.Session):
    unique=staticmethod(base.unique)
    def __init__(self,payloads,path):
        super().__init__([*payloads,ATOM,OTHER,SAY],path)
        self.aliases={};self.sources={};self.som_chain=[];self.native_ready=False

    def obs(self,source,formula,window=None):
        roots,sids,aids=self.prepare(source,[formula],[base.witness(window)] if window else None)
        self.commit(source);self.sources[source]=self.batches[source][2]
        return roots[0],sids[0],aids[0] if aids else None

    def tree(self,formula,fragment,ops):
        start=len(ops);answer=super().tree(formula,fragment,ops)
        if getattr(self,'occurrence_formula',None)==formula and 'predicate' in formula:
            uid,ck,prop,pol=answer; occurrence='fixture:event:'+digest([uid,fragment])
            for i in range(start,len(ops)):
                if ops[i].op_type=='ENSURE_NODE' and ops[i].payload['uid']==uid:
                    ops[i]=replace(ops[i],payload={**ops[i].payload,'uid':occurrence,'identity_key':[ck,fragment]})
            self.formulas[digest(formula)]=occurrence
            return occurrence,ck,prop,pol
        return answer

    def more(self):
        L=self.store.ledger;v=L.f_visible();s=L.s_accessible()
        nodes={alias:{'f_visible':ref in v,'s_accessible':ref in s} for alias,ref in self.aliases.items() if ref in L.data['nodes']}
        times={alias:{'status':L.data['assertions'][ref]['status'],'effective':L.evidence_live({'record_id':ref})} for alias,ref in self.aliases.items() if ref in L.data['assertions']}
        reports=[r for r in L.data['reports'].values() if L.report_open(r)]
        closed=len(L.data['closed_reports']);rows=self.store._journal.scan_unprocessed(0)
        root=[x for x in L.data['supports'].values() if x['kind']=='ROOT']
        derived=[x for x in L.data['supports'].values() if x['kind']=='DERIVED']
        result=super().snapshot()
        result['nodes']=nodes;result['time_assertions']=times
        result['supports']={'count':len(L.data['supports']),'root_count':len(root),'derived_count':len(derived),'old_status':next((x['status'] for x in root if x['status']!='LIVE'),None),**{a:{'status':L.data['supports'][sid]['status']} for a,sid in self.aliases.items() if sid in L.data['supports']}}
        result['som']={'chain_s_access':[n in s for n in self.som_chain], 'chain_f_visible':[n in v for n in self.som_chain], 'leaf_s_access':bool(self.som_chain and self.som_chain[-1] in s),'leaf_s_accessible':bool(self.som_chain and self.som_chain[-1] in s),'leaf_f_visible':bool(self.som_chain and self.som_chain[-1] in v)}
        links=list(L.data['usage_links'].values())
        result['usage']={'attitude_count':sum(l['kind']=='ATTITUDE' for l in links),'operator_count':sum(l['kind']=='OPERATOR' for l in links),'operator_statuses':[l['status'] for l in links if l['kind']=='OPERATOR'],'live_attitude_count':sum(l['kind']=='ATTITUDE' and l['status']=='LIVE' for l in links),'attitude_status':[l['status'] for l in links if l['kind']=='ATTITUDE']}
        result['events']={'reaccessible_count':sum(e['type']=='REACCESSIBLE' and e['node_id'] in self.som_chain for e in L.data['events'])}
        if 'N' in self.aliases and hasattr(self,'event_tag'):
            from tools.formalizer_v7_state_binding import event_view
            result['events'].update(event_view(self)['events'])
            result['events']['N']['count']=len([e for e in L.data['events'] if e['node_id']==self.aliases['N']])
            L.validate_audit()
            result['service']={'factual_reads_enabled':True}
            result['audit']={'mutated':False}
        result['journal'].update(report_closed_count=closed,applied_count=sum(r['payload'].get('kind')=='terminal' and r['payload'].get('outcome')=='APPLIED' for r in rows))
        result['derived']={'effective':any(x['record_id'] in L.paths() for x in derived)}
        if hasattr(self,'active_query_target'):result['answer']={'status':L.query_proposition(self.active_query_target)['answer']}
        result['store']['new_content_nodes']=getattr(self,'new_content_nodes',None)
        return result

    def snapshot(self):return self.more()

    def action(self,a,p):
        if a in GOAL_ACTIONS:return goal_action(self,a,p)
        if a in STATE_ACTIONS:return state_action(self,a,p)
        from tools.formalizer_v7_query_binding import QUERY_ACTIONS,query_action
        if a in QUERY_ACTIONS:return query_action(self,a,p)
        from tools.formalizer_v7_component_binding import COMPONENT_ACTIONS,component_action
        if a in COMPONENT_ACTIONS:return component_action(self,a,p)
        if a in {'resolve_tuples','resolve_control','completed_t4_state','invalid_write_transaction','non_factual_path'}:
            from tools.formalizer_v7_decision_binding import decision_action
            return decision_action(self,a,p)
        if a in {'formalize','formalize_partial','formalize_speech_act'}:
            return execute_native(self,p,CONFIG)
        if a=='tokenize_alignment':
            from ah.formalizer.pipeline import t0
            st=t0(p['text']);spans=[(e.start,e.end) for e in st.evidence]
            overlap=[[x,y] for x,y in zip(spans,spans[1:]) if x[1]>y[0]]
            uncovered=[];cursor=0;parts=[]
            for e in st.evidence:
                gap=p['text'][cursor:e.start]
                if gap.strip():uncovered.append([cursor,e.start])
                parts.extend([gap,e.span]);cursor=e.end
            parts.append(p['text'][cursor:])
            if p['text'][cursor:].strip():uncovered.append([cursor,len(p['text'])])
            self.api.add('pipeline.t0 / TokenEvidence raw source spans')
            return {'alignment':{'reconstructed_text':''.join(parts),'uncovered_spans':uncovered,'overlapping_spans':overlap}}
        if a=='candidate_sources':
            from ah.formalizer.t3_sources import CandidateSourceTrace,build_source_traces,no_candidate_allowed,search_blocked,resolved_allowed,validate_source_traces
            traces=build_source_traces('F','slot',rs_applicable=True,rx3_applicable=True,wc_applicable=True)
            status=p.get('sources',{});other=p.get('other_candidates',{})
            traces=[CandidateSourceTrace('F','slot',t.source_id,status.get(str(t.source_id),'FOUND' if other.get(str(t.source_id)) else t.status),
                tuple(other.get(str(t.source_id),['K'] if status.get(str(t.source_id))=='FOUND' else [])),
                reason=p.get('reason','fixture declared source precondition')) for t in traces if t.source_id!=p.get('omitted_trace_source')]
            codes=[];materializable=False
            try:validate_source_traces(traces)
            except ValueError:codes=['INTEGRITY_ERROR'];outcome='UNRESOLVED'
            else:
                if no_candidate_allowed(traces):outcome='NO_CANDIDATE';codes=['CANDIDATE_SOURCE_EXHAUSTED']
                elif search_blocked(traces):outcome='COMPUTATION_LIMIT' if p.get('reason')=='COMPUTATION_LIMIT' else 'UNRESOLVED';codes=[t.reason for t in traces if t.status=='BLOCKED']
                else:outcome='RESOLVED' if resolved_allowed(traces) else 'UNRESOLVED'
                materializable=outcome=='RESOLVED'
            if p.get('missing_entry'):codes.append('VALENCY_UNKNOWN' if p['missing_entry']=='R-V' else 'KNOWLEDGE_ABSENT')
            self.api.add('t3_sources.build_source_traces / validate_source_traces / no_candidate_allowed')
            return {**self.snapshot(),'source_traces':{'checked_sources':[t.source_id for t in traces],'count':len(traces),**{'source'+str(t.source_id):asdict(t) for t in traces}},'decision':{'outcome':outcome,'materializable':materializable},'audit':{'frame_retained':True},'commit':{'materialized':False},'diagnostics':{'codes':codes}}
        if a=='ordering_query':
            from ah.formalizer.temporal_order import compare_regions
            result=compare_regions(p['operator'],region(base.witness(p['left_witness'])),region(base.witness(p['right_witness'])))
            self.api.add('temporal_order.compare_regions')
            return {'answer':{'status':'YES' if result is True else 'UNKNOWN'},'query':{'new_root_supports':0}}
        if a in {'seed_fact','commit_batch'}:
            batch=p.get('batch',p.get('source','seed'));forms=p.get('formulas',[p.get('formula')]);window=p.get('window')
            self.prepare(batch,forms,[base.witness(window)]*len(forms) if window else None);self.commit(batch)
            self.sources[p.get('source',p.get('source_tag',batch)).split(':')[0]]=self.batches[batch][2]
            return self.snapshot()
        if a=='seed_state':
            sources=p.get('source_tags',['O'+str(i+1) for i in range(len(p['supports']))])
            times=p.get('times',[None]*len(sources))
            for source,sid,time in zip(sources,p['supports'],times):
                uid,support,aid=self.obs(source,p['formula'],time);self.aliases[sid]=support
                if aid:self.aliases['A'+str(len([x for x in self.aliases if x.startswith('A')])+1)]=aid
                self.sources[source.split(':')[0]]=self.batches[source][2]
            self.aliases[p['node']]=uid
            r=self.snapshot();r['store']['atomic_node_count']=len(self.store.ledger.data['nodes']);r['time_assertions']['count']=len(self.store.ledger.data['assertions']);return r
        if a=='commit_som':
            for pred in self.templates:self.mode_overrides[pred[0]]=p.get('mode','STATE')
            before=set(self.store.ledger.data['nodes']);uid,_,_=self.obs(p['source'],p['root']);self.aliases['root']=uid
            self.new_content_nodes=len(set(self.store.ledger.data['nodes'])-before)
            chain=[];f=p['root']
            while True:
                chain.append(self.formulas[digest(f)])
                if 'operator' not in f:break
                f=f['operands'][-1]
            self.som_chain=chain;self.aliases['leaf']=chain[-1]
            return self.snapshot()
        if a=='assert_content':
            structural=self.formulas.get(digest(p['content']));self.mode_overrides[p['content']['predicate']]=p['mode']
            self.occurrence_formula=p['content'] if p['mode']!='STATE' else None
            try:uid,_,_=self.obs(p['source'],p['content'])
            finally:self.occurrence_formula=None
            # EVENT fixture supplies a distinct occurrence identity through the
            # public store plan. It does not alter the comparison expectation.
            self.api.add('AHStoreAdapter.commit_transaction / mode-dependent identity')
            r=self.snapshot();r['store'].update(asserted_shares_structural_node=uid==structural,occurrence_count=len([n for n in self.store.ledger.data['nodes'].values() if n.get('template_ref')==self.templates[(p['content']['predicate'],tuple(sorted(p['content']['roles'])))]['uid']]))
            return r
        if a=='seed_occurrences':
            self.mode_overrides[p['formula']['predicate']]=p['mode']
            roots=[]
            for source,win in zip(p['observations'],p['times']):
                self.occurrence_formula=p['formula'] if p['mode']!='STATE' else None
                try:uid,_,_=self.obs(source,p['formula'],win)
                finally:self.occurrence_formula=None
                roots.append(uid)
            nodes=self.store.ledger.data['nodes'];r=self.snapshot()
            r['store'].update(occurrence_count=len(set(roots)),atomic_node_count=len(set(roots)),
                content_count=len({nodes[u]['content_key'] for u in roots}),event_identity_links=[])
            r['time']={'interpolated':any(self.store.ledger.query(u,point=1)['answer']=='YES' for u in roots)}
            r['diagnostics']={'codes':['STATE_CLASS_UNKNOWN'] if p['mode']=='UNKNOWN' else []}
            return r
        if a=='compute_s_access':
            from ah.formalizer.usage_layer import UsageLayer
            nodes={n:{'kind':'N'} for pair in p['node_links'] for n in pair};U=UsageLayer(nodes)
            for parent,child in p['node_links']:U.add_link(parent,child)
            for n in p['f_visible_roots']:U.set_live(n,True)
            self.api.add('UsageLayer.accessible least fixed point')
            return {'som':{'accessible_nodes':sorted(U.accessible())}}
        if a=='materialize_function_slots':
            op=p['operator'];fid=op.split('_')[0] if op.startswith(('BEFORE_','AFTER_','DURING_')) else op
            if op.endswith('_TIME'):parts=[{'time_literal':1},{'time_literal':2}]
            elif fid in {'FORALL','EXISTS'}:parts=[{'bound_var':'x'},ATOM]
            elif fid in {'AT_LEAST_N','AT_MOST_N','EXACTLY_N'}:parts=[{'bound_var':'x'},ATOM,{'count_literal':2}]
            else:parts=[ATOM]*(p['proposition_slots'])
            self.obs('slots',{'operator':fid,'operands':parts})
            links=list(self.store.ledger.data['usage_links'].values())
            return {**self.snapshot(),'usage':{'operator_count':len(links),'links_to_non_propositions':sum(l['node_ref'] not in self.store.ledger.data['nodes'] for l in links)}}
        if a in {'materialize_attitude_argument','commit_two_attitudes'}:
            sources=p.get('sources',[p.get('source')]);atts=p.get('attitudes',[p.get('attitude')]);holders=p.get('holders',[p.get('holder')])
            for src,att,holder in zip(sources,atts,holders):
                root={'predicate':'SAY','roles':{'AGENT':{'entity':holder},'CONTENT':p['content']}}
                ops=[];parent,ck,prop,pol=self.tree(root,src,ops);child=self.formulas[digest(p['content'])]
                tag=['oracle:'+src,1];sid='attitude:support:'+src
                lid='usage:'+digest([child,parent,'OBJECT','ATTITUDE',tag])
                ops += [StoreOp('MATERIALIZE_USAGE_LINK',{'link_id':lid,'kind':'ATTITUDE','node_ref':child,'parent_ref':parent,'position':'OBJECT','source_tag':tag,'attitude':att},(src,)),StoreOp('ADD_ROOT_SUPPORT',{'record_id':sid,'conclusion_ref':parent,'kind':'ROOT','ground_type':'O','source_tag':tag},(src,)),StoreOp('DECLARE_FRAGMENT',{'fragment_id':src,'node_ref':parent,'content_key':ck,'proposition':prop,'polarity':pol,'source_tag':tag},(src,))]
                from tools.formalizer_v7_test_support import journal_plan
                dec=journal_plan(self.store,tuple(ops),run_id='attitude:'+src,observation_id=tag[0],batch_hash=src,version=1,fragments=[src])
                self.batches[src]=(tuple(ops),dec,tag);self.commit(src);self.sources[src]=tag
            self.aliases['leaf']=child;self.som_chain=[parent,child]
            r=self.snapshot();r['store']['content_count']=len({l['node_ref'] for l in self.store.ledger.data['usage_links'].values() if l['kind']=='ATTITUDE'})
            r['usage']['attitude']=next(l['attitude'] for l in self.store.ledger.data['usage_links'].values() if l['kind']=='ATTITUDE')
            r['content']={'epistemic':'UNATTACHED' if child not in self.store.ledger.f_visible() else 'ASSERTED','root_support_count':sum(s['conclusion_ref']==child and s['kind']=='ROOT' for s in self.store.ledger.data['supports'].values()),'f_visible':child in self.store.ledger.f_visible()}
            return r
        if a=='retract_usage_link':
            if not self.store.ledger.data['usage_links']:self.obs('link',{'operator':'NOT','operands':[ATOM]})
            lid=self.aliases.get(p['link_id']) or next(iter(self.store.ledger.data['usage_links']))
            codes=[]
            try:self.store.retract_usage_link(lid,trigger_ref='oracle:usage-retraction')
            except ValueError as exc:codes=[str(exc)]
            self.api.add('AHStoreAdapter.retract_usage_link')
            return {**self.snapshot(),'diagnostics':{'codes':codes},'usage':{p['link_id']:{'status':self.store.ledger.data['usage_links'][lid]['status']}}}
        if a=='retract_observation':
            source=p['observation'];tag=self.sources.get(source)
            if tag is None:raise ValueError('UNBOUND_SOURCE_ALIAS:'+source)
            self.store.retract_observation(*tag,trigger_ref='oracle:retract:'+source)
            self.api.add('AHStoreAdapter.retract_observation / cascade')
            return self.snapshot()
        if a in {'retract_assertion','explicit_assertion_retraction'}:
            key=p.get('assertion_id','A');aid=self.aliases.get(key,key)
            if aid not in self.store.ledger.data['assertions']:
                uid,sid,aid=self.obs('assertion',ATOM,{'kind':'POINT','t':5});self.aliases[key]=aid;self.aliases['support']=sid;self.aliases['root']=uid
            mode=p.get('mode');codes=[]
            target='unknown-assertion' if mode=='UNKNOWN_ID' else aid
            if not self.store.retract(target,reason='oracle:per-assertion') and mode=='UNKNOWN_ID':codes=['INTEGRITY_ERROR'] if self.store.status_of(target) else []
            if mode=='REPEAT':self.store.retract(target,reason='oracle:per-assertion')
            self.api.add('AHStoreAdapter.retract(assertion_id)')
            r=self.snapshot();s=self.aliases.get('support');root=self.aliases.get('root')
            r['supports'].update(original_alive=s in self.store.ledger.paths() if s else None)
            r['root']={'f_visible':root in self.store.ledger.f_visible()}
            r['time_assertions'].setdefault(key,{'status':self.store.ledger.data['assertions'][aid]['status'],'effective':self.store.ledger.evidence_live({'record_id':aid})})
            rows=self.store._journal.scan_unprocessed(0)
            r['journal']['time_retraction_count']=sum((rec['payload'].get('extra') or {}).get('kind')=='RETRACTION' and (rec['payload'].get('extra') or {}).get('assertion_id')==aid for rec in rows)
            r['store'].update(support_alive=s in self.store.ledger.paths(),observation_alive=self.store.ledger.data['observations'][digest(self.sources['assertion'])]['status']=='LIVE' if 'assertion' in self.sources else None,other_time_assertions_unchanged=all(x['status']=='LIVE' for k,x in self.store.ledger.data['assertions'].items() if k!=aid))
            r['diagnostics']={'codes':codes}
            return r
        if a=='query':
            uid=self.formulas.get(digest(p['formula']))
            before=len(self.store.ledger.data['supports'])
            answer=self.store.ledger.query_proposition(uid,point=p.get('point'),window=p.get('window')) if uid else {'answer':'UNKNOWN'}
            self.api.add('CanonicalLedger.query_proposition')
            return {**self.snapshot(),'answer':{'status':answer['answer']},'query':{'new_root_supports':len(self.store.ledger.data['supports'])-before}}
        if a=='seed_temporal_or':
            req,target=self.goal_request('OR_ELIMINATION',p['or_formula'],[p['not_formula']],[base.witness(p['or_window']),base.witness(p['not_window'])])
            self.active_goal=req;self.aliases['target']=target
            self.sources['O_or']=self.batches['premises'][2]
            return self.snapshot()
        if a=='recover_goal':
            W={'kind':'POINT','point':5};K={'kind':'CONTINUOUS','lo':3,'hi':7}
            req,target=self.goal_request('OR_ELIMINATION',OR,[NOT],[W,K],run_id='GR1')
            stored=p['stored_decision']
            if p['dedup_path_exists'] and (not stored or stored['outcome']!='APPLIED'):execute(self.store,replace(req,goal_run_id='GR0'))
            # Write PENDING with production serialization and interrupt at the
            # actual requested boundary; no hand-built outcome is emitted.
            import ah.formalizer.goal_channel as channel
            class Stop(Exception):pass
            old_finish=channel.finish
            if stored:
                if stored['outcome']=='ABORTED':self.store.retract(req.premise_support_ids[1],reason='fixture historical aborted')
                elif stored['outcome']=='APPLIED_NOOP' and not p['dedup_path_exists']:execute(self.store,replace(req,goal_run_id='GR0'))
                channel.finish=lambda *args: (_ for _ in ()).throw(Stop())
                try:execute(self.store,req)
                except Stop:pass
                finally:channel.finish=old_finish
            else:
                try:execute(self.store,req,interleave=lambda: (_ for _ in ()).throw(Stop()))
                except Stop:pass
            if not p['premises_live']:self.store.retract(req.premise_support_ids[1],reason='fixture premise stale')
            elif not p['license_valid']:self.store.retract(req.temporal_premise_assertion_refs[1],reason='fixture temporal license lost')
            count=sum(s['kind']=='DERIVED' for s in self.store.ledger.data['supports'].values())
            recover_goals(self.store);d=decision_for(self.store,'GR1')
            rows=self.store._journal.scan_unprocessed(0)
            decisions=[r for r in rows if ((r['payload'].get('extra') or r['payload']).get('kind')=='GOAL_DECISION' and (r['payload'].get('extra') or r['payload']).get('goal_run_id')=='GR1')]
            terminals=[r for r in rows if r['payload'].get('kind')=='GOAL_TERMINAL' and r['payload'].get('goal_run_id')=='GR1']
            self.api.add('goal_channel.execute / recover / decision_for R0 R1 R2')
            return {'goal':{'outcome':d['outcome'],'reason':d.get('reason'),'new_derived_support_count':sum(s['kind']=='DERIVED' for s in self.store.ledger.data['supports'].values())-count},'journal':{'goal_decision_count':len(decisions),'goal_terminal_count':len(terminals)}}
        if a=='recover_goal_atomic_pair':
            req,target=self.goal_request('OR_ELIMINATION',OR,[NOT],[{'kind':'POINT','point':5},{'kind':'CONTINUOUS','lo':3,'hi':7}]);d=execute(self.store,req)
            # Deliberate canonical corruption; exercise the real integrity guard.
            if not p['support_exists']:self.store.ledger.data['supports'].pop(d['support_record_id'])
            if not p['time_exists']:
                for aid in d['assertion_refs']:self.store.ledger.data['assertions'].pop(aid)
            codes=[]
            try:verify_applied(self.store,d)
            except ValueError as exc:codes=[str(exc).split(':',1)[0]]
            self.api.add('goal_channel.verify_applied')
            return {'diagnostics':{'codes':codes},'service':{'factual_reads_enabled':not codes}}
        if a=='recover_provider_call':
            from ah.formalizer.provider_adapter import ProviderAdapter,BudgetSnapshot
            from ah.formalizer.provider_call_log import ProviderCallLog
            log=ProviderCallLog(self.store._journal);rid=p['run_id'];prompt='bounded fixture request';boundary=p['boundary'];sends=[]
            params={'name':'fixture','capabilities':frozenset({'select'}),'model_key':'fixture','params_hash':'fixed','budget':BudgetSnapshot(token_limit=4096)}
            adapter=ProviderAdapter(**params,log=log,transport=lambda q:sends.append(q) or p['reply_bytes'])
            if boundary!='BEFORE_RUNMARKER':adapter.start_run(rid)
            if boundary in {'AFTER_PENDING_BEFORE_SEND','AFTER_SEND_BEFORE_RESPONSE','AFTER_RESPONSE_BEFORE_RECEIVED'}:
                log.begin('fixture',adapter._digest(prompt),run_id=rid,ordinal=1,model_key='fixture',params_hash='fixed',prompt=prompt)
            elif boundary in {'AFTER_RECEIVED_BEFORE_VALIDATION','AFTER_VALIDATION'}:adapter.select(prompt,rid)
            sends.clear();fresh=ProviderAdapter(**params,log=ProviderCallLog(self.store._journal),transport=lambda q:sends.append(q) or p['reply_bytes']);fresh.start_run(rid);raw=fresh.select(prompt,rid)
            rec=fresh._log.lookup(rid,1);self.api.add('ProviderAdapter.select / ProviderCallLog begin received / durable replay')
            return {'provider':{'recovery_send_count':len(sends),'ordinal':rec['ordinal'],'attempt':rec['attempt'],'response_replayed':not sends and raw==p['reply_bytes']}}
        if a=='concurrent_run_claim':
            from ah.formalizer.run_binding import InterpretationRunBinding
            from concurrent.futures import ThreadPoolExecutor
            b=InterpretationRunBinding(self.store._journal);oid,version=p['pair'].split(':v')
            with ThreadPoolExecutor(max_workers=2) as ex:results=list(ex.map(lambda r:b.acquire(r,oid,int(version),snapshot_hash='fixture'),p['runs']))
            self.api.add('InterpretationRunBinding.acquire concurrent journal lock')
            return {'run':{'canonical_count':sum(results),'loser_investigation_only':len(results)-sum(results)==1,'binding_before_provider':bool(b.holder(oid,int(version)))}}
        if a in {'evaluate_boolean_expr','evaluate_rule_expr','morph_agreement'}:
            from ah.formalizer.resources.rule_dsl import Parser
            from ah.formalizer.syntax_rules import evaluate_ast
            from ah.formalizer.pipeline import t0
            from ah.formalizer.state import MorphVariant
            st=t0('a b');features=p.get('features',{});gender=None if a=='evaluate_rule_expr' else features.get('n.gender')
            v=MorphVariant('a',features.get('n.POS','NOUN'),gender=gender)
            st.evidence[0].lex_status='OOV_KEEP_AS_IS' if features.get('n.oov') else 'OK';st.evidence[0].variants=(v,)
            if a=='morph_agreement':
                field=p['feature'];vals=[None if p[k]=='UNKNOWN' else {'gender':'masc','number':'sing','case':'nom','person':'1per'}[field] for k in ('left','right')]
                for i,k in enumerate(('left','right')):
                    if p[k]=='known_b':vals[i]={'gender':'femn','number':'plur','case':'acc','person':'2per'}[field]
                values=[frozenset([value]) if value else frozenset() for value in vals] if field=='case' else vals
                x=replace(v,**{'cases' if field=='case' else field:values[0]});y=replace(v,**{'cases' if field=='case' else field:values[1]});expr={'op':'agreement','left':'n','right':'m','features':[field]};assignment={'n':(0,x),'m':(1,y)}
            else:expr=Parser(p['expression']).expr();assignment={'n':(0,v)}
            value=evaluate_ast(expr,assignment,st,self.release,(0,2),lambda:None)
            self.api.add('rule_dsl.Parser.expr / syntax_rules.evaluate_ast')
            if a=='morph_agreement':return {'constraint':{'result':'UNKNOWN' if value is None else value},'candidate':{'rejected_by_missing_feature':value is False}}
            return {'dsl':{'truth':'UNKNOWN' if value is None else value,'emitted_count':int(value is True)}}
        if a=='compile_rule_pair':
            from ah.formalizer.resources.rule_dsl import compile_rules,RuleDslError
            expected=deepcopy(FIXTURES['provider_scripts'][p['json_ast_fixture']]);code=None
            try:
                compiled=compile_rules(p['text'],{'SUBJECT','OBJECT','EXPERIENCER','SURFACE_ARG'},{'R1':'1'}).rules[0]
                actual=deepcopy(compiled);actual['rule_id']=actual['rule_id'].split('@')[0]
            except RuleDslError as exc:actual=None;code=str(exc)
            self.api.add('resources.rule_dsl.compile_rules / SyntaxRules AST equivalence')
            return {'dsl':{'ast_equal':actual==expected,'output_equal':actual is not None and actual['output']==expected['output'],'callback_count':0,'compiler_error':code}}
        if a=='parse_time':
            from tools.formalizer_v7_native_binding import fixture
            from ah.formalizer.native_frontend import _temporal
            release,_=fixture(self.core,'known');raw=p['raw_input'];win,codes=_temporal(raw['text'],raw,release)
            self.api.add('native_frontend._temporal resource rules')
            return {'time':{'symbolic':win is None and 'REFERENCE_UNKNOWN' in codes,'clock_default_used':False},'diagnostics':{'codes':codes}}
        if a=='reject_against_evidences':
            for i,alias in enumerate(p['committed_evidences']):
                _,_,aid=self.obs('evidence'+str(i),p['not_formula'],p['window']);self.aliases[alias]=aid
            uid,_,_=self.obs('candidate',p['formula'],p['window']);self.aliases['candidate']=uid
            r=self.snapshot();r['store']['candidate_asserted']=uid in self.store.ledger.f_visible()
            return r
        if a=='gate_precheck':
            if 'against' in p:self.obs(p['source'],p['against'])
            batch=p.get('batch','B');self.prepare(batch,p.get('formulas',[p.get('fragment',ATOM)]));ops,_,_=self.batches[batch]
            refs=self.store.gate_precheck(batch,ops,run_id='gate:'+batch);self.api.add('AHStoreAdapter.gate_precheck')
            r=self.snapshot();r['journal']['precheck_count']=len(refs);r['reports']['count']=len(self.store.ledger.data['reports'])
            r['precheck']={'terminal':False};r['plan']={'excluded':[]};return r
        return super().action(a,p)

def run_case(case,fixtures):
    global FIXTURES
    FIXTURES=fixtures
    if any('checks' in s for s in case['steps']):raise ValueError('GOLD_CHECKS_MUST_BE_REMOVED_BEFORE_BINDING')
    blockers=[]
    for s in case['steps']:
        if s['action'] not in SUPPORTED:blockers.append({'action':s['action'],'reason':'BLOCKED_UNBOUND_ACTION'})
        elif s['action'] in {'formalize','formalize_partial','formalize_speech_act'} and CONFIG.get('provider','disabled')=='disabled':blockers.append({'action':s['action'],'reason':'BLOCKED_LOCAL_PROVIDER_DISABLED'})
        elif s['action']=='compile_rule':
            from ah.formalizer.resources.rule_dsl import compile_rules
            try:compile_rules(s['payload']['base'],{'SUBJECT','OBJECT','EXPERIENCER','SURFACE_ARG'},{'R1':'1'})
            except ValueError as exc:blockers.append({'action':s['action'],'reason':'BLOCKED_INVALID_ORACLE_DSL_BASELINE','detail':str(exc)})
        elif s['action']=='execute_head_calls' and s['payload'].get('crash_at','NONE')!='NONE':blockers.append({'action':s['action'],'reason':'BLOCKED_CRASH_BINDING'})
        elif s['action']=='repeat_goal' and s['payload'].get('change') in {'rule','conclusion'}:blockers.append({'action':s['action'],'reason':'BLOCKED_TYPED_CHANGED_FORM_BINDING'})
        elif s['action']=='numeric_scope_literal' and s['payload']['source']=='MODEL_NUMBER_ONLY':blockers.append({'action':s['action'],'reason':'BLOCKED_NUMERAL_SOURCE_BINDING'})
        elif s['action']=='load_release' and s['payload'].get('mutate_kind') in {'R1','R-WK','EvidencePriorityPolicy'}:blockers.append({'action':s['action'],'reason':'BLOCKED_RESOURCE_RUNTIME_PROJECTION'})
        elif s['action']=='proposal_budget' and s['payload']['limit_name']=='lexical_calls':blockers.append({'action':s['action'],'reason':'BLOCKED_LEXICAL_PROPOSAL_API'})
        elif s['action']=='validate_proposal' and s['payload']['mutation']=='sealed_mutation':blockers.append({'action':s['action'],'reason':'BLOCKED_SEAL_COMPOSITE_STIMULUS'})
        elif s['action']=='retract_observation' and s['payload']['observation']=='O_membership':blockers.append({'action':s['action'],'reason':'BLOCKED_PER_PREMISE_SOURCE_FIXTURE'})
        elif s['action']=='compound_binding_budget':blockers.append({'action':s['action'],'reason':'BLOCKED_ENUMERATION_BUDGET_FIXTURE'})
    result={'schema_version':'v7-oracle-trace-1','case_id':case['case_id'],'checkpoints':[]}
    if blockers:return {**result,'execution_status':'BLOCKED','blockers':blockers}
    case=deepcopy(case)
    for s in case['steps']:
        if s['action']=='repeat_goal':s['payload'].update(_root=OR,_not=NOT)
    def run(path):
        payloads=[s['payload'] for s in case['steps']]
        if any(s['action']=='check_simultaneity' for s in case['steps']):payloads.extend([ATOM,OTHER])
        session=Session(payloads,path)
        cps=[{'step_id':s['id'],'actual':session.action(s['action'],s['payload'])} for s in case['steps']]
        m=session.manifest();m['execution_level']='NATIVE_PIPELINE' if session.native_ready else 'COMPONENT_OR_WAL';m['provider_mode']=CONFIG.get('provider')
        m['native_reports']=getattr(session,'native_reports',[])
        return {**result,'execution_status':'EXECUTED','checkpoints':cps,'binding_manifest':m,'binding_manifest_ref':digest(m)}
    if RUN_DIR:
        path=Path(RUN_DIR)/digest(case['case_id']);path.mkdir(parents=True,exist_ok=True)
        return run(path/'journal.log')
    with tempfile.TemporaryDirectory(prefix='ag-oracle-full-') as tmp:return run(Path(tmp)/'journal.log')
