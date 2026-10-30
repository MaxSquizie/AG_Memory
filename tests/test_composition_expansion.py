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
    assert window.frontier[first.value.address]['status']=='REQUESTED'
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


def test_scheduler_depth_does_not_grow_with_language_depth():
    state=t0('source');dispatcher=Dispatcher(state);tasks=ChildTasks(state,dispatcher)
    maximum=0
    def branch(depth):
        def compute():
            nonlocal maximum
            maximum=max(maximum,len(tasks.active))
            if depth<1100:return branch(depth+1)
            return [FrameCandidate('leaf','FLAT','source',())]
        return tasks.child(str(depth),compute,depth)
    assert branch(0)[0].frame_id=='leaf'
    assert maximum<=3
    assert dispatcher.valid('child:0')
    assert not tasks.expansion.path and not tasks.expansion.frontier


def test_scheduled_child_restores_context_and_pending_probe_dependency():
    state=t0('source');tasks=ChildTasks(state,Dispatcher(state))
    state.component_probe_records['p']={'decision':{'selector_outcome':'INSUFFICIENT_CONTEXT'}}
    context=['outside'];seen=[]
    tasks.capture_context=lambda:context[0]
    tasks.restore_context=lambda value:context.__setitem__(0,value)
    def branch(depth):
        def compute():
            inherited=context[0];seen.append((depth,inherited))
            try:
                context[0]='parent:'+str(depth)
                if depth<5:return branch(depth+1)
                tasks.record_probe('p')
                return []
            finally:context[0]=inherited
        return tasks.child(str(depth),compute,depth)
    branch(0)
    assert context==['outside']
    assert all(value==('outside' if depth==0 else 'parent:'+str(depth-1)) for depth,value in seen)
    assert tasks.cache['0',None]['pending']==['p']
    assert 'child:3' in tasks.dispatcher.nodes['child:2']['reads']


def test_feedback_resume_can_suspend_then_finish_same_attempt():
    state=t0('source');tasks=ChildTasks(state,Dispatcher(state))
    state.component_probe_records['p']={'decision':{'selector_outcome':'INSUFFICIENT_CONTEXT'}}
    def deep(depth):
        return tasks.child('nested:'+str(depth),lambda:deep(depth+1) if depth<5 else [FrameCandidate('leaf','FLAT','source',())],depth)
    def child():
        if tasks.feedback:
            assert tasks.feedback['contract']=='parent slot'
            return deep(0)
        tasks.record_probe('p');return []
    def parent():
        frames=tasks.child('child',child)
        assert tasks.resume(frames,'parent slot','context','parent')
        return frames
    result=tasks.child('parent',parent)
    assert result[0].frame_id=='leaf'
    assert any(row.get('kind')=='COMPOSITION_CHILD_RESUMED' and row['structure_complete'] for row in state.syntax_trace)
    assert tasks.feedback is None and not tasks.expansion.frontier


def test_cycle_to_suspended_nonroot_ancestor_is_detected():
    state=t0('source');tasks=ChildTasks(state,Dispatcher(state));calls=[]
    def branch(depth):
        def compute():
            calls.append(depth)
            return branch(1 if depth==5 else depth+1)
        return tasks.child(str(depth),compute,depth)
    with pytest.raises(DispatchBlocked,match='CYCLE'):branch(0)
    assert calls==[0,1,2,3,4,5]
    assert not tasks.driving and not tasks.active and not tasks.expansion.path


def test_session_fields_restore_at_each_scheduled_window():
    from ah.formalizer.composition_session import session
    from types import SimpleNamespace
    release=SimpleNamespace(entries=lambda kind:[{'max_rule_steps':1000}] if kind=='ProposalPolicy' else [])
    state=t0('source');observed=[]
    with session(state,release) as runtime:
        runtime.morphology_scope='outside morphology';runtime.domain_feedback='outside feedback'
        def branch(depth):
            def compute():
                observed.append((depth,runtime.morphology_scope,runtime.domain_feedback))
                previous=runtime.morphology_scope,runtime.domain_feedback
                runtime.morphology_scope='morphology '+str(depth)
                runtime.domain_feedback='feedback '+str(depth)
                try:return branch(depth+1) if depth<5 else []
                finally:runtime.morphology_scope,runtime.domain_feedback=previous
            return runtime.child(str(depth),compute,depth)
        branch(0)
        assert runtime.morphology_scope=='outside morphology'
        assert runtime.domain_feedback=='outside feedback'
    for depth,morphology,feedback in observed:
        assert morphology==('outside morphology' if depth==0 else 'morphology '+str(depth-1))
        assert feedback==('outside feedback' if depth==0 else 'feedback '+str(depth-1))


def test_inherited_morphology_and_feedback_are_child_cache_inputs():
    from ah.formalizer.composition_session import session
    from types import SimpleNamespace
    release=SimpleNamespace(entries=lambda kind:[{'max_rule_steps':1000}] if kind=='ProposalPolicy' else [])
    state=t0('source');calls=[]
    with session(state,release) as runtime:
        def compute():
            calls.append((runtime.morphology_scope,runtime.domain_feedback));return []
        runtime.morphology_scope='scope one'
        runtime.child('child',compute);runtime.child('child',compute)
        runtime.morphology_scope='scope two';runtime.child('child',compute)
        runtime.domain_feedback='new constraint';runtime.child('child',compute)
        assert calls==[('scope one',None),('scope two',None),('scope two','new constraint')]
