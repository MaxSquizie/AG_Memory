# -*- coding: utf-8 -*-
"""Open-set value-generation *trigger* (V7 §2.3 / §5.x) — D.

Philosophy: open-set predicate-value generation is **deferred** and must be enabled only after enough
*honest misses* have accumulated (never per-example, never by inventing values now). This module provides
the auditable *decision trigger*, not the generation itself: it turns "we keep hitting NO_CANDIDATE on this
slot across many distinct inputs" into a flagged :class:`OpenSetProposal` that says *consider extending the
value space here*.

Contract (honest, conservative):
- A miss is an honest ``NO_CANDIDATE`` decision on the target slot (mechanism ran; declared value set did not fit).
- The gate fires only when misses recur across at least ``min_distinct`` **distinct** inputs — a single repeated
  sentence cannot justify open-set generation.
- Below threshold it returns ``None``: nothing changes, no values are invented, and the proposal is never auto-applied.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenSetProposal:
    slot_id: str
    distinct_miss_inputs: int
    total_misses: int
    threshold: int
    reason: str


def evaluate_open_set(states, slot_id: str = "predicate_value", min_distinct: int = 3):
    """Return an :class:`OpenSetProposal` when honest misses on ``slot_id`` recur across >= ``min_distinct``
    distinct inputs; otherwise ``None``. Never invents values and is not auto-applied."""
    distinct: set[str] = set()
    total = 0
    for st in states:
        missed_here = False
        for dec in getattr(st, "decisions", {}).values():
            if dec.slot_id == slot_id and dec.outcome == "NO_CANDIDATE":
                total += 1
                missed_here = True
        if missed_here:
            distinct.add(getattr(st, "text", ""))

    if len(distinct) >= min_distinct:
        return OpenSetProposal(
            slot_id=slot_id,
            distinct_miss_inputs=len(distinct),
            total_misses=total,
            threshold=min_distinct,
            reason=f"{len(distinct)} distinct inputs missed {slot_id} (>= {min_distinct})",
        )
    return None


__all__ = ["OpenSetProposal", "evaluate_open_set"]
