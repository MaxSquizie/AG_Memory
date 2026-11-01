"""External observations of formalizer execution, including private branches.

No trace identity, cursor, clock or writer is stored in FormalizationState.
Collected rows carry their capture time; they do not invent timestamps for
earlier mutations. Full state deltas are confined to stage/branch boundaries.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields, is_dataclass
from functools import wraps
from hashlib import sha256
from inspect import signature
from uuid import uuid4
import weakref


_tracker = ContextVar("formalizer_trace_tracker", default=None)
_state = ContextVar("formalizer_trace_state", default=None)

_STREAMS = ("syntax_trace", "rejections", "diagnostics", "context_reads")
_MAPS = {"decisions": "decision_updated", "component_probe_records": "probe_record",
         "morphology_records": "morphology_record", "observation": "observation_field",
         "generation_snapshot": "generation_field"}
_KEYED_LISTS = {"evidence": ("token_id", "token_evidence"),
                "frames": ("frame_id", "frame_updated")}


def _runtime():
    # diagnostics.__init__ imports runtime services; keep this import lazy.
    from ah.diagnostics import runtime_trace
    return runtime_trace


def enabled():
    try:
        return _runtime().enabled()
    except Exception:
        return False


def _safe(function):
    @wraps(function)
    def observe(*args, **kwargs):
        if not enabled():
            return None
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            _runtime().emit("trace_capture_failed", status="ERROR",
                            observer=function.__name__, error_type=type(exc).__name__,
                            reason=_runtime().error_text(exc))
            return None
    return observe


def _hash(value):
    return sha256(_runtime().encode_json(value).encode("utf-8", errors="backslashreplace")).hexdigest()


def _identity(state):
    # Early refusal states are t0 placeholders. Their default version can be 1
    # even when the validated observation/report refers to a later version.
    observation = state.observation
    return {"observation_id": observation.get("observation_id", state.source_uid),
            "interpretation_version": observation.get("interpretation_version", state.interpretation_version)}


class _Cursor:
    def __init__(self, state, ref, parent, inherited):
        self.state = weakref.ref(state)
        self.ref = ref
        self.parent = parent
        self.streams = {}
        self.values = {}
        self.decisions = {}
        if inherited:
            for name in _STREAMS:
                rows = getattr(state, name)
                self.streams[name] = (rows, len(rows), rows[-1] if rows else None)
            self.baseline(state)

    def baseline(self, state):
        for field in fields(state):
            name = field.name
            if name in _STREAMS:
                continue
            value = getattr(state, name)
            if name in _MAPS:
                self.values[name] = {str(key): _hash(item) for key, item in value.items()}
            elif name in _KEYED_LISTS:
                key, _ = _KEYED_LISTS[name]
                self.values[name] = {str(getattr(item, key)): _hash(item) for item in value}
            else:
                self.values[name] = _hash(value)


class _Tracker:
    def __init__(self):
        self.states = {}
        self.sequence = 0

    def register(self, state, parent=None, inherited=False):
        old = self.states.get(id(state))
        if old is not None and old.state() is state:
            return old
        self.sequence += 1
        parent_cursor = self.states.get(id(parent)) if parent is not None else None
        parent_ref = parent_cursor.ref if parent_cursor and parent_cursor.state() is parent else None
        cursor = _Cursor(state, "state:" + str(self.sequence), parent_ref, inherited)
        self.states[id(state)] = cursor
        state_id = id(state)
        def retire(reference):
            if self.states.get(state_id) is cursor:
                self.states.pop(state_id, None)
        cursor.state = weakref.ref(state, retire)
        _runtime().emit("state_fork" if inherited else "state_registered",
                        state_ref=cursor.ref, parent_state_ref=cursor.parent,
                        **_identity(state),
                        inherited_counts={name: len(getattr(state, name)) for name in _STREAMS}
                        if inherited else {}, capture="checkpoint")
        return cursor


@_safe
def register_state(state, *, parent=None, inherited=False):
    tracker = _tracker.get()
    if tracker is not None:
        return tracker.register(state, parent, inherited)


@_safe
def watch_state(state):
    """Associate the current executing state without changing the IR."""
    cursor = register_state(state)
    if cursor is not None:
        _state.set(state)
        _runtime().update_context(state_ref=cursor.ref, parent_state_ref=cursor.parent,
                                  **_identity(state))


@_safe
def report_context(report):
    identity = {}
    for key, attribute in (("run_id", "run_id"), ("observation_id", "observation_id"),
                           ("interpretation_version", "version")):
        value = getattr(report, attribute, None)
        if value is not None:
            identity[key] = value
    _runtime().update_context(**identity)


def _stream(cursor, state, name, reason):
    rows = getattr(state, name)
    previous, offset, tail = cursor.streams.get(name, (rows, 0, None))
    restored = (previous is not rows or offset > len(rows)
                or offset > 0 and rows[offset - 1] is not tail)
    if restored:
        _runtime().emit("state_collection_reset", state_ref=cursor.ref,
                        collection=name, previous_count=offset, count=len(rows),
                        capture="checkpoint", reason=reason)
        offset = 0
    events = {"syntax_trace": "syntax_trace", "rejections": "candidate_rejected",
              "diagnostics": "diagnostic", "context_reads": "context_read"}
    for index in range(offset, len(rows)):
        row = rows[index]
        entity = (row.get("decision_ref") or row.get("task_ref") or row.get("frame_ref")
                  or row.get("region_ref") or "") if isinstance(row, dict) else getattr(row, "candidate_id", "")
        row_reason = row.get("reason", "") if isinstance(row, dict) else getattr(row, "reason", getattr(row, "code", ""))
        _runtime().emit(events[name], state_ref=cursor.ref, parent_state_ref=cursor.parent,
                        entity_id=entity, reason=row_reason, record=row, index=index,
                        collection=name, capture="restored_snapshot" if restored else "checkpoint",
                        checkpoint_reason=reason)
    cursor.streams[name] = (rows, len(rows), rows[-1] if rows else None)


def _mapping(cursor, name, values, event, reason):
    old = cursor.values.setdefault(name, {})
    keys = {str(key) for key in values}
    for key in list(old):
        if key not in keys:
            _runtime().emit("state_item_removed", state_ref=cursor.ref,
                            collection=name, entity_id=key, capture="checkpoint", reason=reason)
            del old[key]
    for key, value in values.items():
        key = str(key)
        value_hash = _hash(value)
        if old.get(key) == value_hash:
            continue
        _runtime().emit(event, state_ref=cursor.ref, parent_state_ref=cursor.parent,
                        entity_id=key, collection=name, value=value,
                        status=getattr(value, "outcome", "") or "",
                        capture="checkpoint", reason=reason)
        old[key] = value_hash


@_safe
def checkpoint(state=None, *, full=False, reason="", collections=()):
    """Flush appended records, and optionally changed state fields.

    A checkpoint is observational: its position is the capture order. Records
    copied from a clarification snapshot are explicitly labelled as restored.
    """
    state = state if state is not None else _state.get()
    if state is None or _tracker.get() is None:
        return
    cursor = _tracker.get().states.get(id(state))
    # Read-only proof overlays are not executing branches. They have no cursor.
    if cursor is None or cursor.state() is not state:
        return
    with _runtime().bind(state_ref=cursor.ref, parent_state_ref=cursor.parent,
                         **_identity(state)):
        for name in _STREAMS:
            _stream(cursor, state, name, reason)
        if not full and not collections:
            return
        for field in fields(state):
            name = field.name
            if not full and name not in collections:
                continue
            if name in _STREAMS:
                # Diagnostics can be retired in place without changing length.
                # The full collection at a boundary records removals/reorders.
                value = getattr(state, name)
                if name == "syntax_trace":
                    continue
            else:
                value = getattr(state, name)
            if name in _MAPS:
                _mapping(cursor, name, value, _MAPS[name], reason)
            elif name in _KEYED_LISTS:
                key, event = _KEYED_LISTS[name]
                _mapping(cursor, name, {getattr(row, key): row for row in value}, event, reason)
            else:
                value_hash = _hash(value)
                if cursor.values.get(name) != value_hash:
                    _runtime().emit("state_field", state_ref=cursor.ref,
                                    field=name, value=value, capture="checkpoint", reason=reason)
                    cursor.values[name] = value_hash


@_safe
def note_decision(state, key):
    tracker = _tracker.get()
    cursor = tracker.states.get(id(state)) if tracker is not None else None
    if cursor is None or cursor.state() is not state:
        return
    value = state.decisions.get(key)
    if value is None:
        return
    old = cursor.values.setdefault("decisions", {})
    value_hash = _hash(value)
    if old.get(str(key)) != value_hash:
        _runtime().emit("decision_updated", entity_id=key, state_ref=cursor.ref,
                        **_identity(state),
                        collection="decisions", value=value, status=value.outcome or "",
                        capture="checkpoint", reason="probe_result")
        old[str(key)] = value_hash


@contextmanager
def executing_state(state, *, parent=None, inherited=False):
    if not enabled() or _tracker.get() is None:
        yield
        return
    cursor = register_state(state, parent=parent, inherited=inherited)
    if cursor is None:
        yield
        return
    token = _state.set(state)
    with _runtime().bind(state_ref=cursor.ref, parent_state_ref=cursor.parent,
                         **_identity(state)):
        _runtime().emit("state_execution_started", state_ref=cursor.ref)
        failure = {}
        try:
            yield
        except BaseException as exc:
            failure = {"error_type": type(exc).__name__, "reason": _runtime().error_text(exc)}
            raise
        finally:
            checkpoint(state, full=True, reason="state_execution_exit")
            _runtime().emit("state_execution_failed" if failure else "state_execution_finished",
                            state_ref=cursor.ref, status="INTERRUPTED" if failure else "RETURNED", **failure)
            _state.reset(token)


@contextmanager
def condition_scope(state, condition, *, shell_ref=None, child_ref=None):
    if not enabled():
        yield
        return
    checkpoint(state, reason="condition_enter")
    details = {**condition.record(), "hypothesis_ref": condition.hypothesis_ref,
               "parent_condition_ref": condition.parent_condition_ref,
               "parent_shell_ref": shell_ref or condition.parent_shell_ref,
               "child_ref": child_ref or condition.child_ref}
    with _runtime().bind(**details):
        _runtime().emit("condition_entered", **details)
        try:
            yield
        finally:
            checkpoint(state, reason="condition_exit", collections=("decisions", "component_probe_records"))
            _runtime().emit("condition_exited", **details)


@contextmanager
def phase(name, state=None, **fields):
    """A lexically scoped stage; contexts always unwind in their entry order."""
    if not enabled():
        yield {}
        return
    with _runtime().span(name, **fields) as outcome:
        if state is not None:
            watch_state(state)
        try:
            yield outcome
        finally:
            checkpoint(state, full=True, reason="stage_exit")


@_safe
def _result(result, outcome):
    state = None
    report = None
    if isinstance(result, tuple) and len(result) == 2 and hasattr(result[0], "source_uid"):
        state, report = result
    elif hasattr(result, "source_uid"):
        state = result
    elif hasattr(result, "state") and hasattr(result.state, "source_uid"):
        state = result.state
    elif hasattr(result, "terminal") or hasattr(result, "t5_eligibility"):
        report = result
    if state is not None:
        watch_state(state)
        checkpoint(state, full=True, reason="operation_result")
        outcome["machine_state"] = state.machine_state
        outcome["decision_outcomes"] = {key: value.outcome for key, value in state.decisions.items()}
    if report is not None:
        report_context(report)
        # A rejected preflight may have an empty terminal but a precise T5 code.
        terminal = getattr(report, "terminal", "")
        outcome["status"] = getattr(terminal, "value", terminal) or getattr(report, "t5_eligibility", "") or "RETURNED"
        if is_dataclass(report):
            payload = {field.name: getattr(report, field.name) for field in fields(report) if field.name != "perception"}
        else:
            payload = {"terminal": terminal}
        _runtime().emit("formalizer_result", report=payload, status=outcome["status"])
    elif isinstance(result, dict):
        _runtime().emit("formalizer_result", result=result, status="RETURNED")


def traced(operation, *, mode="native"):
    """Pair public entry/exit events, retaining independent invocation identity."""
    def decorate(function):
        sig = signature(function)

        @wraps(function)
        def call(*args, **kwargs):
            if not enabled():
                return function(*args, **kwargs)
            rt = _runtime()
            try:
                arguments = sig.bind_partial(*args, **kwargs).arguments
            except TypeError:
                arguments = kwargs
            observation = arguments.get("observation") or {}
            given_state = arguments.get("state")
            identity = {key: arguments[key] for key in ("run_id", "observation_id")
                        if arguments.get(key) is not None}
            if isinstance(observation, dict):
                identity.update({key: observation[key] for key in ("observation_id", "interpretation_version") if key in observation})
            if "version" in arguments:
                identity["interpretation_version"] = arguments["version"]
            root = _tracker.get() is None
            tracker_token = _tracker.set(_Tracker()) if root else None
            if root:
                parent = rt.current_context()
                identity["trace_id"] = (parent.get("trace_id") if parent.get("span_id") else None) or "trace:" + uuid4().hex
                if "turn_id" not in parent:
                    from ah.diagnostics.session_log import active_session
                    session = active_session()
                    if session is not None and rt.active_trace() is session.runtime_trace:
                        identity["turn_id"] = session.current_turn_id()
            state_token = _state.set(given_state if given_state is not None else _state.get())
            with rt.bind(**identity):
                with rt.span(operation, mode=mode) as outcome:
                    try:
                        if given_state is not None:
                            watch_state(given_state)
                        inputs = {key: arguments[key] for key in (
                            "text", "context_facts", "raw_input", "observation", "resolution_key",
                            "trigger_ref", "previous_version", "target_version") if key in arguments}
                        if inputs:
                            rt.emit("formalizer_input", operation=operation, inputs=inputs)
                        result = function(*args, **kwargs)
                        _result(result, outcome)
                        return result
                    finally:
                        checkpoint(full=True, reason="operation_exit")
                        _state.reset(state_token)
                        if tracker_token is not None:
                            _tracker.reset(tracker_token)
        return call
    return decorate
