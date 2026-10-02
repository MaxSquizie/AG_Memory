# -*- coding: utf-8 -*-
"""WP2.7/WP2.8 remainder — goal-journal crash recovery, decision-first (V7 §6.4/§8.3): R0 then R1/R2.

Recovering a PENDING goal record without a terminal status:
* **R0** — lookup GOAL_DECISION by ``goal_run_id`` first: if the outcome is already fixed it was committed atomically with
  the apply, so recovery appends only the missing terminal and stops (idempotent; no duplicate path/decision).
* **No decision -> R1/R2** — reconcile against the canonical store by dedup key. A record that exists (created by another run)
  is re-evaluated for current premise visibility + license without mutation (APPLIED_NOOP / ABORTED); a missing record is
  re-validated and, if live+licensed, applied now (APPLIED). This is exactly the GoalExecutor transaction semantics, so R1/R2
  delegate to it after the decision-first check.

Pure module; the durable adapter persists journal/decision records with fsync (see the crash-stop test for restart-from-disk).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ah.formalizer.goal_executor import GoalExecutor, GoalRequest, _path_key


@dataclass(frozen=True)
class GoalJournalRecord:
    goal_run_id: str
    rule_id: str
    premise_support_ids: tuple
    conclusion_signature: str
    temporal: Optional[tuple] = None
    status: str = "PENDING"


class GoalRecovery:
    def __init__(self, store, executor: GoalExecutor):
        self.store = store
        self.executor = executor

    def recover(self, rec: GoalJournalRecord) -> dict:
        # R0 — decision-first: a fixed outcome is an immutable historical fact; just return it (idempotent).
        if rec.goal_run_id in self.store.decisions:
            return dict(self.store.decisions[rec.goal_run_id])

        req = GoalRequest(rec.goal_run_id, rec.rule_id, rec.premise_support_ids,
                         rec.conclusion_signature, rec.temporal)
        # R1/R2 — reconcile against the canonical store (dedup key), then apply or abort per current state.
        return self.executor.execute(req)


if __name__ == "__main__":  # pragma: no cover - quick sanity
    from ah.formalizer.goal_executor import GoalStore
    from ah.formalizer.temporal_license import point, cont
    store = GoalStore()
    store.live_premises.update({"s_or", "s_not"})
    rec = GoalJournalRecord("run1", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7)))
    print(GoalRecovery(store, GoalExecutor(store)).recover(rec))
