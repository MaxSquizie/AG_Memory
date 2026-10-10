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
    callback = _observer.get()
    if callback is not None:
        try:
            callback({'event': event, 'monotonic_seconds': monotonic(), **fields})
        except Exception:
            # A broken observer cannot turn a committed operation into a failure.
            pass
