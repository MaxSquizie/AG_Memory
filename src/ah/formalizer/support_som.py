# -*- coding: utf-8 -*-
"""WP2.4 — support ledger + SOM invariant (V7 §7.4/§7.5): the proof-graph liveness core.

Encodes, on a pure in-memory proof graph, the two independent visibility notions and the retraction cascade:

* **Direct support** ``add_root_support`` — an asserted proposition (N or G root) gets its own O/C/W ground from
  the span that asserts it. R/D/M/A/P are interpretation grounds only and are NEVER written as fact support (§7.4);
  a NOT(P) root rests on "not P", not on N(P)'s support.
* **Derived support** ``add_derived_support`` — a rule conclusion (commit-time AND_ELIMINATION; on-demand
  OR_ELIMINATION/FORALL_INST by the goal executor) is valid while at least one complete proof path exists: all its
  premises are F-visible and their own supports/paths alive. Retraction of a premise breaks only that path.
* **S-accessible vs F-visible** (§7.5): an asserted node is *F-visible* iff it has >=1 live, complete support; a
  structural operand (unasserted) is *S-accessible* iff it reaches a live UsageLink chain to an F-visible ancestor —
  but it is never F-visible by itself until it gains its own path. Both are computed as monotone fixpoints (cycle-safe).
* **Retraction cascade** ``retract``: invalidating an observation's tag SUPERSEDES its root supports; the fixpoint
  then propagates derived-path deaths, and any asserted node left with no live support is marked SUPERSEDED (orphaned),
  while a node that lost only a structural link but keeps its own live path stays F-visible.

Pure module: it mutates an in-memory graph and returns liveness results; the store adapter persists these transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

FACT_GROUNDS = frozenset({"O", "C", "W"})          # only these assert a fact (§7.4)
INTERPRETATION_ONLY = frozenset({"R", "D", "M", "A", "P"})  # never written as fact support


class InvalidFactGround(ValueError):
    """Raised when an interpretation-only ground (R/D/M/A/P) is offered as a fact's direct support."""


@dataclass
class SupportRecord:
    record_id: str
    conclusion_ref: str          # node id this supports
    kind: str                   # "ROOT" | "DERIVED"
    ground_type: str | None = None   # O/C/W for ROOT; None for DERIVED
    rule_id: str | None = None       # for DERIVED
    premises: tuple[str, ...] = ()   # node ids (for DERIVED)
    tag: tuple[str, int] = ("", 0)   # (observation_id, interpretation_version)
    status: str = "LIVE"             # LIVE | SUPERSEDED
    binding_refs: tuple[str, ...] = ()
    temporal_assertion_refs: tuple[str, ...] = ()


@dataclass
class Node:
    node_id: str
    kind: str                       # "N" | "G"
    asserted: bool                  # True if it is an asserted root (makes its own claim)
    supports: list[SupportRecord] = field(default_factory=list)
    usage_links: dict[str, str] = field(default_factory=dict)  # parent_node_id -> LIVE|SUPERSEDED
    status: str = "LIVE"            # LIVE | SUPERSEDED


class ProofGraph:
    """A minimal in-memory proof graph over asserted nodes and unasserted structural operands."""

    def __init__(self, nodes: Sequence[Node] = ()) -> None:
        self.nodes: dict[str, Node] = {n.node_id: n for n in nodes}
        self.binding_status: dict[str, str] = {}
        self.assertion_status: dict[str, str] = {}
        self.audit: list[dict] = []

    def add_node(self, node: Node) -> None:
        self.nodes[node.node_id] = node

    def effective_supports(self) -> set[str]:
        records = {r.record_id: r for n in self.nodes.values() for r in n.supports}
        live: set[str] = set()
        while True:
            new = {rid for rid, r in records.items() if r.status == "LIVE"
                   and all(self.binding_status.get(b, "INVALID") == "LIVE" for b in r.binding_refs)
                   and all(self.assertion_status.get(a, "RETRACTED") == "LIVE" for a in r.temporal_assertion_refs)
                   and ((r.kind == "ROOT" and r.ground_type in FACT_GROUNDS)
                        or (r.kind == "DERIVED" and bool(r.premises) and all(p in live for p in r.premises)))}
            if new <= live:
                return live
            live.update(new)

    # -- support writers ---------------------------------------------------- #
    def add_root_support(self, node_id: str, ground_type: str, tag: tuple[str, int], record_id: str) -> SupportRecord:
        """Attach a direct O/C/W support. R/D/M/A/P are rejected (they never assert a fact)."""
        if ground_type not in FACT_GROUNDS:
            raise InvalidFactGround(f"{ground_type!r} is an interpretation ground, not a fact ground")
        existing = next((r for r in self.nodes[node_id].supports if r.record_id == record_id), None)
        if existing is not None:
            return existing
        self.nodes[node_id].status = "LIVE"
        rec = SupportRecord(record_id=record_id, conclusion_ref=node_id, kind="ROOT",
                           ground_type=ground_type, tag=tag)
        self.nodes[node_id].supports.append(rec)
        return rec

    def add_derived_support(self, node_id: str, rule_id: str, premises: Sequence[str],
                           tag: tuple[str, int], record_id: str) -> SupportRecord:
        """Attach a derived path (valid while all its premises stay F-visible)."""
        rec = SupportRecord(record_id=record_id, conclusion_ref=node_id, kind="DERIVED",
                           rule_id=rule_id, premises=tuple(premises), tag=tag)
        self.nodes[node_id].supports.append(rec)
        return rec

    # -- liveness (monotone fixpoints, cycle-safe) -------------------------- #
    def f_visible(self) -> set[str]:
        """Nodes with >=1 live, complete support. A DERIVED path is complete iff all its premises are F-visible."""
        paths = self.effective_supports()
        return {n.node_id for n in self.nodes.values() if any(r.record_id in paths for r in n.supports)}

    def s_accessible(self, fvis: set[str] | None = None) -> set[str]:
        """Nodes reachable by a live UsageLink chain to an F-visible ancestor (or F-visible themselves)."""
        fvis = self.f_visible() if fvis is None else fvis
        acc: set[str] = set(fvis)
        while True:
            grew = False
            for node in self.nodes.values():
                if node.node_id in acc:
                    continue
                if any(status == "LIVE" and parent in acc for parent, status in node.usage_links.items()):
                    acc.add(node.node_id)
                    grew = True
            if not grew:
                return acc

    # -- retraction cascade ------------------------------------------------- #
    def retract(self, tag: tuple[str, int]) -> list[str]:
        """Invalidate an observation's root supports; propagate and SUPERSEDE orphaned asserted nodes.

        Returns the node ids newly marked SUPERSEDED."""
        for node in self.nodes.values():
            for rec in node.supports:
                if rec.kind == "ROOT" and rec.tag == tag and rec.status == "LIVE":
                    rec.status = "SUPERSEDED"
        return self._cascade()

    def _cascade(self) -> list[str]:
        """Recompute liveness; SUPERSEDE any LIVE node that is neither F-visible nor S-accessible (§8.2 step 7).

        Covers both an orphaned asserted fact (lost its last live, complete path — a DERIVED path dies when one of its
        premises stops being visible) and an unasserted structural operand with no own path under a dead parent.
        Reachability is computed once on the pre-supersede graph; superseding only removes liveness, so a single pass
        flags every truly unreachable node."""
        reachable = self.s_accessible()
        newly = []
        for node in self.nodes.values():
            current = "LIVE" if node.node_id in reachable else "SUPERSEDED"
            if node.status != current:
                self.audit.append({"node_id": node.node_id, "type": "REACCESSIBLE" if current == "LIVE" else "CASCADE_SUPERSEDED"})
                if current == "SUPERSEDED":
                    newly.append(node.node_id)
                node.status = current  # replaceable projection; never gates canonical identity
        return newly

    def som_violations(self) -> list[str]:
        """Asserted nodes that are LIVE yet have no live, complete support — the SOM invariant is broken."""
        fvis = self.f_visible()
        return sorted(n.node_id for n in self.nodes.values() if n.asserted and n.status == "LIVE" and n.node_id not in fvis)
