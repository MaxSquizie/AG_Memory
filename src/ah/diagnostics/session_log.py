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
    """Emit lifecycle/GC diagnostics for one Ignition tick, never into AH/H."""
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
