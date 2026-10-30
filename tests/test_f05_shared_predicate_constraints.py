"""Common source pruning must see every use of a shared predicate occurrence."""
from itertools import permutations
from types import SimpleNamespace as NS
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.component_constraints import compatible_bundle


def frame(fid,token,role='SUBJECT',reading=None):
    sem={'proposed_roles':{token:role},'morph_bindings':{token:reading or {'pos':'NOUN','cases':['nom']}}}
    return FrameCandidate(fid,'FLAT','source',(),predicate_token_ref='p',argument_token_refs=(token,),semantic=sem)


def setup(monkeypatch,role='SUBJECT',reading=None):
    state=t0('source');region=NS(region_id='r')
    state.syntax_trace.append({'kind':'ESTABLISHED_PREDICATE_ROLE','region_ref':'r','task_scope':None,
        'predicate_ref':'p','token_ref':'a','role':role,'proof':{'id':'proof'},'reading':reading})
    monkeypatch.setattr('ah.formalizer.structural_tasks.licensed',lambda *a,**k:True)
    return state,region


def test_shared_predicate_keeps_disjoint_branch_participants_in_both_orders(monkeypatch):
    state,region=setup(monkeypatch)
    for bundle in permutations([frame('left','a'),frame('right','b')]):
        assert compatible_bundle(state,region,bundle)


def test_any_conflicting_use_cannot_be_hidden_by_last_frame(monkeypatch):
    state,region=setup(monkeypatch)
    for bundle in permutations([frame('good','a'),frame('bad','a','OBJECT')]):
        assert not compatible_bundle(state,region,bundle)
    assert not compatible_bundle(state,region,[frame('absent','b')])


def test_negative_role_and_whole_reading_apply_to_every_use(monkeypatch):
    state,region=setup(monkeypatch,'NO_DIRECT_ROLE')
    for bundle in permutations([frame('present','a'),frame('absent','b')]):
        assert not compatible_bundle(state,region,bundle)
    assert compatible_bundle(state,region,[frame('absent','b')])
    state,region=setup(monkeypatch,reading={'pos':'NOUN','cases':['nom']})
    for bundle in permutations([frame('good','a'),frame('bad','a',reading={'pos':'NOUN','cases':['dat']})]):
        assert not compatible_bundle(state,region,bundle)


def test_partial_reading_domain_preserves_role_in_all_uses(monkeypatch):
    from ah.formalizer.morphology_domain import clean
    state=t0('source');region=NS(region_id='r')
    row={'predicate_ref':'p','token_ref':'a','role':'SUBJECT',
        'alternatives':[{'reading':clean({'pos':'NOUN','cases':['nom']})}]}
    monkeypatch.setattr('ah.formalizer.partial_readings.domains',lambda *a:[row])
    monkeypatch.setattr('ah.formalizer.partial_readings.valid_domain',lambda *a:True)
    for bundle in permutations([frame('left','a'),frame('right','b')]):
        assert compatible_bundle(state,region,bundle)
    for bundle in permutations([frame('good','a'),frame('bad','a','OBJECT')]):
        assert not compatible_bundle(state,region,bundle)


def test_partial_structural_receipt_cannot_hide_open_parent_requirement(monkeypatch):
    from ah.formalizer.partial_composition import receipt,basis,validate
    monkeypatch.setattr('ah.formalizer.partial_readings.valid_domain',lambda *a:True)
    state=t0('source');frames=[frame('left','a'),frame('right','a')]
    tree={'choice_ref':'c','alternatives':[{'frame_ref':f.frame_id} for f in frames]}
    record=receipt(state,tree,frames,[{'domain_ref':'d'}],{'c':tree['alternatives']})
    original=basis(frames[0])
    frames[0].semantic['parent_slot_obligation']={'head_ref':'a','reason':'HEAD_CASE_UNKNOWN'}
    assert basis(frames[0])!=original
    with pytest.raises(ValueError,match='BASIS_CHANGED'):validate(state,record,frames)
    with pytest.raises(ValueError,match='UNCLOSED'):receipt(state,tree,frames,[{'domain_ref':'d'}],{'c':tree['alternatives']})


def test_partial_receipt_revalidates_owner_dependencies(monkeypatch):
    from ah.formalizer.partial_composition import receipt,validate
    monkeypatch.setattr('ah.formalizer.partial_readings.valid_domain',lambda *a:True)
    live={'value':True}
    monkeypatch.setattr('ah.formalizer.component_constraints.frame_hosts_live',lambda *a:live['value'])
    frames=[frame('left','a'),frame('right','a')];state=t0('source')
    tree={'choice_ref':'c','alternatives':[{'frame_ref':f.frame_id} for f in frames]}
    record=receipt(state,tree,frames,[{'domain_ref':'d'}],{'c':tree['alternatives']})
    live['value']=False
    with pytest.raises(ValueError,match='HOST_STALE'):validate(state,record,frames)
