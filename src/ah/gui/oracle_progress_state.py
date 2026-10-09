"""Incremental oracle stdout framing and observable run state (no Qt)."""
from __future__ import annotations

import codecs
from dataclasses import dataclass, field
import json
import time

PREFIX = "V7_PROGRESS "


class OracleOutputParser:
    """QProcess chunks are neither UTF-8 characters nor complete JSON lines."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pending = ""

    def feed(self, chunk: bytes, *, final: bool = False) -> tuple[list[dict], list[str]]:
        self._pending += self._decoder.decode(chunk, final=final)
        lines = self._pending.split("\n")
        self._pending = lines.pop()
        if final and self._pending:
            lines.append(self._pending)
            self._pending = ""
        events, logs = [], []
        for line in lines:
            if line.startswith(PREFIX):
                try:
                    event = json.loads(line[len(PREFIX):])
                    if not isinstance(event, dict) or event.get("schema_version") != "v7-oracle-progress-1":
                        raise ValueError("unsupported progress event")
                    events.append(event)
                except (ValueError, TypeError):
                    logs.append("Invalid oracle progress event: " + line[:500])
            elif line.strip():
                logs.append(line)
        # Never let an accidental non-line stderr stream consume unbounded RAM.
        if len(self._pending) > 2_000_000:
            logs.append("Oversized incomplete oracle output: " + self._pending[:500])
            self._pending = ""
        return events, logs


@dataclass
class OracleProgressState:
    started_at: float = field(default_factory=time.monotonic)
    last_seq: int = -1
    completed: int = 0
    total: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    requests_started: int = 0
    requests_finished: int = 0
    requests_failed: int = 0
    case_id: str = ""
    action: str = ""
    active_request_at: float | None = None
    finished: bool = False
    finished_at: float | None = None

    def apply(self, event: dict, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        seq = event.get("seq")
        if not isinstance(seq, int) or seq <= self.last_seq:
            return False
        self.last_seq = seq
        for name in ("completed", "total", "passed", "failed", "blocked", "requests_started", "requests_finished", "requests_failed"):
            value = event.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                setattr(self, name, value)
        self.case_id = str(event.get("case_id", self.case_id))
        self.action = str(event.get("action", self.action))
        kind = event.get("event")
        if kind == "request_started":
            self.active_request_at = now
        elif kind == "request_finished":
            self.active_request_at = None
        elif kind == "case_started":
            self.action = ""
        elif kind == "run_finished":
            self.finished = True
            self.finished_at = now
            self.active_request_at = None
        return True

    def text(self, *, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        elapsed = max(0, (self.finished_at if self.finished_at is not None else now) - self.started_at)
        text = (f"Кейсы {self.completed}/{self.total or '?'} · PASS {self.passed} / FAIL {self.failed} / BLOCKED {self.blocked}"
                f" | Запросы {self.requests_finished}/{self.requests_started}, ошибок {self.requests_failed} | {elapsed:.0f} с")
        if not self.finished:
            if self.case_id:
                text += f" | {self.case_id} / {self.action or 'подготовка'}"
            if self.active_request_at is not None:
                text += f" | ожидание модели {max(0, now - self.active_request_at):.0f} с"
        return text
