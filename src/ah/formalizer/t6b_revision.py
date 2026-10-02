# -*- coding: utf-8 -*-
"""WP2.7 — T6b retraction cascade + two-level distinction + conflict-report closing (V7 §8.1/§8.2).

Builds on the WP2.4 proof graph for node/support liveness and adds the observation/assertion/report layer with its
state-transition tables:

* **State transitions** — ObservationRecord and TimeAssertion move LIVE -> RETRACTED or LIVE -> SUPERSEDED; terminal
  states have no outgoing transition (an illegal one raises ``InvalidTransition``).
* **Observation-level retraction** (§8.2, case b) writes status=RETRACTED to *every* TimeAssertion carrying the matching
  source_tag (ROOT and DERIVED alike), invalidates that observation's root supports in the graph (cascading orphaned
  nodes to SUPERSEDED), then closes any conflict report whose evidence lost effective visibility.
* **Path death at a live observation** (§8.2, case a) — retracting a *different* observation kills an upstream premise
  path; the affected assertion (grounded by the still-LIVE observation) stays LIVE in the ledger with no RETRACTED write
  ("переписываний нет"), but loses effective visibility and its report closes. This is the two-level distinction the
  contract requires: retraction writes status; path death only recomputes derived state on read.
* **Conflict-report closing** — a report is OPEN iff all its evidence assertions are effectively visible (LIVE + live,
  complete support path); it closes idempotently by report_id when any evidence loses visibility.

Pure module: in-memory model for the retraction protocol; the durable journal / fsync batch is the store adapter's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ah.formalizer.support_som import Node, SupportRecord, ProofGraph


class InvalidTransition(ValueError):
    """A state transition outside the §8.1 tables."""


# §8.1 — allowed status transitions per record kind (terminal states have no outgoing edge).
_TRANSITIONS = {
    "observation": {"LIVE": {"RETRACTED", "SUPERSEDED"}, "RETRACTED": set(), "SUPERSEDED": set()},
    "assertion":   {"LIVE": {"RETRACTED", "SUPERSEDED"}, "RETRACTED": set(), "SUPERSEDED": set()},
}


def _transition(kind: str, current: str, new: str) -> None:
    if new not in _TRANSITIONS[kind].get(current, set()):
        raise InvalidTransition(f"{kind}: {current} -> {new}")


@dataclass
class ObservationRec:
    obs_id: str
    version: int = 0
    status: str = "LIVE"

    @property
    def tag(self):
        return (self.obs_id, self.version)


@dataclass
class TimeAssertionRec:
    assertion_id: str
    source_tag: tuple          # the observation that grounds it (obs_id, version)
    node_id: str              # the N/G node it dates
    support_record_id: str    # the SupportRecord whose liveness gates effective visibility
    status: str = "LIVE"


@dataclass
class ConflictReportRec:
    report_id: str
    evidence: tuple           # assertion_ids that keep the report open
    closed_by: Optional[str] = None   # None=OPEN, else RETRACTION|SUPERSEDE|CLARIFICATION


class RevisionLedger:
    def __init__(self, graph: ProofGraph):
        self.graph = graph
        self.observations: dict[str, ObservationRec] = {}
        self.assertions: dict[str, TimeAssertionRec] = {}
        self.reports: dict[str, ConflictReportRec] = {}

    # -- registration ---------------------------------------------------------
    def register_observation(self, obs_id: str, version: int = 0) -> ObservationRec:
        rec = ObservationRec(obs_id=obs_id, version=version)
        self.observations[obs_id] = rec
        return rec

    def add_assertion(self, assertion_id: str, source_tag: tuple, node_id: str, support_record_id: str) -> TimeAssertionRec:
        rec = TimeAssertionRec(assertion_id=assertion_id, source_tag=source_tag, node_id=node_id,
                               support_record_id=support_record_id)
        self.assertions[assertion_id] = rec
        return rec

    def add_report(self, report_id: str, evidence) -> ConflictReportRec:
        rec = ConflictReportRec(report_id=report_id, evidence=tuple(evidence))
        self.reports[report_id] = rec
        return rec

    # -- effective visibility -------------------------------------------------
    def _find_support(self, record_id: str) -> Optional[SupportRecord]:
        for node in self.graph.nodes.values():
            for rec in node.supports:
                if rec.record_id == record_id:
                    return rec
        return None

    def effective_visibility(self, assertion_id: str) -> bool:
        """LIVE + a live, complete support path (the conclusion node is F-visible)."""
        a = self.assertions[assertion_id]
        if a.status != "LIVE":
            return False
        rec = self._find_support(a.support_record_id)
        if rec is None or rec.status != "LIVE":
            return False
        return a.node_id in self.graph.f_visible()

    # -- retraction protocol --------------------------------------------------
    def retract_observation(self, obs_id: str, version: int = 0) -> dict:
        """§8.2 case (b): observation-level retraction — writes RETRACTED to its assertions + invalidates root supports."""
        obs = self.observations[obs_id]
        tag = (obs_id, version)
        _transition("observation", obs.status, "RETRACTED")
        obs.status = "RETRACTED"

        superseded = self.graph.retract(tag)          # invalidate this observation's root supports + cascade nodes

        retracted = []
        for a in self.assertions.values():           # every assertion with the matching source_tag (ROOT and DERIVED)
            if a.source_tag == tag and a.status == "LIVE":
                _transition("assertion", a.status, "RETRACTED")
                a.status = "RETRACTED"
                retracted.append(a.assertion_id)

        closed = self._close_reports()
        return {"observation": obs_id, "superseded_nodes": sorted(superseded),
                "retracted_assertions": sorted(retracted), "closed_reports": sorted(closed)}

    def supersede_observation(self, obs_id: str, version: int = 0) -> list:
        """Atomic visible-version switch (LIVE -> SUPERSEDED): invalidate the old version's supports + assertions."""
        obs = self.observations[obs_id]
        tag = (obs_id, version)
        _transition("observation", obs.status, "SUPERSEDED")
        obs.status = "SUPERSEDED"

        self.graph.retract(tag)
        for a in self.assertions.values():
            if a.source_tag == tag and a.status == "LIVE":
                _transition("assertion", a.status, "SUPERSEDED")
                a.status = "SUPERSEDED"
        return sorted(self._close_reports())

    def _close_reports(self) -> list:
        """Close every OPEN report whose evidence lost effective visibility; idempotent by report_id."""
        closed = []
        for r in self.reports.values():
            if r.closed_by is not None:
                continue                                   # already closed — no second write
            if any(not self.effective_visibility(e) for e in r.evidence):
                r.closed_by = "RETRACTION"
                closed.append(r.report_id)
        return closed


if __name__ == "__main__":  # pragma: no cover - quick sanity
    g = ProofGraph()
    g.add_node(Node("p", "N", True))
    rec = g.add_root_support("p", "O", tag=("O1", 0), record_id="s1")
    led = RevisionLedger(g)
    led.register_observation("O1")
    led.add_assertion("A1", ("O1", 0), "p", rec.record_id)
    print(led.retract_observation("O1"))
