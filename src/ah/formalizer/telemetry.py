"""Optional, task-local runtime observations; never an input to interpretation."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

_observer = ContextVar('formalizer_observer', default=None)


@contextmanager
def observe(callback):
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


def emit(event, **fields):
    # TSV is a separate subscriber: a document/GUI observer must not replace it.
    try:
        from . import runtime_tracing
        if runtime_tracing.enabled():
            runtime_tracing.checkpoint(full=event == 'stage', reason=event)
            from ah.diagnostics.runtime_trace import emit as emit_tsv
            emit_tsv(event, **fields)
    except Exception:
        pass
    callback = _observer.get()
    if callback is not None:
        try:
            callback({'event': event, 'monotonic_seconds': monotonic(), **fields})
        except Exception:
            # A broken observer cannot turn a committed operation into a failure.
            pass
