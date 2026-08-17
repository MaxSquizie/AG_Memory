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
    """Append-only session files: full JSONL plus a one-line-per-event .log."""

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
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "session": self.session_id,
            "kind": kind,
            **payload,
        }
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
        except TypeError:
            line = json.dumps({**record, "payload_error": "unserializable"}, ensure_ascii=False, default=str)
        summary = _summary_line(record)
        with self._lock:
            try:
                for path in (self.jsonl_path, self.latest_jsonl):
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write(line + "\n")
                for path in (self.text_path, self.latest_text):
                    with path.open("a", encoding="utf-8") as handle:
                        handle.write(summary + "\n")
            except OSError:
                self._disabled = True


def _preview(value: Any, limit: int = 160) -> str:
    text = "" if value is None else str(value).replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _summary_line(record: dict[str, Any]) -> str:
    kind = str(record.get("kind") or "")
    ts = str(record.get("ts") or "")
    if kind == "llm_request":
        state = "ERROR" if record.get("error") else "OK"
        return (
            f"{ts} llm_request #{record.get('sequence')} role={record.get('role')} {state} "
            f"prompt_chars={record.get('prompt_chars')} response_chars={record.get('response_chars')} "
            f"response={_preview(record.get('response_text'))}"
            + (f" error={record.get('error')}" if record.get("error") else "")
        )
    if kind == "agent_sanitize":
        return (
            f"{ts} agent_sanitize contaminated={record.get('contaminated')} "
            f"cleaned_empty={record.get('cleaned_empty')} action={record.get('action')} "
            f"cleaned={_preview(record.get('cleaned'))}"
        )
    if kind == "agent_repair":
        return (
            f"{ts} agent_repair attempt={record.get('attempt')} "
            f"bad_draft_chars={record.get('bad_draft_chars')} "
            f"cleaned_empty={record.get('cleaned_empty')} "
            f"cleaned={_preview(record.get('cleaned'))}"
        )
    if kind in {"turn_start", "turn_end", "turn_error"}:
        return (
            f"{ts} {kind} user={_preview(record.get('user_text'))} "
            f"response={_preview(record.get('response_text'))} "
            f"error={_preview(record.get('error'))}"
        )
    return f"{ts} {kind} {_preview(record)}"


def start_session(logs_dir: Path, *, extra: dict[str, Any] | None = None) -> SessionLogger:
    """Begin a JSONL session under ``logs_dir``. Previous session stays on disk."""
    logger = SessionLogger(logs_dir)
    with _active_lock:
        global _active
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


def log_llm_request(
    *,
    sequence: int,
    req_id: str,
    role: str,
    prompt: str,
    system: str,
    response_text: str,
    error: str | None = None,
    choice_winner: str | None = None,
    choice_margin: float | None = None,
    choice_outputs: tuple[str, ...] | list[str] | None = None,
) -> None:
    emit(
        "llm_request",
        sequence=sequence,
        req_id=req_id,
        role=role,
        prompt=prompt,
        system=system,
        response_text=response_text,
        error=error,
        choice_winner=choice_winner,
        choice_margin=choice_margin,
        choice_outputs=list(choice_outputs) if choice_outputs else None,
        prompt_chars=len(prompt),
        response_chars=len(response_text or ""),
    )
