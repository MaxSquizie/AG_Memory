# -*- coding: utf-8 -*-
"""WP2.5 — SOM + UsageLink typed layer (V7 §7.5): s_visible = F ∪ S, s_accessible = asserted ∧ (s_visible ∨ live usage link),
SUPERSEDED cascade by usage dependencies.

A node is *accessible* if it is asserted and either has a live support path (F-visible) or is referenced by a LIVE usage link
whose source is itself accessible. ``UsageLink`` is typed: kind ∈ {N→N, G→N, G→G} (an N→G link is rejected). Accessibility is
computed as an iterative monotone fixpoint over the asserted/live base — cycle-safe, so mutual references without a live base
support nothing. Superseding a node (dropping it from the live set) cascades: dependents reachable only through it fall out of
the accessible set and their outgoing links are marked SUPERSEDED.

Pure module; the durable store adapter persists nodes/links with fsync.
"""

from __future__ import annotations

from dataclasses import dataclass, field


ALLOWED_KINDS = {"N_N", "G_N", "G_G"}   # N→G is not a legal usage link


@dataclass
class UsageLink:
    link_id: str
    source_ref: str
    target_ref: str
    kind: str                            # one of ALLOWED_KINDS
    status: str = "LIVE"                 # LIVE | SUPERSEDED


class UsageLayer:
    def __init__(self, nodes: dict):
        """nodes: {node_id: {"kind": "N"|"G", "asserted": bool}}."""
        self.nodes = nodes
        self.links: dict[str, UsageLink] = {}
        self.live: set = set()           # F-visible (support-backed) node ids

    def _kind(self, node_id: str) -> str:
        return self.nodes[node_id]["kind"]

    def add_link(self, source_ref: str, target_ref: str) -> UsageLink:
        kind = f"{self._kind(source_ref)}_{self._kind(target_ref)}"
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"illegal usage link kind {kind} ({source_ref}->{target_ref})")
        rec = UsageLink(link_id=f"L{len(self.links) + 1}", source_ref=source_ref, target_ref=target_ref, kind=kind)
        self.links[rec.link_id] = rec
        return rec

    def set_live(self, node_id: str, is_live: bool) -> None:
        if is_live:
            self.live.add(node_id)
        else:
            self.live.discard(node_id)

    def accessible(self) -> set:
        """Iterative monotone fixpoint: asserted∧live base, then asserted targets of LIVE links from an accessible source."""
        acc = {nid for nid, n in self.nodes.items() if n["asserted"] and nid in self.live}
        changed = True
        while changed:
            changed = False
            for l in self.links.values():
                if (l.status == "LIVE" and l.source_ref in acc
                        and self.nodes[l.target_ref]["asserted"] and l.target_ref not in acc):
                    acc.add(l.target_ref)
                    changed = True
        return acc

    def s_accessible(self, node_id: str) -> bool:
        return node_id in self.accessible()

    def supersede(self, node_id: str) -> set:
        """Drop a node from the live set and cascade: mark SUPERSEDED every node that falls out of the accessible set, plus
        their outgoing links. Returns the set of newly-inaccessible nodes."""
        before = self.accessible()
        self.set_live(node_id, False)
        after = self.accessible()
        dropped = before - after
        for nid in dropped:
            self.nodes[nid]["status"] = "SUPERSEDED"
        for l in self.links.values():
            if l.status == "LIVE" and (l.source_ref in dropped or l.target_ref in dropped):
                l.status = "SUPERSEDED"
        return dropped


if __name__ == "__main__":  # pragma: no cover - quick sanity
    ul = UsageLayer({"A": {"kind": "N", "asserted": True}, "B": {"kind": "G", "asserted": True}})
    ul.set_live("A", True)
    ul.add_link("A", "B")
    print(sorted(ul.accessible()))
