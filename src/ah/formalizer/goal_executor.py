# -*- coding: utf-8 -*-
"""WP2.8 — GoalExecutor goal transaction (V7 §6.4/§7.5): append-only derived N/G + AddDerivedSupport, on-demand rules,
GOAL_DECISION record, DB-N race serialization, idempotency by goal_run_id.

The executable core of the goal channel:

* **Idempotency** — a lookup by ``goal_run_id`` precedes any write; exactly one GOAL_DECISION and one terminal status per
  run (a re-execution returns the fixed decision without new records). A recorded decision is an immutable historical fact:
  a later retraction supersedes the *node* by cascade but never rewrites the decision.
* **Preflight license** — read-only temporal license for OR_ELIMINATION / FORALL_INST via ``temporal_license`` (§6.3/§7.4);
  failure -> ABORTED{GOAL_LICENSE_FAILED} with no node/path created (pre-PENDING detection returns UNKNOWN to the caller).
* **Premise liveness re-checked inside the atomic transaction** — a premise that dies between preflight and apply (a
  concurrent retraction commit, modeled by an ``interleave`` hook) -> ABORTED{GOAL_PREMISES_STALE} with no partial records.
* **Dedup** — path key = (rule_id, sorted premise support ids, conclusion_signature). A hit whose premises are still live
  -> APPLIED_NOOP (no new path/TimeAssertion); a hit whose premises died -> ABORTED{GOAL_PREMISES_STALE} (the existing path
  is already invalidated by the §8.2 cascade; it is not resurrected and no duplicate is created).
* **Fresh + licensed + live** -> node-level dedup (EnsureNode) + AddDerivedSupport atomically with GOAL_DECISION{APPLIED,
  conclusion_ref} in the same commit boundary -> terminal APPLIED{created=true}.

Pure module: an in-memory store stands in for the canonical store; the durable journal / fsync batch is the adapter's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ah.formalizer.temporal_license import (
    or_elimination_license, forall_inst_license,
)


@dataclass(frozen=True)
class GoalRequest:
    goal_run_id: str
    rule_id: str                       # "OR_ELIMINATION" | "FORALL_INST"
    premise_support_ids: tuple         # support ids that must be live at apply time
    conclusion_signature: str          # canonical content signature (node + path dedup)
    temporal: Optional[tuple] = None   # regions for licensing, e.g. (w_or, w_not) / (w_interval, w_instance)


@dataclass
class PathRecord:
    record_id: str
    rule_id: str
    premise_support_ids: tuple
    node_id: str
    status: str = "LIVE"


def _path_key(req: GoalRequest):
    return (req.rule_id, tuple(sorted(req.premise_support_ids)), req.conclusion_signature)


class GoalStore:
    """In-memory stand-in for the canonical store's goal channel."""

    def __init__(self):
        self.nodes: dict[str, str] = {}          # conclusion_signature -> node_id (node-level dedup)
        self._next_node = 0
        self.paths: dict[tuple, PathRecord] = {}  # path_key -> record (path-level dedup)
        self.live_premises: set = set()          # support ids currently live (mutable to simulate retraction)
        self.decisions: dict[str, dict] = {}     # goal_run_id -> GOAL_DECISION (exactly one per run)
        self.terminals: list = []               # append-only terminal status audit

    def ensure_node(self, signature: str) -> str:
        if signature not in self.nodes:          # node-level dedup: a duplicate N is not created
            self._next_node += 1
            self.nodes[signature] = f"N{self._next_node}"
        return self.nodes[signature]

    def retract_premise(self, support_id: str) -> None:
        """Simulate a concurrent retraction commit (the premise path dies)."""
        self.live_premises.discard(support_id)


class GoalExecutor:
    def __init__(self, store: GoalStore):
        self.store = store

    def execute(self, req: GoalRequest, interleave: Optional[Callable] = None) -> dict:
        # Idempotency: lookup by goal_run_id precedes any write; a re-execution returns the fixed decision.
        if req.goal_run_id in self.store.decisions:
            return dict(self.store.decisions[req.goal_run_id])

        # (2) read-only preflight license (§6.3/§7.4). Failure -> ABORTED{GOAL_LICENSE_FAILED}, no node/path.
        lic = self._license(req)
        if lic is not None and lic.status != "LICENSED":
            return self._decide(req, "ABORTED", reason="GOAL_LICENSE_FAILED")

        # A concurrent retraction may commit here (between preflight and the atomic apply).
        if interleave is not None:
            interleave()

        key = _path_key(req)
        existing = self.store.paths.get(key)
        dead = [p for p in req.premise_support_ids if p not in self.store.live_premises]

        if existing is not None:
            # Dedup hit: re-evaluate the EXISTING path's premises (DB-N). A dead premise -> do not resurrect.
            dead_existing = [p for p in existing.premise_support_ids if p not in self.store.live_premises]
            if dead or dead_existing:
                return self._decide(req, "ABORTED", reason="GOAL_PREMISES_STALE")
            return self._decide(req, "APPLIED_NOOP", conclusion_ref=existing.node_id)

        if dead:                                # premise died inside the transaction -> no partial records
            return self._decide(req, "ABORTED", reason="GOAL_PREMISES_STALE")

        # Fresh + licensed + live: node (dedup) + AddDerivedSupport atomically with GOAL_DECISION{APPLIED}.
        node_id = self.store.ensure_node(req.conclusion_signature)
        rec = PathRecord(record_id=f"DS{len(self.store.paths) + 1}", rule_id=req.rule_id,
                         premise_support_ids=tuple(sorted(req.premise_support_ids)), node_id=node_id)
        self.store.paths[key] = rec
        return self._decide(req, "APPLIED", conclusion_ref=node_id)

    def _license(self, req: GoalRequest):
        if req.temporal is None:                # undated -> no temporal constraint
            return None
        a, b = req.temporal
        if req.rule_id == "OR_ELIMINATION":
            return or_elimination_license(a, b)
        if req.rule_id == "FORALL_INST":
            return forall_inst_license(a, b)
        return None

    def _decide(self, req: GoalRequest, outcome: str, reason: Optional[str] = None,
                conclusion_ref: Optional[str] = None) -> dict:
        rec = {"goal_run_id": req.goal_run_id, "outcome": outcome}
        if reason is not None:
            rec["reason"] = reason
        if conclusion_ref is not None:
            rec["conclusion_ref"] = conclusion_ref
        self.store.decisions[req.goal_run_id] = rec          # exactly one per run (idempotent)
        terminal = {"goal_run_id": req.goal_run_id, "status": outcome}
        if reason is not None:
            terminal["reason"] = reason
        if conclusion_ref is not None:
            terminal["conclusion_ref"] = conclusion_ref
        self.store.terminals.append(terminal)                # append-only audit
        return dict(rec)


if __name__ == "__main__":  # pragma: no cover - quick sanity
    from ah.formalizer.temporal_license import point, cont
    store = GoalStore()
    store.live_premises.update({"s_or", "s_not"})
    ex = GoalExecutor(store)
    print(ex.execute(GoalRequest("run1", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7)))))
