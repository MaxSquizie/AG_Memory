# -*- coding: utf-8 -*-
"""WP3.3 — Inference engine + temporal licenses (V7 §6.3/§7.4): rule table, derived TimeAssertions in the goal transaction, mismatch diagnostics.

Each inference rule is declared with its operator and the *temporal license kind* it requires; admissibility for a given operator is
checked against the FunctionRegistry v2 table (WP3.1) rather than hard-coded per rule. A conclusion's temporal interval is derived from
its premises' intervals inside the goal transaction: an AND-like derivation intersects all premise regions, and if they do not overlap
the engine reports ``TEMPORAL_MISMATCH`` (no derived TimeAssertion). OR_ELIMINATION additionally requires every branch to be covered or it
reports ``OR_ELIMINATION_INCOMPLETE``.

Pure module; reuses the temporal license algebra (WP2.6) and the operator table (WP3.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from ah.formalizer.operator_algebra import FunctionRegistryV2
from ah.formalizer.temporal_license import TemporalRegion, cont, covers


@dataclass(frozen=True)
class InferenceRule:
    name: str
    operator: str                 # the operator/quantifier this rule applies to
    license_kind: str             # POINT | CONTINUOUS | NONE
    needs_all_branches: bool = False


DEFAULT_RULES = [
    InferenceRule("AND_ELIMINATION", "AND", "POINT"),
    InferenceRule("OR_ELIMINATION", "OR", "CONTINUOUS", needs_all_branches=True),
    InferenceRule("FORALL_INST", "EVERY", "POINT"),   # EVERY is a quantifier (WP3.2), not in the operator table
    InferenceRule("MODUS_PONENS", "IMPLIES", "POINT"),
]


def _intersect(a: TemporalRegion, b: TemporalRegion):
    """Conservative intersection of two premise regions; None when they share no common region (TEMPORAL_MISMATCH)."""
    if a.kind == "CONTINUOUS" and b.kind == "CONTINUOUS":
        if any(x is None for x in (a.lo, a.hi, b.lo, b.hi)):
            return None                                  # unknown boundary -> mismatch
        lo, hi = max(a.lo, b.lo), min(a.hi, b.hi)
        return cont(lo, hi) if lo <= hi else None
    if a.kind == "POINT" and b.kind in ("CONTINUOUS", "EXISTENTIAL"):
        return a if covers(b, a) is True else None
    if b.kind == "POINT" and a.kind in ("CONTINUOUS", "EXISTENTIAL"):
        return b if covers(a, b) is True else None
    if a.kind == "POINT" and b.kind == "POINT":
        return a if a.point == b.point else None
    return None                                          # otherwise -> conservative mismatch


class InferenceEngine:
    def __init__(self, registry: FunctionRegistryV2 | None = None):
        self.registry = registry or FunctionRegistryV2()
        self.rules = {r.name: r for r in DEFAULT_RULES}

    def rule(self, name: str) -> InferenceRule:
        return self.rules[name]

    def admissible_for_operator(self, operator: str, rule_name: str) -> bool:
        """A rule is admissible only if the operator's declared inference rules include it (WP3.1 table)."""
        r = self.rules[rule_name]
        if r.operator == "EVERY":                       # quantifier layer, not in the operator table
            return operator == "EVERY"
        return r.operator == operator and self.registry.inferable(operator, rule_name)

    def derive_interval(self, rule_name: str, premise_regions):
        """Intersect all premise regions; None (TEMPORAL_MISMATCH) if they do not share a common region."""
        regions = list(premise_regions)
        if not regions:
            raise ValueError("no premises to derive from")
        result: TemporalRegion = regions[0]
        for pr in regions[1:]:
            inter = _intersect(result, pr)
            if inter is None:
                return None                             # TEMPORAL_MISMATCH
            result = inter
        return result

    def or_elimination_status(self, covered_branches: int, total_branches: int) -> str:
        return "OK" if covered_branches >= total_branches else "OR_ELIMINATION_INCOMPLETE"

    def derive_time_assertion(self, rule_name: str, premise_regions, conclusion_id: str):
        """A derived TimeAssertion for the goal transaction; None on TEMPORAL_MISMATCH (caller records the diagnostic)."""
        interval = self.derive_interval(rule_name, premise_regions)
        if interval is None:
            return None
        return {"assertion_id": conclusion_id, "interval": interval,
                "provenance": {"rule": rule_name}}


if __name__ == "__main__":  # pragma: no cover - quick sanity
    from ah.formalizer.temporal_license import cont
    e = InferenceEngine()
    print(e.derive_time_assertion("AND_ELIMINATION", [cont(0, 5), cont(3, 8)], "c1"))
