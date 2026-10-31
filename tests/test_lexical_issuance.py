"""Historical origin/read checks; these do not establish semantic completeness."""
from copy import deepcopy,copy
import pytest
from test_structural_open_forest import native
from test_structural_lexical import lexical_answer
from ah.formalizer.lexical_issuance import inspect
from ah.formalizer.canonical_ledger import digest


@pytest.fixture
def issued(tmp_path,monkeypatch):
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),lexical_answer)
    return state,list(state.observation['structural_lexical_results'].values()),result


def test_native_both_sources_check_outside_session(issued):
    state,rows,result=issued
    for row in rows:
        for source in row['sources']:
            expected='PRODUCED_EVIDENCE_CURRENT'
            assert inspect(state,row,source)['status']==expected,(source['source'],inspect(state,row,source))
    assert not result['assertions']['ah']


@pytest.mark.parametrize('change',['frame','membership','condition','issuer','container_type'])
def test_recomputed_checksum_cannot_certify_changed_output(issued,change):
    state,rows,_=issued;row=deepcopy(rows[0]);source=row['sources'][0]
    if change=='frame':source['frames'][0]['anchor_span']='changed'
    elif change=='membership':source['bundles'][0]['frame_refs']=[]
    elif change=='condition':row['condition']=rows[1]['condition']
    elif change=='container_type':source['bundles'][0]['frame_refs']=tuple(source['bundles'][0]['frame_refs'])
    else:
        state=copy(state);del state._lexical_issuer
    row['receipt_digest']=digest({k:v for k,v in row.items() if k!='receipt_digest'})
    assert inspect(state,row,source)['status']=='STALE_EVIDENCE'


def test_local_probe_retirement_preserves_grammar_and_sibling(issued):
    state,rows,_=issued;row=rows[0];component=row['sources'][1]
    issued=state._lexical_issuer.get(component['issuance_ref'])
    assert issued['reads']['probes']
    ref=next(iter(issued['reads']['probes']))
    local=deepcopy(state)
    local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':ref})
    assert inspect(local,row,component)['status']=='STALE_EVIDENCE'
    assert inspect(local,row,row['sources'][0])['status']=='PRODUCED_EVIDENCE_CURRENT'
    assert all(inspect(local,rows[1],s)['status']!='STALE_EVIDENCE' for s in rows[1]['sources'])


def test_current_decision_override_wins_over_packet(issued):
    from ah.formalizer.structural_shells import evidence_state
    state,rows,_=issued;row=rows[0];source=row['sources'][1]
    manifest=state._lexical_issuer.get(source['issuance_ref'])
    local=evidence_state(state,{'evidence':manifest['evidence']})
    ref=next(iter(manifest['reads']['probes']))
    local.decisions[ref].selector_outcome='INSUFFICIENT_CONTEXT'
    assert inspect(local,row,source)['status']=='STALE_EVIDENCE'


def test_known_case_conflict_unknown_case_and_stale_evidence_are_distinct(issued):
    from ah.formalizer.state import FrameCandidate
    from ah.formalizer.lexical_issuance import slot_obligations,assess
    state,rows,_=issued;row=rows[0];source=row['sources'][0]
    frame=FrameCandidate(**deepcopy(source['frames'][0]))
    ref=frame.predicate_token_ref
    frame.semantic.setdefault('morph_bindings',{})[ref]={'cases':['nom']}
    slot={'head_ref':ref,'allowed_cases':['dat'],'output_sort':'PROPOSITION'}
    conflicts,unknown=slot_obligations(frame,slot)
    assert conflicts[0]['kind']=='HEAD_CASE_CONFLICT' and not unknown
    frame.semantic['morph_bindings'][ref]['cases']=[]
    conflicts,unknown=slot_obligations(frame,slot)
    assert not conflicts and unknown[0]['kind']=='HEAD_CASE_UNKNOWN'
    local=deepcopy(state)
    from ah.formalizer.structural_conditions import resolve
    local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED',
        'decision_ref':resolve(local,row['condition']).forest['membership']['decision_ref']})
    assert assess(local,row,source)['status']=='STALE_EVIDENCE'
    assert assess(local,row,source)['bundles']==[]


def test_lexical_compatibility_check_is_pure_and_not_a_completion_claim(issued):
    from ah.formalizer.state import FrameCandidate
    from ah.formalizer.composition_contracts import lexical_violations
    from ah.formalizer.lexical_issuance import assess
    state,rows,_=issued;row=rows[0];source=row['sources'][0]
    frame=FrameCandidate(**deepcopy(source['frames'][0]));before=deepcopy(frame)
    assert not lexical_violations([frame],row['token_refs'],boundaries=[frame])
    assert frame==before
    frame.semantic['component_scope_tree']={'operator':'NOT','operands':[{'frame_ref':frame.frame_id}]}
    assert lexical_violations([frame],row['token_refs'],boundaries=[frame])
    result=assess(state,row,source)
    assert result['status']=='PRODUCED_EVIDENCE_CURRENT'
    assert all(b['status']=='OPEN_REQUIREMENTS' for b in result['bundles'])
    assert not result['write_eligible'] and not source['producer_complete']


def test_native_cached_source_keeps_prior_context_obligation(tmp_path,monkeypatch):
    from ah.formalizer import structural_lexical
    original=structural_lexical.produce;repeated=[]
    def produce(*args,**kwargs):
        first=original(*args,**kwargs)
        if first and not repeated:
            second=original(*args,**kwargs);repeated.append(second)
            return second
        return first
    monkeypatch.setattr(structural_lexical,'produce',produce)
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),lexical_answer)
    row=repeated[0][0];source=row['sources'][1]
    record=state._lexical_issuer.get(source['issuance_ref'])
    assert record['reads']['contexts']
    assert inspect(state,row,source)['status']=='PRODUCED_EVIDENCE_CURRENT'


def test_missing_context_verifier_preserves_pending(tmp_path,monkeypatch):
    from ah.formalizer.attention_context import AttentionContextReader
    monkeypatch.setattr(AttentionContextReader,'validate_context_receipts',None)
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),lexical_answer)
    row=next(iter(state.observation['structural_lexical_results'].values()))
    assert inspect(state,row,row['sources'][0])['status']=='PRODUCED_EVIDENCE_CURRENT'
    assert inspect(state,row,row['sources'][1])['status']=='CONTEXT_REVALIDATION_PENDING'
