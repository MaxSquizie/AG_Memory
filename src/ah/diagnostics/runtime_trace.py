"""Append-only, task-local runtime observations in a versioned TSV format.

Each event occupies one physical UTF-8 line. Scalar columns escape backslash,
tab, carriage return and newline as ``\\\\``, ``\\t``, ``\\r`` and ``\\n``.
``data_json`` is ordinary JSON and needs only ``json.loads``. TSV readers should
disable CSV quote processing (``csv.QUOTE_NONE``). No payload is truncated.

The writer and observation helpers never supply inputs to interpretation. An
unwritable journal disables this observer, reports the failure once, and leaves
the application's result or exception unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields as dataclass_fields, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
import base64
import json
import math
from pathlib import Path
import sys
from threading import RLock
from time import monotonic
from uuid import UUID, uuid4
import warnings


SCHEMA_VERSION = "runtime-tsv-1"
TSV_COLUMNS = (
    "schema_version", "timestamp", "sequence", "session_id", "turn_id",
    "trace_id", "span_id", "parent_span_id", "run_id", "observation_id",
    "interpretation_version", "component", "stage", "event", "status",
    "duration_ms", "entity_id", "reason", "data_json",
)
_GENERATED_COLUMNS = {"schema_version", "timestamp", "sequence", "session_id", "event", "data_json"}
_DIMENSIONS = set(TSV_COLUMNS) - _GENERATED_COLUMNS
_INHERITED_FIELDS = {
    "turn_id", "trace_id", "run_id", "observation_id", "interpretation_version",
}
_DEFAULT = object()
_sink = ContextVar("runtime_trace_sink", default=_DEFAULT)
_context = ContextVar("runtime_trace_context", default=None)


def _type_name(value):
    cls = type(value)
    return cls.__module__ + "." + cls.__qualname__


def _safe_text(value):
    try:
        return str(value)
    except Exception:
        return "<unprintable " + _type_name(value) + ">"


def error_text(value):
    """Render an observation error without replacing the original exception."""
    return _safe_text(value)


def escape_scalar(value):
    """Encode a scalar column without introducing a physical tab or newline."""
    if value is None:
        return ""
    return (_safe_text(value).replace("\\", "\\\\").replace("\t", "\\t")
            .replace("\r", "\\r").replace("\n", "\\n"))


def unescape_scalar(value):
    """Reverse :func:`escape_scalar`; unknown escape sequences stay literal."""
    result = []
    index = 0
    replacements = {"\\": "\\", "t": "\t", "r": "\r", "n": "\n"}
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value) and value[index + 1] in replacements:
            result.append(replacements[value[index + 1]])
            index += 2
        else:
            result.append(value[index])
            index += 1
    return "".join(result)


def _json_value(value, seen, problems):
    if isinstance(value, Enum):
        return _json_value(value.value, seen, problems)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"_trace_float": str(value)}
    if isinstance(value, (Path, UUID)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"_trace_bytes_base64": base64.b64encode(value).decode("ascii")}
    identity = id(value)
    if identity in seen:
        problems.add("cycle")
        return {"_trace_unserializable": "cycle", "type": _type_name(value)}
    seen.add(identity)
    try:
        if is_dataclass(value) and not isinstance(value, type):
            return {field.name: _json_value(getattr(value, field.name), seen, problems)
                    for field in dataclass_fields(value)}
        if isinstance(value, dict):
            if all(isinstance(key, str) for key in value):
                return {key: _json_value(item, seen, problems) for key, item in value.items()}
            return {"_trace_mapping": [[_json_value(key, seen, problems), _json_value(item, seen, problems)]
                                       for key, item in value.items()]}
        if isinstance(value, (tuple, list)):
            return [_json_value(item, seen, problems) for item in value]
        if isinstance(value, (set, frozenset)):
            items = [_json_value(item, seen, problems) for item in value]
            return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        problems.add("unsupported type")
        return {"_trace_unserializable": "unsupported_type", "type": _type_name(value)}
    finally:
        seen.remove(identity)


def _warning(message):
    try:
        warnings.warn(message, RuntimeWarning, stacklevel=3)
    except Exception:
        # Warning filters can promote warnings to exceptions; diagnostics still
        # must not replace a successful commit or an application's exception.
        try:
            print(message, file=sys.stderr)
        except Exception:
            pass


def _encode_json(value):
    problems = set()
    data = _json_value(value, set(), problems)
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True, allow_nan=False)
    # U+2028/U+2029 are valid JSON characters but text viewers can display them
    # as line breaks; keep the physical-row contract.
    return encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"), problems


def encode_json(value):
    """Encode typed observation data without deepcopy, mutation or truncation.

    Unsupported objects and cycles receive explicit ``_trace_unserializable``
    markers. Identical mappings and sets serialize in a stable order so callers
    may hash this representation for observation-only change detection.
    """
    return _encode_json(value)[0]


def read_events(path):
    """Stream decoded events without the csv module's 128 KiB cell limit.

    Only tabs inserted by the writer delimit fields. JSON is decoded into
    ``data`` while the original ``data_json`` column remains available.
    Malformed/truncated records are reported rather than silently skipped.
    """
    with Path(path).open(encoding="utf-8", newline="") as stream:
        header = stream.readline().rstrip("\r\n").split("\t")
        if tuple(header) != TSV_COLUMNS:
            raise ValueError("RUNTIME_TSV_HEADER_INVALID")
        for number, line in enumerate(stream, 2):
            values = line.rstrip("\r\n").split("\t")
            if len(values) != len(TSV_COLUMNS) or not line.endswith("\n"):
                raise ValueError(f"RUNTIME_TSV_ROW_INCOMPLETE: line {number}")
            row = {name: value if name == "data_json" else unescape_scalar(value)
                   for name, value in zip(TSV_COLUMNS, values)}
            if row["schema_version"] != SCHEMA_VERSION:
                raise ValueError(f"RUNTIME_TSV_SCHEMA_UNSUPPORTED: line {number}")
            try:
                row["data"] = json.loads(row["data_json"])
            except ValueError as exc:
                raise ValueError(f"RUNTIME_TSV_JSON_INVALID: line {number}") from exc
            yield row


class RuntimeTrace:
    """One thread-safe TSV stream, created exclusively and flushed per event."""

    def __init__(self, path, *, session_id=""):
        self.path = Path(path)
        self.session_id = session_id or "session:" + uuid4().hex
        self.enabled = False
        self._lock = RLock()
        self._file = None
        self._sequence = 0
        self._failure_reported = False
        self._serialization_reported = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # An existing trace belongs to another writer/run. Never truncate
            # it or silently append a second sequence or schema into its stream.
            self._file = self.path.open("x", encoding="utf-8", errors="backslashreplace", newline="\n")
            self._file.write("\t".join(TSV_COLUMNS) + "\n")
            self._file.flush()
            self.enabled = True
        except Exception as exc:
            self._disable(exc)

    def _disable(self, exc):
        self.enabled = False
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
        if not self._failure_reported:
            self._failure_reported = True
            _warning(f"Runtime TSV logging disabled for {self.path}: {type(exc).__name__}: {_safe_text(exc)}")

    def emit(self, event, *, component="formalizer", **fields):
        if not self.enabled:
            return
        with self._lock:
            if not self.enabled:
                return
            try:
                record = {**(_context.get() or {}), **fields}
                record["component"] = component
                payload = {key: value for key, value in record.items() if key not in _DIMENSIONS}
                encoded, problems = _encode_json(payload)
                record.update(
                    schema_version=SCHEMA_VERSION,
                    timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    sequence=self._sequence + 1,
                    session_id=self.session_id,
                    event=event,
                    data_json=encoded,
                )
                line = "\t".join(encoded if name == "data_json" else escape_scalar(record.get(name))
                                 for name in TSV_COLUMNS) + "\n"
                self._file.write(line)
                self._file.flush()
                self._sequence += 1
                if problems and not self._serialization_reported:
                    self._serialization_reported = True
                    _warning(f"Runtime TSV payload contains explicit serialization markers ({', '.join(sorted(problems))}): {self.path}")
            except Exception as exc:
                self._disable(exc)

    def close(self):
        with self._lock:
            self.enabled = False
            if self._file is not None:
                try:
                    self._file.close()
                    self._file = None
                except Exception as exc:
                    self._disable(exc)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def active_trace():
    """Use an explicit task sink, or the current GUI/CLI session's writer."""
    writer = _sink.get()
    if writer is not _DEFAULT:
        return writer
    try:
        from .session_log import active_session
        session = active_session()
        return getattr(session, "runtime_trace", None)
    except Exception:
        return None


def enabled():
    writer = active_trace()
    try:
        return writer is not None and writer.enabled
    except Exception:
        return False


@contextmanager
def use_trace(writer):
    """Temporarily select a sink; ``None`` explicitly disables fallback logging."""
    token = _sink.set(writer)
    try:
        yield writer
    finally:
        _sink.reset(token)


@contextmanager
def bind(**fields):
    """Bind correlation fields to this task without leaking them to siblings."""
    token = _context.set({**(_context.get() or {}), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def update_context(**fields):
    if enabled():
        _context.set({**(_context.get() or {}), **fields})


def current_context():
    """An isolated view of observation dimensions, never interpretation input."""
    return dict(_context.get() or {})


def emit(event, *, component="formalizer", **fields):
    writer = active_trace()
    if writer is None:
        return
    try:
        if not writer.enabled:
            return
        if "turn_id" not in fields and "turn_id" not in (_context.get() or {}):
            from .session_log import active_session
            session = active_session()
            # An explicit headless sink must not inherit a foreign GUI turn.
            if session is not None and writer is getattr(session, "runtime_trace", None):
                fields["turn_id"] = session.current_turn_id()
        writer.emit(event, component=component, **fields)
    except Exception:
        # Also isolate custom writer implementations supplied by host code.
        pass


@contextmanager
def span(stage, *, component="formalizer", **fields):
    """Record a paired operation, preserving its actual result and exception.

    The yielded dict accepts ``status``, ``reason`` and additional result fields.
    Caller-provided status/reason survive failure, with ERROR/exception text as
    defaults. Large input fields appear only on this span's events.
    """
    outcome = {}
    if not enabled():
        yield outcome
        return
    parent = _context.get() or {}
    identifiers = {name: value for name, value in fields.items() if name in _INHERITED_FIELDS}
    identifiers.update(
        trace_id=identifiers.get("trace_id") or parent.get("trace_id") or "trace:" + uuid4().hex,
        span_id="span:" + uuid4().hex,
        parent_span_id=parent.get("span_id", ""),
        stage=stage,
        component=component,
    )
    started = monotonic()
    details = {name: value for name, value in fields.items() if name not in _INHERITED_FIELDS}
    with bind(**identifiers):
        emit("span_started", component=component, **details)
        try:
            yield outcome
        except BaseException as exc:
            result = {**details, **outcome}
            result.setdefault("status", "ERROR")
            result.setdefault("reason", _safe_text(exc))
            result.update(error_type=type(exc).__name__, error=_safe_text(exc),
                          duration_ms=(monotonic() - started) * 1000)
            result.setdefault("component", component)
            emit("span_failed", **result)
            raise
        else:
            result = {**details, **outcome}
            result.setdefault("status", "OK")
            result["duration_ms"] = (monotonic() - started) * 1000
            result.setdefault("component", component)
            emit("span_finished", **result)
