"""Child resume must not erase unresolved evidence merely for one root."""
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.composition_dispatcher import Dispatcher
from ah.formalizer.composition_tasks import ChildTasks
from ah.formalizer.task_contracts import produced,child_result,TaskOutcome


def frame(**semantic):
    return FrameCandidate('root','FLAT','source',(),semantic=semantic)

assert not produced('COMPOSITION',[frame()]).structure_complete
closed=child_result([frame()])
assert closed.structure_complete and not closed.search_complete and not closed.write_eligible
for sem in [
    {'pending_proposition_roles':['CONTENT']},
    {'proposition_args':{'CONTENT':{'frame_ref':'missing'}}},
    {'proposition_args':{'CONTENT':{'frame_ref':'root'}}},
    {'partial_composition':{'choices':['a','b']}},
    {'composition_domain':{'frame_refs':['root']}},
]:
    assert not child_result([frame(**sem)]).structure_complete,sem
assert not child_result([frame()],pending=['probe']).structure_complete
assert not child_result([frame()],blocked=True).structure_complete

for mode in ['closed','slot','pending','blocked','partial']:
    state=t0('source');tasks=ChildTasks(state,Dispatcher(state))
    state.component_probe_records['p']={'decision':{'selector_outcome':'INSUFFICIENT_CONTEXT'}}
    def compute():
        if tasks.feedback is None:
            tasks.record_probe('p');state.diag('CHILD_NEEDS_CONTEXT','source')
            return []
        if mode=='pending':tasks.record_probe('p')
        if mode=='blocked':state.diag('COMPUTATION_LIMIT','child')
        return [frame(**({'pending_proposition_roles':['CONTENT']} if mode=='slot' else
                         {'partial_composition':{'choices':['a','b']}} if mode=='partial' else {}))]
    frames=tasks.child('child',compute)
    old=state.diagnostics[0]
    assert tasks.resume(frames,'parent slot','source context','parent')
    assert any(d is old for d in state.diagnostics)==(mode!='closed'),mode
    receipt=tasks.dispatcher.nodes['child:child']['receipt']
    assert receipt['structure_complete']==(mode=='closed'),(mode,receipt)
    assert not receipt['search_complete'] and not receipt['write_eligible']
print('PASS: child closure vs cardinality; missing/cyclic slots; partial choices; pending probes; budget; resume diagnostics; independent search/write guarantees')
