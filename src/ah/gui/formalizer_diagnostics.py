"""Read-only formatting of actual V7 diagnostics and oracle progress.

This view never interprets model text, evaluates a gold expectation or changes
runtime state. The subprocess owns counters and checkpoints; the panel displays
them separately from the normal chat backend.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from enum import Enum
import json


def diagnostic_json(value) -> str:
    def encode(obj):
        if isinstance(obj, Enum):
            return obj.value
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, (set, frozenset)):
            return sorted(obj, key=repr)
        return str(obj)
    return json.dumps(value, ensure_ascii=False, indent=2, default=encode)


def format_formalizer_requests(records=(), active=None, *, source_text="") -> str:
    """Render recorded requests verbatim; an in-flight call has no response yet."""
    rows = [r for r in records if str(getattr(r, "role", "")).startswith("formalizer")]
    parts = ["FORMALIZER V7 · ACTUAL MODEL REQUESTS", "SOURCE:\n" + source_text]
    if active is not None and str(getattr(active, "role", "")).startswith("formalizer"):
        rows.append(active)
    if not rows:
        parts.append("No bounded model call has been recorded for this turn. Deterministic stages may run without the model.")
    for row in rows:
        pending = row is active
        parts.extend([
            "\n" + "=" * 60,
            f"REQUEST #{row.sequence} · {row.role} · " + ("IN FLIGHT" if pending else "COMPLETED"),
            "SYSTEM:\n" + str(getattr(row, "system", "") or ""),
            "BOUNDED REQUEST:\n" + str(getattr(row, "prompt", "") or ""),
            "RESPONSE:\n" + ("<waiting for response>" if pending else str(getattr(row, "response_text", "") or "<empty>")),
        ])
        if getattr(row, "error", None):
            parts.append("ERROR:\n" + str(row.error))
    return "\n".join(parts)


def format_native_snapshot(snapshot) -> str:
    if snapshot is None:
        return "V7 IR / TRACE\nThe native run has not returned a diagnostic snapshot yet. No stages or facts are inferred from model output."
    return diagnostic_json(snapshot)


class OracleDiagnostics:
    """Bounded external-run view, safe to retain after a run finishes."""
    def __init__(self):
        self.events = deque(maxlen=64)
        self.requests = deque(maxlen=12)
        self.last_event = {}
        self.current_request = None
        self.requests_started = 0
        self.requests_finished = 0
        self.requests_failed = 0
        self._last_seq = 0
        self._case_checkpoints = deque(maxlen=64)
        self.case_id = ""
        self.running = False

    def update(self, event: Mapping) -> bool:
        if event.get("schema_version") not in (None, "v7-oracle-progress-1"):
            return False
        row = deepcopy(dict(event))
        seq = row.get("seq")
        if type(seq) is int:
            if seq <= self._last_seq:
                return False
            self._last_seq = seq
        name = str(row.get("event", ""))
        case_id = str(row.get("case_id", self.case_id) or "")
        if case_id != self.case_id:
            self.case_id = case_id
            self._case_checkpoints.clear()
            self.current_request = None
        if name == "request_started":
            self.requests_started += 1
            self.current_request = row
            self.requests.append(row)
        elif name == "request_finished":
            self.requests_finished += 1
            if row.get("error") or row.get("status") == "ERROR":
                self.requests_failed += 1
            request_id = row.get("request_id")
            prior = next((r for r in reversed(self.requests) if r.get("request_id") == request_id), {})
            merged = {**prior, **row}
            if prior:
                prior.clear()
                prior.update(merged)
            else:
                self.requests.append(merged)
            self.current_request = merged
        elif name == "step_finished":
            self._case_checkpoints.append(row)
        for key in ("requests_started", "requests_finished", "requests_failed"):
            value = row.get(key)
            if type(value) is int and value >= 0:
                setattr(self, key, max(value, getattr(self, key)))
        self.last_event = row
        self.events.append(row)
        return True

    def stage_text(self) -> str:
        row = self.last_event
        return ("V7 oracle · " + str(row.get("event", "waiting"))
                + (" · " + self.case_id if self.case_id else "")
                + (" / " + str(row["step_id"]) if row.get("step_id") else "")
                + f" | requests={self.requests_started}; finished={self.requests_finished}; errors={self.requests_failed}")

    def raw_text(self) -> str:
        row = self.current_request
        if not row:
            return "V7 ORACLE · MODEL REQUESTS\nNo HTTP/model request has started for the current case. Component checks may execute without the model."
        pending = row.get("event") == "request_started"
        parts = ["V7 ORACLE · ACTUAL MODEL REQUEST", f"CASE: {row.get('case_id', self.case_id)}",
                 f"REQUEST: {row.get('request_id', '')} · {row.get('role', '')}",
                 "STATUS: " + ("IN FLIGHT" if pending else str(row.get("status", "COMPLETED")))]
        for key, label in (("system", "SYSTEM"), ("prompt", "BOUNDED REQUEST"),
                           ("response", "VISIBLE MODEL RESPONSE"), ("raw_response", "HTTP RESPONSE"),
                           ("error", "ERROR")):
            if key in row:
                trunc = f" (preview of {row.get(key + '_chars', '?')} characters)" if row.get(key + "_truncated") else ""
                value = row[key] if isinstance(row[key], str) else diagnostic_json(row[key])
                parts.append(label + trunc + ":\n" + value)
        if pending:
            parts.append("RESPONSE: <waiting; request has started>")
        return "\n\n".join(parts)

    def ir_text(self) -> str:
        return diagnostic_json({"source": "V7 oracle subprocess (actual progress events)",
                                "last_event": self.last_event,
                                "case_checkpoints": list(self._case_checkpoints),
                                "note": "This is a bounded live preview. Complete IR, observations and provider bytes remain in the run artifacts."})

    def requests_text(self) -> str:
        return diagnostic_json({"source": "oracle subprocess",
                                "requests_started": self.requests_started,
                                "requests_finished": self.requests_finished,
                                "requests_failed": self.requests_failed,
                                "recent_requests": list(self.requests)})
