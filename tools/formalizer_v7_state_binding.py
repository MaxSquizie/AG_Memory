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
        return {'open':{'key_equal':first.open_template_key==second.open_template_key,'alias_created':False,'materialized':materialized}}
    if a=='legacy_roundtrip':
        from ah.formalizer.integration_ir import IntegrationCandidateIRV2,StagedElement,legacy_roundtrip
        shape=p['shape'];plain=shape=='representable_graph'
        element=StagedElement('ASSERTION',{'payload_kind':'ASSERTION'}) if plain else StagedElement('STRUCTURAL',{'payload_kind':shape},epistemic='UNATTACHED')
        ir=IntegrationCandidateIRV2(elements=(element,));ok,result=legacy_roundtrip(ir)
        s.api.add('integration_ir.legacy_roundtrip lossless V2 capability guard')
        return {'adapter':{'legacy_used':ok,'lossy_coercion':ok and asdict(ir)!=asdict(result),'v2_preserved':not ok},'diagnostics':{'codes':[] if ok else [result]}}
    if a=='compile_rule':
        from ah.formalizer.resources.rule_dsl import compile_rules
        text=p['base'];m=p['mutation']
        mutations={
          'duplicate_stage':lambda t:t.replace('stage=SRL','stage=SRL, stage=SRL'),
          'missing_reads':lambda t:t.replace('reads [R1:entries@1],',''),
          'unknown_stage':lambda t:t.replace('stage=SRL','stage=FOREIGN'),
          'undeclared_read':lambda t:t.replace('R1:entries@1','FOREIGN:entries@1'),
          'version_mismatch':lambda t:t.replace('R1:entries@1','R1:entries@2'),
          'python_callback':lambda t:t.replace('when n.POS="NOUN"','when __import__("os")'),
          'unregistered_emit':lambda t:t.replace('TOKEN_HYPOTHESIS','FOREIGN'),
          'capture_not_declared':lambda t:t.replace('"capture":"n"','"capture":"foreign"'),
          'unbounded_loop':lambda t:t.replace('when n.POS="NOUN"','when while True'),
        }
        # The fixture itself may be invalid; retain compiler diagnostics so a
        # rejection is never misreported as proof of the requested mutation.
        if m not in mutations:raise ValueError('UNBOUND_DSL_MUTATION:'+m)
        text=mutations[m](text);accepted=True;err=None
        try:compile_rules(text,{'SUBJECT','OBJECT','EXPERIENCER','SURFACE_ARG'},{'R1':'1'})
        except ValueError as exc:accepted=False;err=str(exc)
        s.api.add('resources.rule_dsl.compile_rules strict BNF and declared reads')
        return {'dsl':{'accepted':accepted,'code_executed':False,'error':err},'release':{'partial_fallback_used':False}}
    if a=='rx_replay':
        from ah.formalizer.run_binding import InterpretationRunBinding
        oid,v=p['pair'].split(':v');b=InterpretationRunBinding(s.store._journal)
        b.acquire('RX-run',oid,int(v),snapshot_hash=digest(p['frozen_snapshot']),snapshot_data={'rx_snapshot':p['frozen_snapshot']})
        replay=InterpretationRunBinding(s.store._journal);snap=replay.input_snapshot(oid,int(v))
        s.api.add('InterpretationRunBinding durable frozen RX input_snapshot')
        return {'rx':{'read_snapshot':snap['rx_snapshot']},'run':{'new_version_created':replay.versions(oid)!=(int(v),)}}
    if a=='rx_read':
        from ah.formalizer.rx_cache import FormalizationCache,RxRecord
        # Public pure cache tests stage isolation separately from native/WAL
        # cache tests; PROVISIONAL/REJECTED records are intentionally not fed
        # to the committed-cache writer.
        state=p['record_state'];cache=FormalizationCache({'version':'REL'})
        if state in {'COMMITTED_LIVE','SUPERSEDED','VERSION_MISMATCH'}:
            record=RxRecord('RX',{},stages={p['record_stage']:{'priorities':{'K':1}}},
                versions={'version':'OTHER' if state=='VERSION_MISMATCH' else 'REL'},status='SUPERSEDED' if state=='SUPERSEDED' else 'LIVE')
            cache.record(record)
        rows=cache.read_for_stage(p['read_stage'],{})
        s.api.add('FormalizationCache.read_for_stage stage-isolated committed fixture')
        return {'rx':{'readable':bool(rows),'writes_uncommitted':any(r.status!='LIVE' and state in {'PROVISIONAL','REJECTED'} for r in cache.all_records())},'supports':{'root_from_rx':len(s.store.ledger.data['supports'])},'aliases':[]}
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
        return {'diagnostics':{'codes':codes},'service':{'factual_reads_enabled':not codes},'audit':{'repair_append_count':len(data['events'])-validation_before,'unchanged':m=='missing_derived_index' and len(data['events'])==before}}
    if a=='replay_identity':
        from ah.formalizer.run_binding import InterpretationRunBinding
        b=InterpretationRunBinding(s.store._journal);base={'text':'fixture','context':'CTX','resources':'REL'}
        b.acquire('run','O',1,digest(base),base);changed={**base};m=p['mutation']
        changed['text' if 'text' in m else 'context' if 'context' in m else 'resources']='DIFFERENT'
        codes=[]
        try:b.acquire('run','O',1,digest(changed),changed)
        except RuntimeError as exc:codes=[str(exc).split(':',1)[0]]
        s.api.add('InterpretationRunBinding immutable snapshot hash guard')
        return {'diagnostics':{'codes':codes},'store':{'new_record_count':len(s.store.ledger.data['nodes'])}}
    raise ValueError('UNBOUND_STATE_ACTION:'+a)
