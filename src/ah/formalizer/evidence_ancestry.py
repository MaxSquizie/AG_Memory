"""Pure, iterative traversal of provider receipts for addressed read discard.

An old receipt is ancestry, not permission: retain its exact revision even after
invalidation so that repair can remove the obsolete obligation that used it.
No validation, observers or provider execution occurs here.
"""
from contextvars import ContextVar

_current=ContextVar('evidence_ancestry',default=None)


def collect(state,initial):
    current=_current.get()
    if current is not None and current['state'] is state:return initial()
    context={'state':state,'pending':[]};token=_current.set(context)
    try:
        refs=set(initial());seen=set()
        if not context['pending']:return refs
        receipts={(r.get('task_ref'),r.get('revision')):r for r in state.syntax_trace
                  if r.get('kind')=='DISPATCH_COMPLETED'}
        from .dispatch_evidence import read_probe_refs
        while context['pending']:
            key=context['pending'].pop()
            if key in seen:continue
            seen.add(key);row=receipts.get(key)
            if key[0].startswith('probe:'):refs.add(key[0].removeprefix('probe:'))
            if row is None:continue
            context['pending'].extend((r['task_ref'],r['revision']) for r in row.get('dependencies',()))
            for read in row.get('evidence_reads',()):
                refs.update(read_probe_refs(state,read))
        return refs
    finally:_current.reset(token)


def provider_refs(state,task,revision):
    def enqueue():
        _current.get()['pending'].append((task,revision))
        return set()
    return collect(state,enqueue)
