import pytest
from ah.formalizer.composition_domains import DomainNetwork


def test_open_peer_does_not_disprove_candidate_and_extension_closes_obligation():
    graph=DomainNetwork({'owner':{'a':1,'b':2},'child':{}},open_domains={'child'})
    graph.connect('owner','child',lambda a,b:a==b,'SAME_ADDRESS')
    assert graph.propagate()
    assert set(graph.domains['owner'])=={'a','b'}
    assert graph.snapshot()['obligations']
    graph.extend('child',{'x':2},complete=True)
    assert graph.propagate()
    assert set(graph.domains['owner'])=={'b'}
    assert not graph.snapshot()['obligations']


def test_unknown_is_not_false_and_is_not_certified_support():
    graph=DomainNetwork({'a':{'x':1},'b':{'y':2}})
    graph.connect('a','b',lambda a,b:None,'UNEXPANDED_CONTENT')
    assert graph.propagate()
    assert len(graph.snapshot()['obligations'])==2
    assert graph.domains['a']=={'x':1}


def test_budget_preserves_unfinished_edge_and_candidate_set():
    graph=DomainNetwork({'a':{'x':1,'y':2},'b':{'z':2}})
    graph.connect('a','b',lambda a,b:a==b,'MATCH')
    calls=0
    def spend():
        nonlocal calls
        calls+=1
        if calls==2:raise RuntimeError('fuel')
    with pytest.raises(RuntimeError,match='fuel'):graph.propagate(spend)
    assert set(graph.domains['a'])=={'x','y'}
    assert not graph.snapshot()['propagation_complete']
    assert graph.propagate()
    assert graph.domains['a']=={'y':2}


def test_repeated_page_does_not_restore_disproved_candidate_and_copy_is_independent():
    graph=DomainNetwork({'a':{'x':1},'b':{'y':2}},open_domains={'a'})
    graph.connect('a','b',lambda a,b:a==b,'MATCH')
    assert graph.propagate()
    assert not graph.domains['a']
    child=graph.copy()
    child.extend('a',{'x':1,'z':2},complete=True)
    assert child.propagate() and child.domains['a']=={'z':2}
    assert graph.open_domains=={'a'} and not graph.domains['a']
    with pytest.raises(ValueError,match='ID_CHANGED'):graph.extend('a',{'x':3})


def test_explicit_selection_closes_open_source():
    graph=DomainNetwork({'a':{'x':1}},open_domains={'a'})
    graph.restrict('a',['x'],'SOURCE_DECISION')
    with pytest.raises(ValueError,match='ALREADY_CLOSED'):graph.extend('a',{'y':2})


@pytest.mark.parametrize('cases,kept,unresolved',[([],True,True),(['nom'],True,False),(['dat'],False,True)])
def test_parent_case_unknown_is_retained_but_not_ready(cases,kept,unresolved):
    from types import SimpleNamespace
    from ah.formalizer.pipeline import t0
    from ah.formalizer.state import FrameCandidate
    from ah.formalizer.composition_sources import CompositionSources
    from ah.formalizer.composition_tree import InputSlot
    state=t0('флырка');tid=state.evidence[0].token_id
    source=object.__new__(CompositionSources);source.state=state;source.child_domains={}
    frame=FrameCandidate('f','FLAT','флырка',(),semantic={'morph_bindings':{tid:{'pos':'NOUN','cases':cases}}})
    source.retain('key',SimpleNamespace(region_id='r'),state.evidence,[frame],InputSlot(head_ref=tid,allowed_cases=frozenset({'nom'})))
    assert ('f' in source.allowed('key'))==kept
    assert bool(frame.semantic.get('structural_unresolved'))==unresolved
    assert bool(frame.semantic.get('parent_slot_obligation'))==(kept and unresolved)


def test_missing_parent_premise_survives_accidental_resolved_flag():
    from ah.formalizer.state import FrameCandidate
    from ah.formalizer.task_contracts import child_result
    frame=FrameCandidate('f','FLAT','source',(),semantic={
        'structural_unresolved':False,'parent_slot_obligation':{'reason':'HEAD_CASE_UNKNOWN'}})
    assert not child_result([frame]).structure_complete


def test_singleton_with_open_parent_premise_is_not_selected():
    from ah.formalizer.pipeline import t0
    from ah.formalizer.state import FrameCandidate
    from ah.formalizer.composition_children import select_child
    state=t0('source')
    frame=FrameCandidate('f','FLAT','source',(),semantic={'parent_slot_obligation':{'reason':'HEAD_CASE_UNKNOWN'}})
    assert select_child(state,None,None,None,[frame],'NOMINAL','source') is None
