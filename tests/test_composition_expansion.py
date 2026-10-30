"""Expansion boundaries preserve domains and never certify completion."""
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.composition_dispatcher import Dispatcher, DispatchBlocked
from ah.formalizer.composition_tasks import ChildTasks
from ah.formalizer.composition_expansion import ExpansionWindows, ExpansionRequired


def test_address_includes_ancestor_contract_and_feedback():
    window = ExpansionWindows(t0('source'), width=1)
    def boundary(contract):
        with window.enter('parent', contract, None):
            with window.enter('child', 'same source', None):
                pass
    with pytest.raises(ExpansionRequired) as first:
        boundary('subject')
    window.demand(first.value)
    boundary('subject')
    with pytest.raises(ExpansionRequired) as second:
        boundary('object')
    assert first.value.address != second.value.address
    assert not window.path


def test_deep_requested_branch_replays_without_repeating_completed_probes():
    state=t0('source'); dispatcher=Dispatcher(state); tasks=ChildTasks(state,dispatcher)
    calls=[]
    def branch(depth):
        def compute():
            dispatcher.run('probe-like:'+str(depth),depth,
                lambda:calls.append(depth) or depth,kind='MORPHOLOGY')
            if depth < 7:return branch(depth+1)
            return [FrameCandidate('leaf','FLAT','source',(),semantic={'structural_unresolved':True})]
        return tasks.child(str(depth),compute,{'source':depth})
    result=branch(0)
    assert result[0].semantic['structural_unresolved']
    assert calls==list(range(8))
    deferred=[r for r in state.syntax_trace if r['kind']=='COMPOSITION_EXPANSION_DEFERRED']
    assert [r['depth'] for r in deferred]==[3,6]
    assert all(not r['structure_complete'] and not r['search_complete'] for r in deferred)
    assert not dispatcher.nodes['child:0']['receipt']['structure_complete']
    assert not tasks.expansion.frontier and not tasks.active and not tasks.expansion.path
    assert not dispatcher.stack


def test_budget_during_expansion_never_publishes_parent_result():
    state=t0('source'); dispatcher=Dispatcher(state,limit=4);tasks=ChildTasks(state,dispatcher)
    def branch(depth):
        return tasks.child(str(depth),lambda:branch(depth+1),depth)
    with pytest.raises(DispatchBlocked,match='INCOMPLETE'):
        branch(0)
    assert not dispatcher.valid('child:0')
    assert 'result' not in dispatcher.nodes['child:0']
    assert not tasks.active and not tasks.expansion.path and not dispatcher.stack
    assert tasks.expansion.frontier  # A request is not evidence of completion.
    assert any(d.code=='COMPOSITION_DISPATCH_INCOMPLETE' for d in state.diagnostics)


def test_cycle_is_not_an_expansion_request():
    state=t0('source');tasks=ChildTasks(state,Dispatcher(state))
    def cycle():return tasks.child('same',cycle,None)
    with pytest.raises(DispatchBlocked,match='CYCLE'):cycle()
    assert not any(r['kind']=='COMPOSITION_EXPANSION_REQUESTED' for r in state.syntax_trace)
