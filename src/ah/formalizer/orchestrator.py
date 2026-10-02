# -*- coding: utf-8 -*-
"""P2 integration core — Orchestrator composing the built cores on ONE canonical store (V7 §6.4/§8.1/§8.3).

A support path is live while at least one of its backing observations has not been retracted (reference counting): retracting an
observation kills a premise only when it was the last live backer. The goal channel's store shares the exact ``live_supports``
set, so an observation-channel retraction propagates to a dependent goal (its premise dies -> the pending goal recovers as
ABORTED{GOAL_PREMISES_STALE}).

This is the executable seam for the DR vertical traces: it proves the isolated cores (T6b retraction + GoalExecutor + decision-first
recovery) compose correctly on one store, rather than only in isolation. The full 31-trace harness extends this orchestrator with
T5 batch commit and kill points wired to the same ``live_supports`` seam.

Pure module; durable persistence (fsync journal/decisions + restart-from-disk) is proven separately by the crash-stop test.
"""

from __future__ import annotations

from ah.formalizer.goal_executor import GoalExecutor, GoalRequest, GoalStore
from ah.formalizer.recovery import GoalJournalRecord, GoalRecovery


class Orchestrator:
    def __init__(self):
        self.live_supports: set = set()                 # single source of truth for premise liveness
        self.support_backers: dict[str, set] = {}       # support_id -> {observation tags}
        self.retracted: set = set()                    # retracted observation tags
        self.goal_store = GoalStore()
        self.goal_store.live_premises = self.live_supports   # the goal channel shares this exact set
        self.executor = GoalExecutor(self.goal_store)
        self.recovery = GoalRecovery(self.goal_store, self.executor)

    def register_observation(self, tag: tuple, support_ids) -> None:
        for sid in support_ids:
            self.support_backers.setdefault(sid, set()).add(tag)
            if any(t not in self.retracted for t in self.support_backers[sid]):
                self.live_supports.add(sid)

    def retract_observation(self, tag: tuple) -> list:
        """T6b-style retraction: a premise dies only when this was its last live backer."""
        self.retracted.add(tag)
        killed = []
        for sid, tags in self.support_backers.items():
            if tag in tags and not any(t not in self.retracted for t in tags):
                if sid in self.live_supports:
                    self.live_supports.discard(sid)
                    killed.append(sid)
        return sorted(killed)

    def run_goal(self, req: GoalRequest) -> dict:
        return self.executor.execute(req)

    def recover(self, rec: GoalJournalRecord) -> dict:
        return self.recovery.recover(rec)


if __name__ == "__main__":  # pragma: no cover - quick sanity
    from ah.formalizer.temporal_license import point, cont
    o = Orchestrator()
    o.register_observation(("O1", 0), {"s_or", "s_not"})
    print(o.run_goal(GoalRequest("r1", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7)))))
