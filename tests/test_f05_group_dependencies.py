from types import SimpleNamespace as NS
from copy import deepcopy
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.nominal_reference_chain import finish
from ah.formalizer.nominal_group_dependency import ground,validate_member


def parent(mention,target):
    return {'interpretation_decision_ref':mention+'|referent','target_ref':target,
        'reference_kind':'ENTITY','premise_support_refs':[]}

def ref(mention):
    return {'frame_ref':'f','token_ref':mention,'mention_ref':mention,
        'decision_ref':mention+'|referent','basis_hash':'basis:'+mention}

def dep(state,members):
    return {'frame_ref':'f','role':'SUBJECT','source_tag':[state.source_uid,state.interpretation_version],
        'group_hash':'group','member_token_refs':members,'members':[{'reference':ref(m)} for m in members]}


def test_multi_parent_group_then_shared_dependency_and_downstream_chain():
    state=t0('source');state.observation['nominal_reference_bindings']={
        'a':parent('a','M:a'),'b':parent('b','M:b')}
    dependency=dep(state,['x','y'])
    pending={
        'last':({'interpretation_decision_ref':'last|referent'},ref('group')),
        'group':({'interpretation_decision_ref':'group|referent'},{'group_dependency':dependency}),
        'x':({'interpretation_decision_ref':'x|referent'},ref('a')),
        'y':({'interpretation_decision_ref':'y|referent'},ref('b'))}
    assert not finish(state,pending)
    bindings=state.observation['nominal_reference_bindings']
    assert bindings['last']['target_ref']==bindings['group']['target_ref']=='K:'+digest(['M:a','M:b'])
    assert bindings['last']['reference_kind']=='GROUP'
    anchor=bindings['group']['local_group_anchor']
    assert len(anchor['member_binding_refs'])==2
    assert ground(state,dependency)['local_group_anchor']==anchor
    state.observation['nominal_reference_bindings']['x']['target_ref']='M:changed'
    assert ground(state,dependency)['local_group_anchor']!=anchor


def test_group_cycle_missing_member_and_identity_collapse_do_not_ground():
    for mode in ['cycle','missing','collapse']:
        state=t0('source');state.observation['nominal_reference_bindings']={'b':parent('b','M:b')}
        pending={'group':({'interpretation_decision_ref':'group|referent'},{'group_dependency':dep(state,['a','b'])})}
        if mode=='cycle':pending['a']=({'interpretation_decision_ref':'a|referent'},ref('group'))
        if mode=='collapse':state.observation['nominal_reference_bindings']['a']=parent('a','M:b')
        assert 'group' in finish(state,pending)
        assert 'group' not in state.observation['nominal_reference_bindings']
        assert any('CYCLE' in d.code for d in state.diagnostics)==(mode=='cycle')


def test_member_durable_contract_checks_decision_hash_and_liveness():
    state=t0('source');state.observation['nominal_reference_bindings']={
        'a':parent('a','M:a'),'b':parent('b','M:b')}
    anchor=ground(state,dep(state,['a','b']))['local_group_anchor']
    member=anchor['member_anchors'][0];bid=anchor['member_binding_refs'][0]
    durable={**parent('a','M:a'),'binding_kind':'NOMINAL_REFERENCE','source_tag':anchor['source_tag'],
        'mention_ref':'a','binding_id':bid,'status':'LIVE'}
    live=NS(binding_live=lambda b,p:True)
    validate_member(member,bid,durable,anchor,live,set())
    for field,value in [('interpretation_decision_ref','other'),('target_ref','M:other'),('mention_ref','other')]:
        with pytest.raises(ValueError):validate_member(member,bid,{**durable,field:value},anchor,live,set())
    with pytest.raises(ValueError):validate_member(member,bid,durable,anchor,NS(binding_live=lambda b,p:False),set())


def test_nested_group_dependency_keeps_group_member_without_flattening():
    state=t0('source');state.observation['nominal_reference_bindings']={
        'a':parent('a','M:a'),'b':parent('b','M:b')}
    pending={
        'outer':({'interpretation_decision_ref':'outer|referent'},{'group_dependency':dep(state,['inner','a'])}),
        'inner':({'interpretation_decision_ref':'inner|referent'},{'group_dependency':dep(state,['a','b'])})}
    assert not finish(state,pending)
    bindings=state.observation['nominal_reference_bindings']
    inner=bindings['inner']['target_ref']
    assert bindings['outer']['member_refs']==sorted([inner,'M:a'])
    assert 'M:b' not in bindings['outer']['member_refs']
