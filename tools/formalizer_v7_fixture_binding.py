"""Independent fixed stimuli for determinism and execution coverage.

These fixtures author inputs and scripted selector bytes, never inspect checks or
copy a previous result. Every comparison checkpoint is recomputed by project APIs.
"""
from copy import deepcopy
from dataclasses import asdict
import json
from ah.formalizer.canonical_ledger import digest

FIXTURE_ACTIONS={'run_fixed_fixture','coverage_report'}


def fixture_action(session,action,payload):
    if action=='coverage_report':
        from ah.formalizer.resources.coverage import summarize_outcomes
        report=summarize_outcomes(payload['outcomes'],surface_only=payload['surface_only'])
        session.api.add('resources.coverage.summarize_outcomes semantic vs surface-only counts')
        return {'coverage':report,'gates':{'G5':{'pass':False,'evidence_status':'NOT_EVALUATED','reason':'NO_REVIEWED_EXECUTION_EVIDENCE'}}}
    if action!='run_fixed_fixture':raise ValueError('UNBOUND_FIXTURE_ACTION:'+action)
    if payload['fixture']!='SIMPLE_LOCATIVE':raise ValueError('UNKNOWN_FIXED_FIXTURE')
    from ah.formalizer.pipeline import t0,srl,t1,t2,td,t3,t4
    from ah.formalizer.seal import structural_seal
    from ah.formalizer.selection_protocol import Relation,DecisionSchema
    from ah.formalizer.provider_adapter import ProviderAdapter,BudgetSnapshot
    from ah.formalizer.provider_call_log import ProviderCallLog
    from ah.formalizer.state import ConstraintEdge
    # A public data-only script selects one registered ID in a closed fixture.
    # The real ProviderAdapter still writes/replays request and reply bytes.
    script=json.dumps({'outcome':'ONE_SELECTED','selected':['LOCATIVE']})
    transport_calls=[]
    def transport(prompt):transport_calls.append(prompt);return script
    adapter=ProviderAdapter('FIXED_SCRIPT_ONLY',frozenset({'select'}),transport,
        model_key='independently-authored-fixture',log=ProviderCallLog(session.store._journal),
        budget=BudgetSnapshot(token_limit=32768))
    mutation=payload.get('mutation')
    run_id='fixture:SIMPLE_LOCATIVE:'+('BASE' if mutation in {None,'replay_provider_bytes'} else mutation)
    class Selector:
        def select(self,prompt):return adapter.select(prompt,run_id)
    relation_rows=[('LOCATIVE','Location'),('HAVE','Possession'),('PART_WHOLE','Part whole')]
    mutation=payload.get('mutation')
    if mutation=='R_entries_order':relation_rows.reverse()
    schema=DecisionSchema('FIXTURE_ONLY-v1',{key:Relation(key,label,2,('SUBJECT','LOCATION'),label)
        for key,label in relation_rows})
    state=t0('Книга была на столе. Книга была на полке.');state.source_uid='fixture:SIMPLE_LOCATIVE'
    srl(state);t1(state);t2(state);td(state)
    # Source and constraint permutations carry the same declared inputs. The
    # real solver/prompt machinery receives the changed iteration order.
    frame_keys=[f.frame_id+'|predicate_value' for f in state.frames]
    if len(frame_keys)<2:raise RuntimeError('FIXTURE_PRECONDITION: two locative frames required')
    state.constraints=[ConstraintEdge(frame_keys[0],frame_keys[1],frozenset({('HAVE','PART_WHOLE')})),
                       ConstraintEdge(frame_keys[0],frame_keys[1],frozenset({('PART_WHOLE','HAVE')}))]
    if mutation=='constraint_iteration_order':state.constraints.reverse()
    structural_seal(state);adapter.start_run(run_id)
    t3(state,schema,Selector())
    from ah.formalizer.t3_sources import build_source_traces
    # Perturb actual declared T3 source inputs, not an already-produced trace.
    # Each collection is an independent source of the same finite value set.
    source_inputs=[('schema_candidates',['LOCATIVE','HAVE','PART_WHOLE']),
                   ('rs_senses',['LOCATIVE','HAVE','PART_WHOLE']),
                   ('rx3_prior',['LOCATIVE','HAVE']),
                   ('wc_reads',['LOCATIVE','PART_WHOLE']),('open_candidate',None)]
    if mutation=='source_iteration_order':
        source_inputs=[(key,list(reversed(values)) if isinstance(values,list) else values)
                       for key,values in reversed(source_inputs)]
    for decision in state.decisions.values():
        if decision.slot_id=='predicate_value':
            decision.source_traces=build_source_traces(decision.frame_id,decision.slot_id,
                **dict(source_inputs),rx3_applicable=True,wc_applicable=True)
    t4(state,schema)
    if mutation=='replay_provider_bytes' and transport_calls:
        raise RuntimeError('INTEGRITY_ERROR: provider replay used transport')
    candidate_ids=sorted({cid for d in state.decisions.values() for cid in d.candidates})
    decisions=sorted(state.decisions)
    diagnostics=sorted([{'code':d.code,'location':d.detail} for d in state.diagnostics],key=digest)
    semantic={'selected':{key:list(d.selected) for key,d in sorted(state.decisions.items())},
              'outcomes':{key:d.outcome for key,d in sorted(state.decisions.items())},
              'frames':sorted([asdict(f) for f in state.frames],key=digest),
              'source_traces':{k:[asdict(t) for t in d.source_traces] for k,d in sorted(state.decisions.items())}}
    session.api.add('pipeline T0/SRL/T1/T2/TD/seal/T3/T4 + ProviderAdapter durable byte replay')
    return {'decision':{'outcome':next((d.outcome for d in state.decisions.values() if d.slot_id=='predicate_value'),None)},
            'ir':{'candidate_ids':candidate_ids,'decision_ids':decisions},
            'state':{'semantic_digest':digest(semantic)},'diagnostics':{'located_multiset':diagnostics},
            'provider':{'transport_call_count':len(transport_calls),
                        'recorded_reply_refs':[r['payload']['id'] for r in session.store._journal.scan_unprocessed()
                            if r['payload'].get('kind')=='prov_call' and r['payload'].get('state')=='RECEIVED']}}
