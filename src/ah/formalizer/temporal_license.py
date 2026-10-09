# -*- coding: utf-8 -*-
"""WP2.5 — temporal license algebra (V7 §6.3/§7.4): the pure decision core for dated inference.

Models the four region kinds and the two documented license tables as pure functions over an in-memory region, so the
temporal half of the goal executor / commit-time derivation is testable without a store:

* ``TemporalRegion`` — POINT(t) | EXISTENTIAL(J) | CONTINUOUS([lo,hi]) | UNDATED; a degenerate EXISTENTIAL({t}) is
  normalized to POINT(t) for license computation (the original kind/provenance stay in the ledger for audit).
* ``covers(outer, inner)`` — True/False/None (unknown boundary): does outer's region contain every realization of
  inner? This drives OR_ELIMINATION: a NOT-premise is licensed only if its negation region covers EVERY realization
  of the OR root's region.
* ``or_elimination_license(w_or, w_j)`` — the §7.4 combination table (subset semantics); mixed dated/undated and an
  uncovered region are UNKNOWN with their diagnostics; both undated is a propositional (undated) conclusion.
* ``forall_inst_license(a, b)`` — the §6.3 quantifier table (intersection semantics): POINT+POINT equal -> POINT;
  POINT in CONTINUOUS -> POINT; CONTINUOUS∩CONTINUOUS non-empty -> the intersection; EXISTENTIAL⊆CONTINUOUS -> the
  existential set; two non-degenerate existentials are never licensed.

Pure module: it returns license decisions for the caller to materialize as derived TimeAssertions / goal outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TemporalRegion:
    """A temporal region: POINT(t), EXISTENTIAL(J), CONTINUOUS([lo,hi]) inclusive, or UNDATED."""

    kind: str                                   # "POINT" | "EXISTENTIAL" | "CONTINUOUS" | "UNDATED"
    point: Optional[int] = None                 # for POINT
    lo: Optional[int] = None                    # for CONTINUOUS (None = unknown boundary)
    hi: Optional[int] = None                    # for CONTINUOUS (None = unknown boundary)
    points: frozenset = field(default=frozenset())  # for EXISTENTIAL


@dataclass(frozen=True)
class LicenseResult:
    status: str                 # "LICENSED" | "UNKNOWN"
    derived_region: Optional[TemporalRegion] = None   # the conclusion's region (root's own region, normalized)
    diagnostic: Optional[str] = None                # OR_ELIMINATION_TEMPORAL_MISMATCH / FORALL_INST_... / INTERVAL_BOUNDARY_UNKNOWN


def point(t): return TemporalRegion("POINT", point=t)
def cont(lo, hi): return TemporalRegion("CONTINUOUS", lo=lo, hi=hi)
def exist(*pts): return TemporalRegion("EXISTENTIAL", points=frozenset(pts))
def undated(): return TemporalRegion("UNDATED")


def normalize(r: TemporalRegion) -> TemporalRegion:
    """Collapse a degenerate EXISTENTIAL({t}) to POINT(t); keep everything else as-is."""
    if r.kind == "EXISTENTIAL" and r.lo is not None and r.lo == r.hi:
        return point(r.lo)
    if r.kind == "EXISTENTIAL" and len(r.points) == 1:
        return point(next(iter(r.points)))
    return r


def covers(outer: TemporalRegion, inner: TemporalRegion):
    """True/False/None — does ``outer`` contain every realization of ``inner``? (subset semantics)"""
    o, n = normalize(outer), normalize(inner)

    if n.kind == "POINT":                       # a single moment t
        t = n.point
        if t is None:
            return None
        if o.kind == "POINT":
            return None if o.point is None else o.point == t
        if o.kind == "CONTINUOUS":
            if o.lo is None or o.hi is None:
                return None                     # unknown boundary -> inclusion not established
            return o.lo <= t <= o.hi
        if o.kind == "EXISTENTIAL":
            return False  # existential occurrence does not establish any particular moment
        return False                            # UNDATED outer covers nothing

    if n.kind == "CONTINUOUS":                 # a whole interval must lie inside outer
        if o.kind == "POINT":
            if any(x is None for x in (o.point,n.lo,n.hi)):
                return None
            return n.lo == n.hi == o.point
        if o.kind != "CONTINUOUS":
            return False
        if any(x is None for x in (o.lo, o.hi, n.lo, n.hi)):
            return None
        return o.lo <= n.lo and n.hi <= o.hi

    if n.kind == "EXISTENTIAL":                # a multi-point set: only an interval can cover it
        if o.kind == "CONTINUOUS":
            if o.lo is None or o.hi is None:
                return None
            return (o.lo <= n.lo and n.hi <= o.hi) if n.lo is not None and n.hi is not None else (all(o.lo <= s <= o.hi for s in n.points) if n.points else None)
        return False                           # POINT / EXISTENTIAL outer cannot cover a multi-point set

    return False                               # UNDATED inner


def or_elimination_license(w_or: TemporalRegion, w_j: TemporalRegion) -> LicenseResult:
    """§7.4 — license eliminating disjunct Pj when the NOT-premise region covers every realization of the OR root."""
    o, n = normalize(w_or), normalize(w_j)

    if (o.kind == "UNDATED") != (n.kind == "UNDATED"):
        return LicenseResult("UNKNOWN", None, "OR_ELIMINATION_TEMPORAL_MISMATCH")  # mixed dated/undated
    if o.kind == "UNDATED" and n.kind == "UNDATED":
        return LicenseResult("LICENSED", undated(), None)                          # propositional conclusion

    c = covers(n, o)                        # the negation must cover the root's region
    if c is True:
        return LicenseResult("LICENSED", o, None)   # derived region = the root's own (normalized) region
    if c is None:
        return LicenseResult("UNKNOWN", None, "INTERVAL_BOUNDARY_UNKNOWN")
    return LicenseResult("UNKNOWN", None, "OR_ELIMINATION_TEMPORAL_MISMATCH")


def _cont_intersect(a: TemporalRegion, b: TemporalRegion):
    """Inclusive intersection of two CONTINUOUS regions, or None if empty / unknown boundary."""
    if any(x is None for x in (a.lo, a.hi, b.lo, b.hi)):
        return None
    lo, hi = max(a.lo, b.lo), min(a.hi, b.hi)
    return cont(lo, hi) if lo <= hi else None


def forall_inst_license(a: TemporalRegion, b: TemporalRegion) -> LicenseResult:
    """§6.3 — quantifier instantiation license (intersection semantics; order-insensitive)."""
    x, y = normalize(a), normalize(b)

    if (x.kind == "UNDATED") != (y.kind == "UNDATED"):
        return LicenseResult("UNKNOWN", None, "FORALL_INST_TEMPORAL_MISMATCH")     # mixed dated/undated
    if x.kind == "UNDATED" and y.kind == "UNDATED":
        return LicenseResult("LICENSED", undated(), None)

    def pick(kind):  # the region of a given kind (both dated, so exactly one matches each branch)
        for r in (x, y):
            if r.kind == kind:
                return r
        return None

    mismatch = lambda: LicenseResult("UNKNOWN", None, "FORALL_INST_TEMPORAL_MISMATCH")  # noqa: E731
    kinds = {x.kind, y.kind}

    if kinds == {"POINT"}:
        a, b = x.point, y.point
        if a is None or b is None:
            return LicenseResult("UNKNOWN", None, "INTERVAL_BOUNDARY_UNKNOWN")
        return LicenseResult("LICENSED", point(a)) if a == b else mismatch()

    if kinds == {"POINT", "CONTINUOUS"}:
        p, c = pick("POINT"), pick("CONTINUOUS")
        if p.point is None or c.lo is None or c.hi is None:
            return LicenseResult("UNKNOWN", None, "INTERVAL_BOUNDARY_UNKNOWN")
        ok = c.lo <= p.point <= c.hi
        return LicenseResult("LICENSED", point(p.point)) if ok else mismatch()

    if kinds == {"POINT", "EXISTENTIAL"}:
        return mismatch()                     # only the degenerate {t} case is licensed (already normalized to POINT)

    if kinds == {"CONTINUOUS"}:
        inter = _cont_intersect(x, y)
        if inter is None:
            diag = "INTERVAL_BOUNDARY_UNKNOWN" if any(v is None for v in (x.lo, x.hi, y.lo, y.hi)) \
                else "FORALL_INST_TEMPORAL_MISMATCH"
            return LicenseResult("UNKNOWN", None, diag)
        return LicenseResult("LICENSED", inter)

    if kinds == {"EXISTENTIAL", "CONTINUOUS"}:
        e, c = pick("EXISTENTIAL"), pick("CONTINUOUS")
        if c.lo is None or c.hi is None:
            return LicenseResult("UNKNOWN", None, "INTERVAL_BOUNDARY_UNKNOWN")
        ok = (c.lo <= e.lo and e.hi <= c.hi) if e.lo is not None and e.hi is not None else bool(e.points) and all(c.lo <= s <= c.hi for s in e.points)   # J ⊆ I
        return LicenseResult("LICENSED", e) if ok else mismatch()

    return mismatch()                         # two non-degenerate EXISTENTIAL are never licensed


if __name__ == "__main__":  # pragma: no cover - quick sanity
    print(or_elimination_license(point(5), cont(3, 7)))
    print(forall_inst_license(cont(2, 4), cont(3, 6)))
