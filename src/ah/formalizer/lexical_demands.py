"""Suspend hidden child composition before any child computation or mutation."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from .canonical_ledger import digest
from .composition_dispatcher import canonical

_owner=ContextVar('lexical_child_demand',default=None)


class ChildDemand(Exception):
    def __init__(self,obligation,invocation):
        self.obligation=obligation
        self.invocation=invocation
        super().__init__('LEXICAL_CHILD_PENDING')


@contextmanager
def capture(state,origin):
    token=_owner.set((state,origin))
    try:yield
    finally:_owner.reset(token)


def intercept(state,region,tokens,cfg,depth,attachment,infinitive,request):
    owner=_owner.get()
    if owner is None or owner[0] is not state:return
    from .composition_session import current,child_key
    from .structural_conditions import active
    runtime=current(state);condition=active(state)
    row={'kind':'LEXICAL_CHILD_DEMAND','origin':owner[1],
         'child_key':child_key(region,tokens,attachment,infinitive,request),
         'region_ref':region.region_id,'source_range':list(region.source_range),
         'token_refs':[t.token_id for t in tokens],
         'input_slot':canonical(request),'attachment':canonical(attachment),
         'infinitive':canonical(infinitive),'cfg':canonical(cfg),'depth':depth,
         'condition':condition.record() if condition else None,
         'context':canonical(runtime.capture_context()) if runtime else None,
         'parent_feedback':canonical(runtime.tasks.feedback) if runtime else None,
         'status':'PENDING_SCHEDULER','structure_complete':False,'write_eligible':False}
    row['obligation_ref']='lexical-demand:'+digest(row)
    invocation=deepcopy({'region':region,'tokens':tokens,'cfg':cfg,'depth':depth,
        'attachment':attachment,'infinitive':infinitive,'request':request,
        'context':runtime.capture_context() if runtime else None,
        'parent_feedback':runtime.tasks.feedback if runtime else None})
    raise ChildDemand(deepcopy(row),invocation)
