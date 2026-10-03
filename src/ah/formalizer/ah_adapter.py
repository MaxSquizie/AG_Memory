# -*- coding: utf-8 -*-
"""Minimal AH adapter for the store contract (R1, WP0.8).

Wraps an :class:`~ah.core.store.AHStore` (reads) + a :class:`~ah.core.journal.JournalChannel`
(durable append-only log) behind the :class:`~ah.formalizer.store_interface.Store` contract so
the R1-critical properties become REAL, not just in-memory:

* atomic durable commit of {plan\\E ops + materialization marker + COMMIT_DECISION D} — one
  fsync'd journal unit; a re-commit with the same ``batch_hash`` is an idempotent no-op.
* recovery-from-D after a crash before APPLIED — :meth:`recover_from_head` restores the decided
  outcome from the durable commit unit WITHOUT re-running admission (``re_admitted`` stays False).
* status retraction without deletion — a durable retraction record + in-memory status mirror.

Scope note (honest): translating arbitrary plan\\E ops into live AHCore graph mutations is a P2
extension point (:meth:`register_op_handler`). In P0 the adapter proves the STORE-LEVEL guarantees
(durable atomic unit, idempotency, recovery-from-D, retraction durability) against a real file;
the full op→graph mapping is filled in when the complete formalizer lands.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from ah.core.journal import JournalChannel

from .store_interface import (
    AssertionStatus,
    CommitDecision,
    CommitResult,
    JournalRecord,
    MaterializationMarker,
    RecoveryReport,
    Store,
    StoreOp,
    TerminalOutcome,
)


def _outcome_to_status(outcome: TerminalOutcome) -> AssertionStatus | None:
    if outcome is TerminalOutcome.APPLIED:
        return AssertionStatus.LIVE
    if outcome is TerminalOutcome.STALE_SUPERSEDED:
        return AssertionStatus.SUPERSEDED
    return None  # a rejected admission creates no assertion status


class AHStoreAdapter(Store):
    """Store contract over an AHStore + durable JournalChannel."""

    def __init__(self, store: Any, journal: JournalChannel, core: Any = None) -> None:
        self._store = store          # object with has_uid / get_element_any_domain (AHStore)
        self._journal = journal      # durable append-only log
        self._core = core           # optional AHCore for applying ops to a live graph
        self._status: dict[str, AssertionStatus] = {}
        self._op_handlers: dict[str, Callable[[Any, dict], Any]] = {}

    def register_op_handler(self, op_type: str, handler: Callable[[Any, dict], Any]) -> None:
        """Register how a plan\\E op type mutates the live store (P2 extension point)."""
        self._op_handlers[op_type] = handler

    # -- journal ----------------------------------------------------------- #
    def append_journal(self, channel: str, record: JournalRecord) -> int:
        return self._journal.append(record.channel, dict(record.payload), run_id=record.run_id)

    def read_global_head(self) -> int:
        return self._journal.read_global_head()

    def scan_unprocessed(self, after_seq: int = 0) -> tuple[JournalRecord, ...]:
        recs = self._journal.scan_unprocessed(after_seq)
        return tuple(
            JournalRecord(r["channel"], r.get("run_id", ""), dict(r.get("payload", {})), seq=r["seq"])
            for r in recs
        )

    # -- commit ------------------------------------------------------------ #
    def commit_transaction(self, plan_ops: Sequence[StoreOp], marker: MaterializationMarker, decision: CommitDecision) -> CommitResult:
        if self._already_committed(decision.batch_hash):
            return CommitResult(self.read_global_head(), (), decision.outcome, idempotent_noop=True)

        applied = self._apply_ops(plan_ops)
        seq = self._journal.append(
            "resolution_log",
            {
                "kind": "commit",
                "batch_hash": decision.batch_hash,
                "run_id": decision.run_id,
                "marker": [marker.observation_id, marker.interpretation_version],
                "ops_digest": decision.ops_digest,
                "outcome": decision.outcome.value,
            },
            run_id=decision.run_id,
        )
        return CommitResult(seq, applied, decision.outcome)

    def _already_committed(self, batch_hash: str) -> bool:
        for r in self._journal.scan_unprocessed(0, channel="resolution_log"):
            p = r.get("payload", {})
            if p.get("kind") == "commit" and p.get("batch_hash") == batch_hash:
                return True
        return False

    def _apply_ops(self, plan_ops: Sequence[StoreOp]) -> tuple[str, ...]:
        uids = [str(op.payload["uid"]) for op in plan_ops if op.payload.get("uid") is not None]
        if self._core is not None and self._op_handlers:
            # Handlers receive an AHCore over the COW transaction store: they may use the clean write API
            # (add_abstract_symbol/add_template/...) or fall back to raw mutation via core.store. The
            # transaction commits on a clean exit and rolls back if any handler raises (§12/§17 op→graph).
            with self._core.transaction() as core:
                for op in plan_ops:
                    handler = self._op_handlers.get(op.op_type)
                    if handler is not None:
                        handler(core, dict(op.payload))
        return tuple(uids)

    # -- terminal / retraction -------------------------------------------- #
    def append_terminal(self, assertion_id: str, outcome: TerminalOutcome, reason: str = "") -> int:
        status = _outcome_to_status(outcome)
        if status is not None:
            self._status[assertion_id] = status
        return self._journal.append(
            "resolution_log",
            {"kind": "terminal", "assertion_id": assertion_id, "outcome": outcome.value, "reason": reason},
        )

    def retract(self, assertion_id: str, new_status: AssertionStatus, reason: str = "") -> bool:
        known = (self._store.has_uid(assertion_id) if hasattr(self._store, "has_uid") else False) \
            or assertion_id in self._status
        if not known:
            return False
        self._status[assertion_id] = new_status  # transition only; never delete
        self._journal.append(
            "resolution_log",
            {"kind": "retract", "assertion_id": assertion_id, "new_status": new_status.value, "reason": reason},
        )
        return True

    def status_of(self, assertion_id: str) -> AssertionStatus | None:
        """Test helper (not part of the Store contract)."""
        return self._status.get(assertion_id)

    # -- recovery ---------------------------------------------------------- #
    def recover_from_head(self) -> RecoveryReport:
        applied_terminals = set()
        commits = []
        for r in self._journal.scan_unprocessed(0, channel="resolution_log"):
            p = r.get("payload", {})
            if p.get("kind") == "terminal" and p.get("outcome") == TerminalOutcome.APPLIED.value:
                applied_terminals.add(p["assertion_id"])
            elif p.get("kind") == "commit":
                commits.append((r, p))

        recovered = []
        for r, p in commits:
            if p.get("outcome") != TerminalOutcome.APPLIED.value:
                continue  # only a decided-APPLIED batch needs restoring after a crash
            aid = f"batch:{p['batch_hash']}"
            if aid not in applied_terminals:
                recovered.append((aid, TerminalOutcome(p["outcome"])))
        return RecoveryReport(tuple(recovered), self.read_global_head(), re_admitted=False)

    # -- read helpers ------------------------------------------------------ #
    def has_uid(self, uid: str) -> bool:
        return self._store.has_uid(uid)

    def get_element_any_domain(self, uid: str):
        return self._store.get_element_any_domain(uid)
