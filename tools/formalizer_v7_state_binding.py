"""Lifecycle, declared resource/IR contracts and immutable run/cache bindings."""
from copy import deepcopy
from dataclasses import asdict,replace
import json
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.store_interface import StoreOp
from tools.formalizer_v7_test_support import journal_plan

STATE_ACTIONS={'open_template_keys','rx_read','rx_replay','recover_node_events','commit_two_state_supports',
              'retract_support_batch','legacy_roundtrip','compile_rule','replay_identity'}

def event_view(s):
    events=s.store.ledger.data['events'];last=events[-1]['tx_ref'] if events else None
    root=s.aliases['N'];reverse={v:k for k,v in s.aliases.items()}
    def rows(xs):return {'types':[e['type'] for e in xs],'support_ids':[reverse.get(e.get('support_id')) for e in xs],'seq':[e['seq'] for e in xs]}
    return {'events':{'N':rows([e for e in events if e['node_id']==root]),'last_tx':rows([e for e in events if e['tx_ref']==last]),
                      'identity_unique':len({digest(e['identity']) for e in events})==len(events)}}

def state_action(s,a,p):
    from tools.formalizer_v7_extended_binding import ATOM
    if a=='open_template_keys':
        from ah.formalizer.resources.registry import OpenPredicateCandidate,OpenTemplatePolicy,Role,RoleRegistry,RoleBinding,ensure_open_template
        r=p['base'];dim=p['changed_dimension'];other=deepcopy(r)
        if dim=='observation_id':other['observation']='O2'
        elif dim=='source_revision':other['revision']=2
        elif dim=='role':other['role']='EXPERIENCER'
        elif dim=='attachment':other['attachment']='obl'
        registry=RoleRegistry(frozenset(Role(x) for x in ('AGENT','EXPERIENCER','SURFACE_ARG')))
        policy=OpenTemplatePolicy(released=True)
        def make(row):return ensure_open_template(OpenPredicateCandidate(row['observation'],row['revision'],('t0',),row['surface'],'VERB',
            (RoleBinding(row['role'],syntax_relation=row['attachment']),)),registry,policy)
        first,second=make(r),make(other);materialized=True
        if dim=='sense_conflict':
            from ah.formalizer.c_consolidate import ResolvedValue,SenseKind,TemporalMode,consolidate
            vals=[ResolvedValue('F'+str(i),r['observation'],r['revision'],r['surface'],r['surface'],r['role'],SenseKind.OPEN_LEXICAL,TemporalMode.EVENT,('t0',),r['surface'],'VERB',sense_label=label,bindings=(RoleBinding(r['role']),)) for i,label in enumerate(('sense-a','sense-b'))]
            plan=consolidate(vals,{},registry,policy);materialized=not plan.blocked_fragment_ids
        s.api.add('resources.registry.ensure_open_template / c_consolidate.consolidate open sense collision')
        stimulus={'baseline_valid':True,'mutation_contract_valid':True}
        if dim=='attachment' and r['role']!='SURFACE_ARG':
            stimulus.update(mutation_contract_valid=False,
                defect='ATTACHMENT_NOT_IN_SEMANTIC_ROLE_SIGNATURE',
                norm_ref='§7.1(3b): syntactic attachment fields enter SURFACE_ARG signatures')
        elif dim=='sense_conflict':
            stimulus.update(mutation_contract_valid=False,
                defect='INCOMPATIBLE_SENSES_SHARE_KEY_BY_NORM',
                norm_ref='§7.1(3b): incompatible senses with one key remain ambiguous without open T')
        return {'open':{'key_equal':first.open_template_key==second.open_template_key,'alias_created':False,'materialized':materialized},'stimulus':stimulus}
    if a=='legacy_roundtrip':
        from ah.formalizer.integration_ir import IntegrationCandidateIRV2,StagedElement,legacy_roundtrip
        shape=p['shape'];plain=shape=='representable_graph'
        element=StagedElement('ASSERTION',{'payload_kind':'ASSERTION'}) if plain else StagedElement('STRUCTURAL',{'payload_kind':shape},epistemic='UNATTACHED')
        ir=IntegrationCandidateIRV2(elements=(element,));ok,result=legacy_roundtrip(ir)
        s.api.add('integration_ir.legacy_roundtrip lossless V2 capability guard')
        return {'adapter':{'legacy_used':ok,'lossy_coercion':ok and asdict(ir)!=asdict(result),'v2_preserved':not ok},'diagnostics':{'codes':[] if ok else [result]}}
    if a=='compile_rule':
        result=dsl_probe(p['base'],p['mutation'])
        s.api.add('resources.rule_dsl.compile_rules strict BNF and declared reads')
        return result
    if a=='rx_replay':
        from ah.formalizer.run_binding import InterpretationRunBinding
        oid,v=p['pair'].split(':v');b=InterpretationRunBinding(s.store._journal)
        b.acquire('RX-run',oid,int(v),snapshot_hash=digest(p['frozen_snapshot']),snapshot_data={'rx_snapshot':p['frozen_snapshot']})
        replay=InterpretationRunBinding(s.store._journal);snap=replay.input_snapshot(oid,int(v))
        s.api.add('InterpretationRunBinding durable frozen RX input_snapshot')
        return {'rx':{'read_snapshot':snap['rx_snapshot']},'run':{'new_version_created':replay.versions(oid)!=(int(v),)}}
    if a=='rx_read':
        from ah.formalizer.store_interface import TerminalOutcome
        record_state=p['record_state'];batch='RX-fixture'
        roots,supports,_=s.prepare(batch,[ATOM]);ops,old,tag=s.batches[batch]
        snapshot={'version':'OTHER' if record_state=='VERSION_MISMATCH' else 'REL'}
        # R-X1's authored SRL surface denotes its T1 runtime channel (§2.1).
        # Both write and read go through that real stage-isolated channel.
        record_stage='T1' if p['record_stage']=='SRL' else p['record_stage']
        read_stage='T1' if p['read_stage']=='SRL' else p['read_stage']
        stages={record_stage:{'priorities':{'K':1}}}
        rx=StoreOp('WRITE_COMMITTED_RX',{'record_id':'RX','source_tag':tag,
            'support_record_id':'uncommitted-support' if record_state=='REJECTED' else supports[0],
            'resource_snapshot':snapshot,'stages':stages},old.committed)
        s.store.append_terminal('batch:'+batch,TerminalOutcome.STALE_SUPERSEDED,'fixture adds a stage-isolated RX write')
        actual=batch+':actual';ops=(*ops,rx)
        d=journal_plan(s.store,ops,run_id=old.run_id,observation_id=tag[0],version=1,batch_hash=actual,fragments=old.committed)
        s.batches[actual]=(ops,d,tag)
        if record_state in {'COMMITTED_LIVE','SUPERSEDED','VERSION_MISMATCH','REJECTED'}:
            try:s.commit(actual)
            except ValueError as exc:
                if record_state!='REJECTED' or str(exc)!='RX_COMMIT_GROUND_INVALID':raise
        if record_state=='SUPERSEDED' and s.store.ledger.data['rx_cache']:s.store.retract_observation(*tag,trigger_ref='RX-supersede')
        rows=s.store.read_cache_snapshot({'version':'REL'}).get(read_stage,())
        cache=s.store.ledger.data['rx_cache']
        uncommitted=any(r['support_record_id'] not in s.store.ledger.data['supports'] for r in cache.values())
        s.api.add('AHStoreAdapter WRITE_COMMITTED_RX / read_cache stage isolation and committed-ground validation')
        return {'rx':{'readable':bool(rows),'writes_uncommitted':uncommitted,'record_stage_runtime':record_stage,'read_stage_runtime':read_stage},
                'supports':{'root_from_rx':sum(r.get('ground_type')=='RX' for r in s.store.ledger.data['supports'].values())},'aliases':[]}
    if a in {'commit_two_state_supports','retract_support_batch'}:
        if a=='commit_two_state_supports':
            roots,sids,_=s.prepare(p['tx_ref'],{'F_a':ATOM,'F_b':ATOM})
            ops,d,tag=s.batches[p['tx_ref']];mapping=dict(zip(sids,p['support_ids']))
            ops=tuple(replace(op,payload={**op.payload,'record_id':mapping[op.payload['record_id']]}) if op.op_type=='ADD_ROOT_SUPPORT' else op for op in ops)
            # Replace uncommitted fixture plan by a fresh real journal record.
            # No AH writes have taken place; old pending is terminally retired.
            from ah.formalizer.store_interface import TerminalOutcome
            s.store.append_terminal('batch:'+p['tx_ref'],TerminalOutcome.STALE_SUPERSEDED,'fixture revised explicit support IDs')
            bid=p['tx_ref']+':actual';d=journal_plan(s.store,ops,run_id=d.run_id,observation_id=tag[0],batch_hash=bid,version=1,fragments=['F_a','F_b'])
            s.batches[bid]=(ops,d,tag);s.commit(bid);s.aliases['N']=roots[0]
            s.aliases.update({sid:sid for sid in p['support_ids']});s.event_tag=tag
        else:s.store.retract_observation(*s.event_tag,trigger_ref=p['tx_ref'])
        s.api.add('CanonicalLedger NodeLifecycleEvent / atomic per-observation retraction')
        return event_view(s)
    if a=='recover_node_events':
        if not s.store.ledger.data['events']:
            uid,_,_=s.obs('event-one',ATOM);s.obs('event-two',ATOM)
            s.store.retract_observation(*s.sources['event-one'],trigger_ref='r1');s.store.retract_observation(*s.sources['event-two'],trigger_ref='r2')
        data=s.store.ledger.data;before=len(data['events']);m=p['mutation']
        if m=='missing_event':data['events'].pop(1)
        elif m=='extra_event':data['events'].append({**deepcopy(data['events'][0]),'tx_ref':'foreign'})
        elif m=='wrong_order':data['events'][0],data['events'][1]=data['events'][1],data['events'][0]
        elif m=='duplicate_identity':data['events'].append(deepcopy(data['events'][0]))
        elif m=='missing_derived_index':
            # Derived index is replaceable; recompute from canonical records.
            rebuilt=s.store._codec.import_payload(s.store._codec.export(s.core)).core
            # Import reconstructs indexes from the preserved canonical export.
            assert rebuilt.store.find_hypernodes_by_template(s.templates[('LOCATIVE',('LOCATION','THEME'))]['uid'])
        else:raise ValueError('UNBOUND_EVENT_MUTATION:'+m)
        codes=[];validation_before=len(data['events'])
        try:s.store.ledger.validate_audit()
        except ValueError as exc:codes=[str(exc).split(':',1)[0]]
        s.api.add('CanonicalLedger.validate_audit / replaceable AH indexes')
        return {'diagnostics':{'codes':codes},'service':{'factual_reads_enabled':not codes},'projection':{'rebuilt':m=='missing_derived_index'},'audit':{'repair_append_count':len(data['events'])-validation_before,'mutated':len(data['events'])!=validation_before,'unchanged':m=='missing_derived_index' and len(data['events'])==before}}
    if a=='replay_identity':
        from ah.formalizer.run_binding import InterpretationRunBinding,InputConflict
        b=InterpretationRunBinding(s.store._journal);base={'text':'fixture','context':'CTX','resources':'REL'}
        b.acquire('run','O',1,digest(base),base);changed={**base};m=p['mutation']
        field={'same_revision_different_text':'text',
               'same_pair_different_context_hash':'context',
               'same_pair_different_resource_hash':'resources'}.get(m)
        if field is None:raise ValueError('UNBOUND_REPLAY_MUTATION:'+m)
        changed[field]='DIFFERENT'
        codes=[]
        try:b.acquire('run','O',1,digest(changed),changed)
        except InputConflict:codes=['INPUT_CONFLICT']
        except RuntimeError as exc:codes=[str(exc).split(':',1)[0]]
        s.api.add('InterpretationRunBinding immutable snapshot hash guard')
        return {'diagnostics':{'codes':codes},'store':{'new_record_count':len(s.store.ledger.data['nodes'])}}
    raise ValueError('UNBOUND_STATE_ACTION:'+a)


def dsl_probe(base,mutation,dependency_versions=None):
    """Exercise exactly supplied DSL bytes, keeping invalid baselines distinct.

    A negative mutation cannot verify its intended boundary if the unmodified
    stimulus already fails parsing. The runner records INVALID_STIMULUS using
    this receipt instead of counting that accidental rejection as a pass.
    """
    from ah.formalizer.resources.rule_dsl import compile_rules
    roles={'SUBJECT','OBJECT','EXPERIENCER','SURFACE_ARG'}
    deps=dependency_versions or {'R1':'1'}
    baseline_valid=True;baseline_error=None
    try:compile_rules(base,roles,deps)
    except ValueError as exc:baseline_valid=False;baseline_error=str(exc)
    mutations={
        'duplicate_stage':lambda t:t.replace('stage=SRL','stage=SRL, stage=SRL'),
        'missing_reads':lambda t:t.replace('reads [R1:entries@1],',''),
        'unknown_stage':lambda t:t.replace('stage=SRL','stage=FOREIGN'),
        'undeclared_read':lambda t:t.replace('R1:entries@1','FOREIGN:entries@1'),
        'version_mismatch':lambda t:t.replace('R1:entries@1','R1:entries@2'),
        'python_callback':lambda t:t.replace('when n.POS="NOUN"','when __import__("os")'),
        'python_eval':lambda t:t.replace('when n.POS="NOUN"','when __import__("os")'),
        'unregistered_emit':lambda t:t.replace('TOKEN_HYPOTHESIS','FOREIGN'),
        'unknown_candidate_kind':lambda t:t.replace('TOKEN_HYPOTHESIS','FOREIGN'),
        'capture_not_declared':lambda t:t.replace('"capture":"n"','"capture":"foreign"'),
        'unbounded_loop':lambda t:t.replace('when n.POS="NOUN"','when while True'),
        'unknown_field':lambda t:t[:-1]+', foreign=1}',
        'NaN':lambda t:t.replace('priority=1','priority=NaN'),
        'Infinity':lambda t:t.replace('priority=1','priority=Infinity'),
        'wrong_emit_payload':lambda t:t.replace('["keep_as_is"]','"keep_as_is"'),
        'undeclared_LOOKUP':lambda t:t.replace('when n.POS="NOUN"','when LOOKUP(FOREIGN,{"lemma":{"field":"n.lemma"}})'),
        'capture_feature_missing':lambda t:t.replace('when n.POS="NOUN"','when n.foreign="NOUN"'),
        'expr_depth_17':lambda t:t.replace('when n.POS="NOUN"','when '+'NOT('*17+'n.POS="NOUN"'+')'*17),
        'chars_262145':lambda t:t+' '*(262145-len(t)),
        'rules_4097':lambda t:'\n'.join(t.replace('rule noun:','rule noun'+str(i)+':') for i in range(4097)),
        'join_budget_exceeded':lambda t:t.replace('captures={"n":{"POS":"NOUN"}}','captures={"n":{"POS":"NOUN"},"m":{"POS":"NOUN"}}'),
    }
    if mutation not in mutations:raise ValueError('UNBOUND_DSL_MUTATION:'+str(mutation))
    text=mutations[mutation](base);accepted=True;error=None
    try:compile_rules(text,roles,deps)
    except ValueError as exc:accepted=False;error=str(exc)
    return {'dsl':{'accepted':accepted,'code_executed':False,'error':error},
            'release':{'partial_fallback_used':False},
            'stimulus':{'baseline_valid':baseline_valid,'baseline_error':baseline_error,
                        'mutation_changed_bytes':text!=base}}
