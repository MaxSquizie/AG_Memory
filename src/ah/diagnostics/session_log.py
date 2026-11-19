from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
import json
import os
import uuid

_active_lock = Lock()
_active: SessionLogger | None = None


def protocol_preview(text: str | None, *, limit: int = 240) -> dict[str, Any]:
    """Compact view of a model string so protocol mismatches are visible."""

    raw = "" if text is None else str(text)
    stripped = raw.strip()
    first = stripped.splitlines()[0].strip() if stripped else ""
    token = first.split()[0] if first.split() else ""
    return {
        "len": len(raw),
        "stripped_len": len(stripped),
        "lines": raw.count("\n") + (1 if raw else 0),
        "first_line": first[:limit],
        "token": token[:80],
        "repr": repr(raw[:limit]),
        "has_ws_padding": raw != stripped,
    }


def _text_summary(kind: str, payload: dict[str, Any]) -> str:
    if kind == "pipeline_probe":
        preview = payload.get("raw_preview") or {}
        status = "OK" if payload.get("accepted") else "FAIL"
        return (
            f"{status} {payload.get('stage')} "
            f"raw={preview.get('repr', payload.get('raw'))} "
            f"err={payload.get('error')}"
        )
    if kind == "pipeline_parse_summary":
        return (
            f"ok={payload.get('ok')} probes={payload.get('probe_count')} "
            f"failed={payload.get('failed_count')} err={payload.get('error')}"
        )
    if kind == "llm_request":
        preview = payload.get("response_preview") or {}
        return (
            f"#{payload.get('sequence')} {payload.get('role')} "
            f"err={payload.get('error')} out={preview.get('repr')}"
        )
    if kind == "turn_start":
        return f"#{payload.get('seq')} {payload.get('user_text')!r}"
    if kind == "turn_end":
        return (
            f"{payload.get('fail_kind') or payload.get('status')} "
            f"{payload.get('user_text')!r} {payload.get('error') or ''}"
        )
    if kind == "pipeline_unresolved_goal":
        return f"{payload.get('text')!r} diagnostics={payload.get('diagnostics')}"
    if kind == "pipeline_perception_failed":
        return f"{payload.get('error_type')} {payload.get('error')}"
    if kind == "pipeline_integration_failed":
        return f"{payload.get('error_type')} {payload.get('error')}"
    dumped = json.dumps(payload, ensure_ascii=False, default=str)
    if len(dumped) > 400:
        dumped = dumped[:400] + "…"
    return dumped


# Session events may carry arbitrary model or user strings, including in errors
# and identifiers. Only known event names, typed counters, and enum values
# cross the metadata-only writer. Unknown future events are dropped by default.
_EVENT_FIELDS = {
    "session_start": (), "turn_start": ("seq",), "turn_end": ("seq", "probe_count", "assertion_count"),
    "llm_request": ("sequence",), "agent_sanitize": ("contaminated",),
    "agent_repair": ("attempt", "contaminated"), "agent_response_generation_failed": (),
    "pipeline_raw": (), "pipeline_sensory": (),
    "pipeline_candidates": ("lexical_pass", "coordination_count", "frame_dependency_count"),
    "pipeline_lexical_recovery": ("pass_index",),
    "pipeline_perception": ("relation_count", "conditional_count"),
    "pipeline_candidate_ir": ("query_count", "quantified_query_count", "command_count", "relation_count", "conditional_count"),
    "pipeline_mutation_plan": (), "pipeline_canonical_commit": (),
    "pipeline_probe": ("accepted",), "pipeline_parse_summary": ("ok", "probe_count", "failed_count"),
    "pipeline_unresolved_goal": (), "pipeline_perception_failed": (), "pipeline_integration_failed": (),
    "identity_merge": (), "state_transition_projection_skipped": (),
    "android_turn": ("probe_count",), "android_turn_failed": (), "android_snapshot_failed": (),
    "ignition_tick": ("tick",), "gc_delete": ("tick", "deleted_count"), "lifecycle_update": ("tick", "update_count"),
}
_ENUM_FIELDS = {
    "role": {"generic", "formalizer", "perception", "agent", "agent_repair", "agent_clarification"},
    "status": {"ok", "error"},
    "fail_kind": {"perception", "integration", "exception", "response_generation", "empty_response", "unresolved_goal"},
}


def _metadata(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    record = {name: payload[name] for name in _EVENT_FIELDS[kind] if type(payload.get(name)) in (int, bool)}
    for name, allowed in _ENUM_FIELDS.items():
        value = payload.get(name)
        if type(value) is str and value in allowed:
            record[name] = value
    if kind == "llm_request":
        record["failed"] = bool(payload.get("error"))
        for name in ("prompt", "response_text"):
            if isinstance(payload.get(name), str):
                record[name + "_chars"] = len(payload[name])
    return record


class SessionLogger:
    """Runtime-only append-only diagnostics. Never enters AH/H."""
    def __init__(self, logs_dir: Path, *, include_content: bool = False) -> None:
        self.include_content = include_content
        self.logs_dir = Path(logs_dir) / ("debug" if include_content else "telemetry")
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.jsonl_path = self.logs_dir / f"session-{self.session_id}.jsonl"
        self.text_path = self.logs_dir / f"session-{self.session_id}.log"
        self.latest_jsonl = self.logs_dir / "latest.jsonl"
        self.latest_text = self.logs_dir / "latest.log"
        self.turns_path = self.logs_dir / "turns.jsonl"
        self._lock = Lock()
        self._disabled = False
        self._turn_seq = 0
        self._turn_id: str | None = None
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            for path in (self.jsonl_path, self.latest_jsonl, self.text_path, self.latest_text):
                path.write_text("", encoding="utf-8")
            if not self.turns_path.is_file():
                self.turns_path.write_text("", encoding="utf-8")
        except OSError:
            self._disabled = True

    def current_turn_id(self) -> str | None:
        with self._lock:
            return self._turn_id

    def begin_turn(self, user_text: str) -> str:
        with self._lock:
            self._turn_seq += 1
            self._turn_id = f"{self.session_id}:{self._turn_seq}"
            turn_id = self._turn_id
            seq = self._turn_seq
        self._write("turn_start", {"seq": seq, "user_text": user_text}, turn_id)
        return turn_id

    def finish_turn(self, **payload: Any) -> None:
        with self._lock:
            turn_id = self._turn_id
            seq = self._turn_seq
            self._turn_id = None
        self._write("turn_end", {**payload, "seq": seq}, turn_id)

    def emit(self, kind: str, **payload: Any) -> None:
        self._write(kind, payload, self.current_turn_id())

    def _write(self, kind: str, payload: dict[str, Any], turn_id: str | None) -> None:
        if self._disabled or (not self.include_content and kind not in _EVENT_FIELDS):
            return
        fields = payload if self.include_content else _metadata(kind, payload)
        record = {**fields, "ts": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                  "session": self.session_id, "kind": kind, "turn_id": turn_id}
        line = json.dumps(record, ensure_ascii=False, default=str)
        detail = _text_summary(kind, fields) if self.include_content else json.dumps(fields)
        summary = f"{record['ts']} {kind} {detail}"
        with self._lock:
            try:
                paths = [self.jsonl_path, self.latest_jsonl]
                if kind == "turn_end":
                    paths.append(self.turns_path)
                for path in paths:
                    with path.open("a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
                for path in (self.text_path, self.latest_text):
                    with path.open("a", encoding="utf-8") as fh:
                        fh.write(summary + "\n")
            except OSError:
                self._disabled = True


def start_session(logs_dir: Path, *, extra: dict[str, Any] | None = None,
                  include_content: bool | None = None) -> SessionLogger:
    if include_content is None:
        include_content = os.environ.get("AH_SESSION_LOG_CONTENT") == "1"
    logger = SessionLogger(logs_dir, include_content=include_content)
    global _active
    with _active_lock:
        _active = logger
    logger.emit("session_start", **(extra or {}))
    return logger


def active_session() -> SessionLogger | None:
    with _active_lock:
        return _active


def emit(kind: str, **payload: Any) -> None:
    logger = active_session()
    if logger is not None:
        logger.emit(kind, **payload)


def begin_turn(user_text: str) -> str | None:
    logger = active_session()
    if logger is None:
        return None
    return logger.begin_turn(user_text)


def finish_turn(**payload: Any) -> None:
    logger = active_session()
    if logger is not None:
        logger.finish_turn(**payload)


def current_turn_id() -> str | None:
    logger = active_session()
    if logger is None:
        return None
    return logger.current_turn_id()


def log_llm_request(**payload: Any) -> None:
    logger = active_session()
    if logger is None:
        return
    if logger.include_content and "response_preview" not in payload:
        payload["response_preview"] = protocol_preview(payload.get("response_text"))
    logger.emit("llm_request", **payload)


def audit_tick_result(result: Any) -> None:
    """Emit a full runtime-only decomposition of one Ignition tick, never into AH/H."""
    logger = active_session()
    if logger is None:
        return
    if not logger.include_content:
        tick = int(getattr(result, "tick", -1))
        logger.emit("ignition_tick", tick=tick)
        gc = getattr(result, "gc", None)
        if getattr(gc, "deleted", ()):
            logger.emit("gc_delete", tick=tick, deleted_count=len(gc.deleted))
        lifecycle = getattr(result, "lifecycle", None)
        if getattr(lifecycle, "updates", ()):
            logger.emit("lifecycle_update", tick=tick, update_count=len(lifecycle.updates))
        return
    node_transitions = getattr(result, "node_transitions", ())
    propagations = getattr(result, "propagations", ())
    logger.emit(
        "ignition_tick",
        tick=int(getattr(result, "tick", -1)),
        incoming=dict(getattr(result, "incoming_consumed", {})),
        outgoing=dict(getattr(result, "outgoing_scheduled", {})),
        activation_events=[ref.uid for ref in getattr(result, "activation_events", ())],
        workspace=[ref.uid for ref in getattr(result, "workspace", ())],
        pacemaker_targets=list(getattr(result, "pacemaker_targets", ())),
        nodes=[
            {
                "uid": item.ref.uid,
                "incoming": item.incoming,
                "pacemaker_incoming": item.pacemaker_incoming,
                "seed_reasons": list(item.seed_reasons),
                "before": {
                    "x": item.before.excitation,
                    "output": item.before.output,
                    "activation_event": item.before.activation_event,
                    "decay_age": item.before.decay_age,
                    "decay_origin": item.before.decay_origin_excitation,
                    "first_excitation_tick": item.before.first_excitation_tick,
                    "last_activation_tick": item.before.last_activation_tick,
                    "last_output_tick": item.before.last_output_tick,
                },
                "after": {
                    "x": item.after.excitation,
                    "output": item.after.output,
                    "activation_event": item.after.activation_event,
                    "decay_age": item.after.decay_age,
                    "decay_origin": item.after.decay_origin_excitation,
                    "first_excitation_tick": item.after.first_excitation_tick,
                    "last_activation_tick": item.after.last_activation_tick,
                    "last_output_tick": item.after.last_output_tick,
                },
            }
            for item in node_transitions
        ],
        propagations=[
            {
                "source": item.source.uid,
                "target": item.target.uid,
                "via_uid": item.via_uid,
                "via_kind": item.via_kind,
                "relation": item.relation,
                "amount": item.amount,
            }
            for item in propagations
        ],
        link_weight_updates=list(getattr(result, "link_weight_updates", ())),
        hypernode_weight_updates=list(getattr(result, "hypernode_weight_updates", ())),
    )
    gc = getattr(result, "gc", None)
    if gc is not None and getattr(gc, "deleted", ()):
        logger.emit(
            "gc_delete",
            tick=int(getattr(result, "tick", -1)),
            deleted=list(gc.deleted),
            orphan_deleted=list(getattr(gc, "orphan_deleted", ())),
            reasons=dict(getattr(gc, "reasons", {})),
        )
    lifecycle = getattr(result, "lifecycle", None)
    if lifecycle is not None and getattr(lifecycle, "updates", ()):
        logger.emit(
            "lifecycle_update",
            tick=int(getattr(result, "tick", -1)),
            updates=[
                {
                    "uid": item.uid,
                    "before": None if item.before is None else str(getattr(item.before, "value", item.before)),
                    "after": str(getattr(item.after, "value", item.after)),
                }
                for item in lifecycle.updates
            ],
        )
