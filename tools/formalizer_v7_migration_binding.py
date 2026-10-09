"""Declared migrations and replay bindings against the production AH/WAL APIs.

The fixture declares a small predicate/subject grammar and signed TEST_ONLY
releases independently of corpus answers. Every checkpoint below comes from
the actual ledger, binding, provider log, or migration receipt. No gold checks
are accepted by this module.
"""
from copy import deepcopy
from dataclasses import asdict, replace

from ah.core.journal import JournalIntegrityError
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.migration import reinterpret_observation, plan_mass_migration, resume_mass_migration
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.provider_adapter import ProviderAdapter, BudgetSnapshot
from ah.formalizer.provider_call_log import ProviderCallLog
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.store_interface import MaterializationMarker
from ah.formalizer.v7_pipeline import interpret_full
from tools.formalizer_v7_test_support import NativeSelector, role, sign_test_release, test_release, journal_plan


MIGRATION_ACTIONS = {
    'execute_migration', 'plan_migration', 'recover_bulk_migration',
    'supersede_version', 'rerun_same_pair', 'change_source',
    'change_declared_read', 'change_declared_resource',
    'execute_identical_prompts', 't6_with_marker', 'reconcile',
}


class CrashStop(RuntimeError):
    """Test-only interruption at a real durable/store boundary."""


def _resign(manifest):
    m=deepcopy(manifest)
    m['coverage_report']['units_by_kind']={r['kind']:len(r['entries']) for r in m['entries']}
    m['coverage_report']['resource_content_sha256']=digest({k:m[k] for k in ('kind','version','schema_version','entries','dependency_versions')})
    return sign_test_release(m)[0]


def _releases(session, ambiguous=False):
    # Generic subject/predicate construction; not a rule keyed by a case or
    # sentence. Removing its lexical entry leaves the very same syntax intact.
    rule={'rule_id':'TEST_ONLY-SUBJECT-PREDICATE',
        'input_feature_pattern':{'captures':{
            'p':{'lemma':['прийти'],'POS':['VERB']},
            'a':{'POS':['NOUN','NPRO'],'cases':['nom']}}},
        'output_kind':'CANDIDATE_GRAPH',
        'output':{'nodes':[{'id':'p','kind':'PREDICATE','anchors':['p']},
                           {'id':'a','kind':'ENTITY','anchors':['a']}],
                  'edges':[{'kind':'ARGUMENT','from':'p','to':'a','role_id':'SUBJECT'}]},
        'constraints':[{'kind':'BEFORE','left':'a','right':'p'}],
        'priority':0,'min_evidence':2,'coverage_tag':'TEST_ONLY'}
    senses=[('MIG_ARRIVE','прийти','VERB',[role('SUBJECT')],'EVENT')]
    if ambiguous: senses.append(('MIG_ARRIVE_OTHER','прийти','VERB',[role('SUBJECT')],'EVENT'))
    known=test_release(session.core,senses,[rule])
    m=deepcopy(known.manifest)
    for bucket in m['entries']:
        if bucket['kind'] in {'R-S','R-V','TemplateMap'}: bucket['entries']=[]
    return _resign(m),known


def _seed_native(session, *, oid='O1', version=1, old=None):
    if old is None: old,_=_releases(session)
    binding=InterpretationRunBinding(session.store._journal)
    state,report=interpret_full('Иван пришёл.',None,NativeSelector(),session.store,binding,
        release=old,version=version,observation_id=oid,morph=MorphProvider(),
        raw_input={'request_kind':'ASSERTION'},run_id='migration:seed:'+digest([oid,version]))
    if report.terminal!='APPLIED':
        raise RuntimeError('MIGRATION_FIXTURE_NOT_MATERIALIZED:'+report.terminal)
    session.sources[oid]=[report.observation_id,version]
    supports=[sid for sid,s in session.store.ledger.data['supports'].items()
              if s.get('source_tag')==[report.observation_id,version]]
    return binding,report.observation_id,supports


def _links(session, oid, version, supports):
    nodes=session.store.ledger.data['nodes']
    return [{'source_t_ref':nodes[session.store.ledger.data['supports'][sid]['conclusion_ref']]['template_ref'],
             'canonical_t_ref':'fixture:T:MIG_ARRIVE','evidence_refs':[sid]} for sid in supports]


def _version_fixture(session, oid, versions):
    from tools.formalizer_v7_extended_binding import ATOM
    all_supports=[]
    for version in versions:
        batch='version:'+oid+':'+str(version)
        _,sids,_=session.prepare(batch,[ATOM]);ops,decision,_=session.batches[batch]
        # T5's actual marker and support tags refer to the requested version;
        # a discarded provisional fixture plan is made terminal before the
        # replacement journal record, so it cannot block the global head.
        from ah.formalizer.store_interface import TerminalOutcome
        session.store.append_terminal('batch:'+batch,TerminalOutcome.STALE_SUPERSEDED,'fixture retag before execution')
        tag=[oid,version]
        adjusted=tuple(replace(op,payload={**op.payload,'source_tag':tag})
            if 'source_tag' in op.payload else op for op in ops)
        fresh=batch+':retag'
        holder=InterpretationRunBinding(session.store._journal).holder(oid,version)
        decision=journal_plan(session.store,adjusted,run_id=holder or 'version-run:'+digest(tag),
            observation_id=oid,version=version,batch_hash=fresh,fragments=decision.committed)
        session.batches[fresh]=(adjusted,decision,tag);session.commit(fresh)
        all_supports.extend(sids)
    return all_supports


def _actual_graph_links(session):
    # LinkOpenTemplate lives in the formalizer audit layer. Actual AH Link
    # records are inspected separately so an accidentally emitted inferential
    # edge cannot be hidden by reporting a constant empty alias list.
    return [asdict(link) for link in session.store._store.links()]


def _migration_view(session, old_supports, baseline, retirement_checkpoint=None):
    L=session.store.ledger
    old=[L.data['supports'][sid] for sid in old_supports]
    retired={e['support_id'] for e in L.data['events'] if e['type']=='SUPPORT_RETRACTED'
             and e['support_id'] in old_supports}
    old_queries=[]
    for sid in old_supports:
        support=L.data['supports'][sid];uid=support['conclusion_ref'];node=L.data['nodes'][uid]
        old_queries.append({'support_id':sid,'old_node_ref':uid,'old_template_ref':node['template_ref'],
            'own_path_live':sid in L.paths(),
            'occurrence_answer':session.store.prove_node(uid),
            'template_answer':session.store.query_template(node['template_ref'],node['proposition']['actants'])})
    audit_links=deepcopy(list(L.data['open_template_links'].values()))
    known_queries=[{'template_ref':link['canonical_t_ref'],
        'answers':[session.store.query_template(link['canonical_t_ref'],n.get('proposition',{}).get('actants',{}))
            for n in L.data['nodes'].values() if n.get('template_ref')==link['canonical_t_ref']]}
        for link in audit_links]
    L=session.store.ledger;old=[L.data['supports'][sid] for sid in old_supports]
    session.api.update({'AHStoreAdapter.prove_node / query_template old occurrence and old T',
                        'AHStore.links inferential edge observation'})
    def immutable(s): return {k:v for k,v in s.items() if k!='status'}
    return {'migration':{
        'old_supports_live':bool(old) and all(s['status']=='LIVE' for s in old),
        'old_records_rewritten':any(immutable(s)!=immutable(baseline[s['record_id']]) for s in old),
        # A retired occurrence must not become provable via a new known path.
        'alias_reasoner_enabled':any(not probe['own_path_live'] and (
            probe['occurrence_answer']['answer'] in {'YES','NO'}
            or probe['template_answer']['answer'] in {'YES','NO'}) for probe in old_queries),
        'old_supports_resurrected':any(s['status']=='LIVE' and (s['record_id'] in retired
            or (retirement_checkpoint or {}).get(s['record_id'],{}).get('status','LIVE')!='LIVE') for s in old),
        'retired_old_support_ids':sorted(retired),
        'retirement_checkpoint':deepcopy(retirement_checkpoint),
        'old_query_probes':old_queries,'known_query_probes':known_queries,
        'applied':bool(L.data['open_template_links']),
        'link_records':audit_links},
        'aliases':_actual_graph_links(session),
        'store':{'fact_count':len(L.f_visible()),'marker_count':len(L.data['markers'])}}


def _execute_migration(session,p):
    old,known=_releases(session,ambiguous=p.get('failure')=='AMBIGUOUS_SENSE')
    binding,oid,old_supports=_seed_native(session,oid=p['source'],version=p['from_version'],old=old)
    baseline=deepcopy(session.store.ledger.data['supports'])
    links=_links(session,oid,p['from_version'],old_supports)
    failure=p.get('failure','NONE');original_commit=session.store.commit_transaction
    original_finish=session.store._finish_batch
    codes=[]
    if failure=='BEFORE_STORE_COMMIT':
        session.store.commit_transaction=lambda *a,**k: (_ for _ in ()).throw(CrashStop('before store transaction'))
    elif failure=='AFTER_STORE_BEFORE_TERMINAL':
        session.store._finish_batch=lambda *a,**k: (_ for _ in ()).throw(CrashStop('after atomic store decision'))
    elif failure=='STALE_INPUT':
        # Corrupt the in-memory frozen-input cache; _refresh checks its value
        # against the immutable durable run_bind before any new interpretation.
        binding._inputs[(oid,p['from_version'])]['text']='a different frozen source'
    try:
        selector=NativeSelector(unresolved=failure=='AMBIGUOUS_SENSE')
        _,report=reinterpret_observation(session.store,binding,selector,known,
            observation_id=oid,previous_version=p['from_version'],target_version=p['to_version'],
            trigger_ref='oracle:declared-release-migration',open_template_links=links,
            morph=MorphProvider(),run_id='migration:replacement')
    except CrashStop:
        report=None
    except (RuntimeError,ValueError) as exc:
        if failure!='STALE_INPUT': raise
        codes=[str(exc).split(':',1)[0]];report=None
    finally:
        session.store.commit_transaction=original_commit;session.store._finish_batch=original_finish
    if failure=='AFTER_STORE_BEFORE_TERMINAL': session.store.recover_from_head()
    retirement_checkpoint={sid:deepcopy(session.store.ledger.data['supports'][sid]) for sid in old_supports}
    if failure=='AFTER_SUCCESS_RETRACT_V2':
        session.store.retract_observation(oid,p['to_version'],trigger_ref='oracle:retract-migrated-version')
    session.api.update({'migration.reinterpret_observation / v7_pipeline.interpret_full',
        'AHStoreAdapter.commit_transaction / SUPERSEDE_VERSION / LINK_OPEN_TEMPLATE'})
    result=_migration_view(session,old_supports,baseline,retirement_checkpoint)
    result['diagnostics']={'codes':codes}
    result['migration']['terminal']=getattr(report,'terminal',None)
    return result


def _bulk(session,p):
    old,known=_releases(session,ambiguous=True)
    target=p['target_versions'];items=[]
    for oid in p['observations']:
        _seed_native(session,oid=oid,version=target[oid]-1,old=old)
        items.append({'observation_id':oid,'previous_version':target[oid]-1,
                      'input_changes':{'context_snapshot':{'hash':p['frozen_context_hash']}}})
    binding=InterpretationRunBinding(session.store._journal)
    if p.get('boundary')=='BEFORE_PLAN':
        # Nothing migration-specific is durable at this stop. A new binding
        # then reconstructs only the existing source observations.
        try: raise CrashStop('before durable migration plan')
        except CrashStop: binding=InterpretationRunBinding(session.store._journal)
    plan=plan_mass_migration(session.store,binding,known,trigger_ref='oracle:bulk-resource-release',items=items)
    if p.get('boundary')=='AFTER_RESERVE': binding=InterpretationRunBinding(session.store._journal)
    recorded_calls=[]
    class LockProbeSelector(NativeSelector):
        def select(self,prompt):
            from ah.core.journal import _LOCAL
            recorded_calls.append(bool(getattr(_LOCAL,'held',{}).get(session.store._journal._key)))
            return super().select(prompt)
    selector=LockProbeSelector();original_append=session.store._journal.append
    stop=p.get('boundary');fired=False;crash_checkpoint=None
    def receipt_checkpoint(payload):
        report=payload['report'];batch_hash=report.get('batch_hash')
        marker={'observation_id':payload['observation_id'],
                'interpretation_version':payload['target_version']}
        ledger=session.store.ledger
        checkpoint={'observation_id':payload['observation_id'],
            'target_version':payload['target_version'],'batch_hash':batch_hash,
            'marker_hash':ledger.data['markers'].get(digest(marker)),
            'commit_decision':deepcopy(ledger.data['decisions'].get(batch_hash)),
            'terminal':deepcopy(session.store._terminal_records().get('batch:'+str(batch_hash))),
            'receipt_durable':any(r['payload'].get('kind')=='MIGRATION_ITEM_RESULT'
                and r['payload'].get('migration_id')==plan['migration_id']
                and r['payload'].get('observation_id')==payload['observation_id']
                for r in session.store._journal.scan_unprocessed(0))}
        if (report.get('terminal')!='APPLIED' or checkpoint['marker_hash']!=batch_hash
                or not checkpoint['commit_decision']
                or not checkpoint['commit_decision'].get('committed')):
            raise RuntimeError('MIGRATION_CRASH_FIXTURE_HAS_NO_ITEM_STORE_COMMIT')
        return checkpoint
    def interrupted_append(channel,payload,run_id=''):
        nonlocal fired,crash_checkpoint
        is_receipt=payload.get('kind')=='MIGRATION_ITEM_RESULT'
        if is_receipt and not fired and stop=='AFTER_ITEM_COMMIT_BEFORE_RECEIPT':
            crash_checkpoint=receipt_checkpoint(payload)
            fired=True;raise CrashStop('item committed before receipt')
        seq=original_append(channel,payload,run_id=run_id)
        if is_receipt and not fired and stop=='AFTER_RECEIPT':
            crash_checkpoint=receipt_checkpoint(payload)
            fired=True;raise CrashStop('after durable item receipt')
        return seq
    if stop in {'AFTER_ITEM_COMMIT_BEFORE_RECEIPT','AFTER_RECEIPT'}:
        session.store._journal.append=interrupted_append
    try:
        resume_mass_migration(session.store,binding,selector,known,migration_id=plan['migration_id'],morph=MorphProvider())
    except CrashStop: pass
    finally: session.store._journal.append=original_append
    # New binding instances reconstruct durable target-version reservations;
    # two resumptions establish receipt and version idempotence after the stop.
    for _ in range(2):
        binding=InterpretationRunBinding(session.store._journal)
        resume_mass_migration(session.store,binding,selector,known,migration_id=plan['migration_id'],morph=MorphProvider())
    records=[r['payload'] for r in session.store._journal.scan_unprocessed(0)]
    receipts=[r for r in records if r.get('kind')=='MIGRATION_ITEM_RESULT']
    target_bindings=[(i['observation_id'],i['target_version'],binding.holder(i['observation_id'],i['target_version'])) for i in plan['items']]
    bound_targets=[(r['observation_id'],r['version']) for r in records if r.get('kind')=='run_bind'
        and any((r['observation_id'],r['version'])==(o,v) for o,v,_ in target_bindings)]
    session.api.update({'migration.plan_mass_migration','migration.resume_mass_migration',
        'InterpretationRunBinding durable migration reservations'})
    return {'migration':{'item_order':[r['observation_id'] for r in receipts],
        'target_versions_reused':len(bound_targets)!=len(set(bound_targets)),
        'reserved_target_versions':{o:v for o,v,owner in target_bindings if owner is not None and max(binding.versions(o))==v},
        'item_receipts_unique':len(receipts)==len({r['observation_id'] for r in receipts}),
        'provider_holds_writer_lock':any(recorded_calls),
        'provider_lock_observations':recorded_calls,
        'crash_checkpoint':crash_checkpoint,
        'target_commit_decisions':{i['observation_id']:deepcopy(next((D
            for D in session.store.ledger.data['decisions'].values()
            if D['marker']=={'observation_id':i['observation_id'],
                'interpretation_version':i['target_version']}),None)) for i in plan['items']},
        'atomicity':'PER_OBSERVATION', 'plan':plan,'receipts':receipts}}


def migration_action(session,action,p):
    if action=='execute_migration': return _execute_migration(session,p)
    if action=='recover_bulk_migration': return _bulk(session,p)
    if action=='plan_migration':
        old,known=_releases(session)
        binding,oid,sids=_seed_native(session,old=old)
        links=_links(session,oid,1,sids);bad=p['invalid_condition']
        item={'observation_id':oid,'previous_version':1,'open_template_links':links}
        if bad=='name_similarity_only':item['open_template_links'][0]['evidence_refs']=[]
        elif bad=='dead_equivalence_support': session.store.retract(sids[0],reason='fixture declared equivalence retraction')
        elif bad=='changed_frozen_source_text':binding._inputs[(oid,1)]['text']='changed bytes'
        elif bad=='reused_target_version':
            reserved_input=binding.input_snapshot(oid,1)
            reserved_input.update(interpretation_version=2,trigger_ref='oracle:foreign-reserved-target')
            binding.acquire('foreign-target-owner',oid,2,
                snapshot_hash=digest([reserved_input,known.sha256]),snapshot_data=reserved_input)
            # A caller cannot overwrite/reuse that already bound target.
            try: reinterpret_observation(session.store,binding,NativeSelector(),known,
                observation_id=oid,previous_version=1,target_version=2,
                trigger_ref='oracle:invalid-migration',open_template_links=links,morph=MorphProvider())
            except ValueError as exc:codes=[str(exc)]
            else:codes=[]
            session.api.add('migration.reinterpret_observation target replay mismatch')
            return {'migration':{'applied':bool(session.store.ledger.data['open_template_links'])},'aliases':_actual_graph_links(session),'diagnostics':{'codes':codes}}
        try: plan_mass_migration(session.store,binding,known,trigger_ref='oracle:invalid-migration',items=[item])
        except (RuntimeError,ValueError) as exc:codes=[str(exc)]
        else:codes=[]
        session.api.add('migration.plan_mass_migration validation')
        return {'migration':{'applied':bool(session.store.ledger.data['open_template_links'])},'aliases':_actual_graph_links(session),'diagnostics':{'codes':codes}}
    if action=='supersede_version':
        _version_fixture(session,p['observation'],p['versions'])
        session.store.supersede_observation(p['observation'],p['supersede'],trigger_ref='oracle:version-supersede')
        grouped={}
        for support in session.store.ledger.data['supports'].values():
            oid,version=support['source_tag'];grouped[oid+':v'+str(version)]=support['status']
        session.api.add('AHStoreAdapter.supersede_observation exact source tag')
        return {'supports':{'by_tag':grouped}}
    if action in {'change_source','change_declared_read'}:
        old,known=_releases(session);binding,oid,sids=_seed_native(session,old=known)
        before=len(binding.versions(oid));declared=p.get('declared',True);report=None;codes=[]
        try:
            _,report=reinterpret_observation(session.store,binding,NativeSelector(),known,
                observation_id=oid,previous_version=1,target_version=p['new_version'],
                trigger_ref='oracle:declared-read' if declared else '',
                input_changes={'declared_reads':{p.get('read','context:1'):[]}},morph=MorphProvider())
        except ValueError as exc:
            if declared:raise
            codes=[str(exc)]
        after=len(binding.versions(oid));session.api.add('migration.reinterpret_observation declared input change')
        return {'execution':{'recomputed':after>before},
            'identity':{'version_increment':after-before,'interpretation_version':max(binding.versions(oid))},
            'decision':{'outcome':'RESOLVED' if report and report.committed_fragments else 'UNRESOLVED'},
            'diagnostics':{'codes':codes}}
    if action=='change_declared_resource':
        m=deepcopy(session.release.manifest)
        bucket=next(b for b in m['entries'] if b['kind']=='IncompatibilityRules')
        bucket['version']='test-v'+str(p['version'])
        locative=next(spec for (predicate,roles),spec in session.templates.items() if predicate=='LOCATIVE')
        rule={'rule_id':p['rule'],'kind':'ROLE_EXCLUSIVE','sense_id':locative['sense_id'],
              'role_id':locative['roles']['LOCATION'],'key_roles':[locative['roles']['THEME']]}
        bucket['entries']=[rule];m['dependency_versions']['IncompatibilityRules']=bucket['version']
        release=_resign(m);before={sid:s['status'] for sid,s in session.store.ledger.data['supports'].items()}
        session.store.rescan_conflicts(release,trigger_ref='oracle:declared-incompatibility-release')
        session.release=release;result=session.snapshot()
        result['store']['auto_retraction_count']=sum(session.store.ledger.data['supports'][sid]['status']!=v for sid,v in before.items())
        session.api.add('AHStoreAdapter.rescan_conflicts / signed IncompatibilityRules release')
        return result
    if action=='execute_identical_prompts':
        sends=[];log=ProviderCallLog(session.store._journal)
        provider=ProviderAdapter('TEST_ONLY',frozenset({'select'}),
            transport=lambda prompt: sends.append(prompt) or '{}',log=log,budget=BudgetSnapshot(token_limit=100000))
        provider.start_run(p['run_id'])
        for ordinal in p['ordinals']:provider.select(p['prompt'],p['run_id'],ordinal=ordinal)
        rows=[r['payload'] for r in session.store._journal.scan_unprocessed(0) if r['payload'].get('kind')=='prov_call' and r['payload'].get('state')=='RECEIVED']
        session.api.add('ProviderAdapter.select / ProviderCallLog ordinal identity')
        return {'provider':{'send_count':len(sends),'ordinals':[r['ordinal'] for r in rows],
            'cross_ordinal_cache_hits':len(p['ordinals'])-len(sends)}}
    if action=='rerun_same_pair':
        from ah.formalizer.v7_pipeline import interpret_full
        binding=InterpretationRunBinding(session.store._journal);oid='oracle:replay-pair'
        raw={'text':'Иван пришёл.','observation_id':oid,'interpretation_version':1,'context_facts':[],'rx_reads':{}}
        snapshot={'snapshot_id':session.release.sha256,'release_version':session.release.manifest['version']}
        binding.acquire(p['canonical_run_id'],oid,1,snapshot_hash=digest([raw,snapshot]),snapshot_data=raw)
        session.store._journal.append('resolution_log',{'kind':'RESOLUTION','observation_id':oid,'version':1,'outcomes':{'slot':p['recorded_outcome']}})
        if p['materialization_marker']:
            _version_fixture(session,oid,[1])
        before=len([r for r in session.store._journal.scan_unprocessed(0) if r['payload'].get('kind')=='BATCH'])
        class NoSend(NativeSelector):
            calls=0
            def select(self,prompt):self.calls+=1;return p['new_provider_answer']
        selector=NoSend()
        _,report=interpret_full(raw['text'],None,selector,session.store,binding,release=session.release,
            observation_id=oid,version=1,run_id=p['new_run_id'],raw_input={'rx_reads':{}})
        after=len([r for r in session.store._journal.scan_unprocessed(0) if r['payload'].get('kind')=='BATCH'])
        session.api.add('v7_pipeline.interpret_full / immutable InterpretationRunBinding')
        return {'run':{'canonical_run_id':binding.holder(oid,1),
            'new_run_mode':'INVESTIGATION_ONLY' if not report.binding_ok else 'CANONICAL',
            'new_t5_batch_count':after-before},'provider':{'new_canonical_send_count':selector.calls}}
    if action=='t6_with_marker':
        from tools.formalizer_v7_extended_binding import ATOM
        session.prepare(p['marker_hash'],[ATOM]);session.commit(p['marker_hash'])
        ops,old,tag=session.batches[p['marker_hash']]
        decision=replace(old,batch_hash=p['caller_hash']);before=deepcopy(session.store.ledger.data)
        if p['caller_hash']!=p['marker_hash']:
            from ah.formalizer.store_interface import JournalRecord
            payload={'kind':'BATCH','batch_hash':decision.batch_hash,'ops':[asdict(o) for o in ops],
                'decision':{**asdict(decision),'outcome':decision.outcome.value}}
            session.store.append_journal('observation',JournalRecord('observation',decision.run_id,payload))
        try: result=session.store.commit_transaction(ops,decision.marker,decision);codes=[]
        except JournalIntegrityError: result=None;codes=['INTEGRITY_ERROR']
        session.api.add('AHStoreAdapter.commit_transaction committed marker hash guard')
        return {'store':{'repeated_operation_count':len(result.applied_uids) if result is not None else 0},
            'journal':{'new_fact_count':len(session.store.ledger.data['nodes'])-len(before['nodes'])},
            'diagnostics':{'codes':codes}}
    if action=='reconcile':
        for text in p['markers']:
            oid,version=text.rsplit(':v',1);_version_fixture(session,oid,[int(version)])
        oid,version=p['declared_committed_pair'].rsplit(':v',1);codes=[];enabled=True
        try:session.store.reconcile_committed_pairs([MaterializationMarker(oid,int(version))])
        except JournalIntegrityError:codes=['INTEGRITY_ERROR'];enabled=False
        session.api.add('AHStoreAdapter.reconcile_committed_pairs exact pair integrity')
        return {'diagnostics':{'codes':codes},'service':{'factual_reads_enabled':enabled}}
    raise ValueError('UNSUPPORTED_MIGRATION_ACTION:'+action)
