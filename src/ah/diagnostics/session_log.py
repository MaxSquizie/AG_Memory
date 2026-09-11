from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
import json
import uuid

_active_lock = Lock()
_active: SessionLogger | None = None


class SessionLogger:
    """Runtime-only append-only diagnostics. Never enters AH/H."""
    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = Path(logs_dir)
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.jsonl_path = self.logs_dir / f"session-{self.session_id}.jsonl"
        self.text_path = self.logs_dir / f"session-{self.session_id}.log"
        self.latest_jsonl = self.logs_dir / "latest.jsonl"
        self.latest_text = self.logs_dir / "latest.log"
        self._lock = Lock()
        self._disabled = False
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            for path in (self.jsonl_path, self.latest_jsonl, self.text_path, self.latest_text):
                path.write_text("", encoding="utf-8")
        except OSError:
            self._disabled = True

    def emit(self, kind: str, **payload: Any) -> None:
        if self._disabled:
            return
        record = {"ts": datetime.now().astimezone().isoformat(timespec="milliseconds"), "session": self.session_id, "kind": kind, **payload}
        line = json.dumps(record, ensure_ascii=False, default=str)
        summary = f"{record['ts']} {kind} {payload}"
        with self._lock:
            try:
                for path in (self.jsonl_path, self.latest_jsonl):
                    with path.open("a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
                for path in (self.text_path, self.latest_text):
                    with path.open("a", encoding="utf-8") as fh:
                        fh.write(summary + "\n")
            except OSError:
                self._disabled = True


def start_session(logs_dir: Path, *, extra: dict[str, Any] | None = None) -> SessionLogger:
    logger = SessionLogger(logs_dir)
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


def log_llm_request(**payload: Any) -> None:
    emit("llm_request", **payload)


def audit_tick_result(result: Any) -> None:
    """Emit a full runtime-only decomposition of one Ignition tick, never into AH/H."""
    node_transitions = getattr(result, "node_transitions", ())
    propagations = getattr(result, "propagations", ())
    emit(
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
        emit(
            "gc_delete",
            tick=int(getattr(result, "tick", -1)),
            deleted=list(gc.deleted),
            orphan_deleted=list(getattr(gc, "orphan_deleted", ())),
            reasons=dict(getattr(gc, "reasons", {})),
        )
    lifecycle = getattr(result, "lifecycle", None)
    if lifecycle is not None and getattr(lifecycle, "updates", ()):
        emit(
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
