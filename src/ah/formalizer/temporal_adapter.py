# -*- coding: utf-8 -*-
"""WP2.6 remainder — TemporalLedger visibility adapter + two-level retraction (V7 §7.4/§8.2).

Bridges the goal/observation channels to effective temporal visibility on a rich assertion record (§17 fields):
``effective_visibility = status LIVE ∧ support-record live ∧ conclusion node F-visible``.

Two-level retraction distinction:
* **(a) path death at a live observation** — the supporting path dies but the source observation is still live, so the
  evidence keeps ``status=LIVE`` and merely loses effective visibility (no RETRACTED write);
* **(b) observation retraction** — writes ``RETRACTED`` to every OBSERVATION-sourced assertion with the matching
  ``source_tag``, regardless of support kind; GOAL_RUN-sourced assertions are NOT retracted by an observation retraction
  (§8.2 step 5).

Pure module; the durable adapter persists records with fsync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TemporalEvidence:
    assertion_id: str
    target_node: str                    # node id (N or G root)
    support_record_id: str
    source: str                         # "OBSERVATION" | "GOAL_RUN"
    source_tag: Optional[tuple] = None  # for OBSERVATION-sourced evidence
    status: str = "LIVE"                # LIVE | RETRACTED


class TemporalAdapter:
    def __init__(self, evidences):
        self.evidences = {e.assertion_id: e for e in evidences}
        self.support_live: dict[str, bool] = {}
        self.node_visible: dict[str, bool] = {}

    def set_support_live(self, support_record_id: str, live: bool) -> None:
        self.support_live[support_record_id] = live

    def set_node_visible(self, node_id: str, visible: bool) -> None:
        self.node_visible[node_id] = visible

    def effective_visibility(self, assertion_id: str) -> bool:
        e = self.evidences[assertion_id]
        if e.status != "LIVE":
            return False
        if not self.support_live.get(e.support_record_id, False):
            return False
        return self.node_visible.get(e.target_node, False)

    def retract_observation(self, tag: tuple) -> list:
        """Two-level (b): RETRACTED on every OBSERVATION-sourced assertion with the matching source_tag; GOAL_RUN untouched."""
        retracted = []
        for e in self.evidences.values():
            if e.source == "OBSERVATION" and e.source_tag == tag and e.status == "LIVE":
                e.status = "RETRACTED"
                retracted.append(e.assertion_id)
        return sorted(retracted)


if __name__ == "__main__":  # pragma: no cover - quick sanity
    ta = TemporalAdapter([TemporalEvidence("a1", "N1", "s1", "OBSERVATION", ("O1", 0))])
    ta.set_support_live("s1", True)
    ta.set_node_visible("N1", True)
    print(ta.effective_visibility("a1"))
