# -*- coding: utf-8 -*-
"""Append-only durable journal — the missing AH durability primitive (V7 §7.2).

AH's existing persistence is snapshot-based (:class:`ah.core.persistence.JsonPersistence`):
it rewrites the whole store atomically with fsync, but it has NO append-only log and no
per-record durability. V7 needs a two-channel journal (observation / resolution_log) whose
records survive a crash so that T5 pre-commit records and terminal outcomes can be replayed
and recovery can restore a committed outcome from COMMIT_DECISION D without re-admission.

Design (kept minimal on purpose — no new monolith):
* ONE physical append-only log file; the two channels are logical partitions of it, each
  record tagged with its ``channel``. A single total order (monotonic ``seq``) drives
  head-only admission and recovery ordering.
* Every append is flushed and fsynced before :meth:`append` returns, so a returned seq is
  durable.
* Crash safety: on open / :meth:`recover`, the log is scanned; the longest prefix of lines
  that parse as well-formed records is kept, any trailing torn line (a crash mid-write) is
  dropped by rewriting the file with only the valid prefix, and ``head`` is derived from the
  surviving records — never from a separate counter that could lie after a crash.

This module is AH-core infrastructure; the formalizer's :class:`ah_adapter` wraps it behind
the :class:`~ah.formalizer.store_interface.Store` contract.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _fsync_dir_best_effort(path: Path) -> None:
    """Fsync the containing directory (new-file durability). Best-effort on Windows."""
    try:
        dfd = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dfd)
    except OSError:
        pass
    finally:
        os.close(dfd)


class JournalChannel:
    """A single append-only durable log with logical observation/resolution channels."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self._path.exists()
        if is_new:
            self._path.touch()
            _fsync_dir_best_effort(self._path)
        self._head = self.recover()

    # -- durability primitives -------------------------------------------- #
    def append(self, channel: str, payload: dict[str, Any], run_id: str = "") -> int:
        """Append one record and fsync it; return its durable ``seq``."""
        self._head += 1
        rec = {"seq": self._head, "channel": channel, "run_id": run_id, "payload": payload}
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        return self._head

    def read_global_head(self) -> int:
        """Highest durable seq (0 if the log is empty)."""
        return self._head

    def scan_unprocessed(self, after_seq: int = 0, channel: str | None = None) -> list[dict[str, Any]]:
        """Records with ``seq > after_seq`` in ascending order; optionally one channel."""
        out = []
        for rec in self._iter_valid():
            if rec["seq"] <= after_seq:
                continue
            if channel is not None and rec["channel"] != channel:
                continue
            out.append(rec)
        return sorted(out, key=lambda r: r["seq"])

    def recover(self) -> int:
        """Drop any trailing torn line and re-derive ``head`` from surviving records.

        Returns the recovered head seq. Safe to call on open and after a simulated crash.
        """
        raw = self._path.read_text(encoding="utf-8") if self._path.exists() else ""
        lines = [ln for ln in raw.split("\n") if ln.strip() != ""]
        valid: list[str] = []
        head = 0
        torn_tail = False
        for ln in lines:
            try:
                rec = json.loads(ln)
            except (json.JSONDecodeError, ValueError):
                torn_tail = True  # first unparseable line starts the torn tail
                break
            if not isinstance(rec, dict) or "seq" not in rec:
                torn_tail = True
                break
            valid.append(ln)
            head = max(head, int(rec["seq"]))

        if torn_tail and len(valid) != len(lines):
            # Rewrite with only the valid prefix so future appends are clean.
            data = "".join(v + "\n" for v in valid)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(str(tmp), str(self._path))
            _fsync_dir_best_effort(self._path)

        self._head = head
        return head

    # -- internals --------------------------------------------------------- #
    def _iter_valid(self):
        if not self._path.exists():
            return
        for ln in self._path.read_text(encoding="utf-8").split("\n"):
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except (json.JSONDecodeError, ValueError):
                break  # torn tail — stop at first unparseable line
            if isinstance(rec, dict) and "seq" in rec:
                yield rec

    @property
    def path(self) -> Path:
        return self._path
