# -*- coding: utf-8 -*-
"""MemoryStore — in-memory double of :class:`Store` (R1, WP0.7).

Exists ONLY to unit-test PURE decisions fast (head-only admission, plan\\E
computation, terminal-outcome selection) without touching AH core or disk.

Honest limitation (see store_interface docstring): this double applies operations
in memory and has NO crash window, so it CANNOT demonstrate the two properties that
only a real store can — atomic durable commit of {ops + marker + D} and recovery-from-D
after a crash before APPLIED. Those are proven exclusively by the AH adapter with
crash-stop runs (WP2.9). Do not declare P2 passed on this double.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence

from .store_interface import (
    AssertionStatus,
    CommitDecision,
    CommitResult,
    JournalRecord,
    RecoveryReport,
    Store,
    StoreOp,
    TerminalOutcome,
)


class MemoryStore(Store):
    """In-memory implementation of the store contract for pure-decision tests."""

    def __init__(self) -> None:
        self._channels: dict[str, list[JournalRecord]] = {}
        self._seq = 0                 # global monotonic seq counter (admission order basis)
        self._elements: dict[str, Any] = {}   # uid -> opaque payload (from applied ops)
        self._status: dict[str, AssertionStatus] = {}
        self._known: set[str] = set()         # assertion/element uids ever materialized
        self._committed_hashes: set[str] = set()

    # -- journal ----------------------------------------------------------- #
    def append_journal(self, channel: str, record: JournalRecord) -> int:
        self._seq += 1
        rec = replace(record, seq=self._seq)
        self._channels.setdefault(channel, []).append(rec)
        return self._seq

    def read_global_head(self) -> int:
        return self._seq

    def scan_unprocessed(self, after_seq: int) -> tuple[JournalRecord, ...]:
        recs = [r for ch in self._channels.values() for r in ch]
        return tuple(sorted((r for r in recs if r.seq > after_seq), key=lambda r: r.seq))

    # -- commit ------------------------------------------------------------ #
    def commit_transaction(
        self, plan_ops: Sequence[StoreOp], marker, decision: CommitDecision
    ) -> CommitResult:
        if decision.batch_hash in self._committed_hashes:
            return CommitResult(self._seq, (), decision.outcome, idempotent_noop=True)

        applied = []
        for op in plan_ops:
            uid = op.payload.get("uid")
            if uid is not None:
                self._elements[uid] = op.payload
                self._known.add(uid)
                applied.append(str(uid))
        unit = JournalRecord(
            channel="resolution_log",
            run_id=decision.run_id,
            payload={
                "marker": (marker.observation_id, marker.interpretation_version),
                "ops_digest": decision.ops_digest,
                "outcome": decision.outcome.value,
            },
        )
        seq = self.append_journal("resolution_log", unit)
        self._committed_hashes.add(decision.batch_hash)
        return CommitResult(seq, tuple(applied), decision.outcome)

    # -- terminal / retraction -------------------------------------------- #
    def append_terminal(self, assertion_id: str, outcome: TerminalOutcome, reason: str = "") -> int:
        self._known.add(assertion_id)
        if outcome is TerminalOutcome.APPLIED:
            self._status.setdefault(assertion_id, AssertionStatus.LIVE)
        elif outcome is TerminalOutcome.STALE_SUPERSEDED:
            self._status[assertion_id] = AssertionStatus.SUPERSEDED
        rec = JournalRecord(
            channel="resolution_log",
            run_id="",
            payload={"assertion_id": assertion_id, "outcome": outcome.value, "reason": reason},
        )
        return self.append_journal("resolution_log", rec)

    def retract(self, assertion_id: str, new_status: AssertionStatus, reason: str = "") -> bool:
        if assertion_id not in self._known and assertion_id not in self._status:
            return False
        self._status[assertion_id] = new_status  # transition only; never delete
        rec = JournalRecord(
            channel="resolution_log",
            run_id="",
            payload={"assertion_id": assertion_id, "new_status": new_status.value, "reason": reason},
        )
        self.append_journal("resolution_log", rec)
        return True

    def status_of(self, assertion_id: str) -> AssertionStatus | None:
        """Test helper (not part of the Store contract)."""
        return self._status.get(assertion_id)

    # -- recovery ---------------------------------------------------------- #
    def recover_from_head(self) -> RecoveryReport:
        # No crash window in memory: nothing to restore. Real recovery is AH-only.
        return RecoveryReport(recovered=(), drained_to_seq=self.read_global_head())

    # -- read helpers ------------------------------------------------------ #
    def has_uid(self, uid: str) -> bool:
        return uid in self._elements

    def get_element_any_domain(self, uid: str):
        return self._elements.get(uid)
