# -*- coding: utf-8 -*-
"""Bounded-count answer surface (V7 §6.3 deferred / §17.3): read an asserted numeric bound and render it.

The quantifier is already materialized in the graph (§6.2/§15): ``AT_LEAST_N`` carries a lower-bound
``bound_value``; ``EXACTLY_N``/``AT_MOST_N`` additionally require a DomainCertificate (§2.1) to be exact.
This module is the *reader* that was missing: it takes an asserted claim (extracted from committed state by
the caller) and renders a bounded-count answer, or returns UNKNOWN with a reason — never inventing a number
and never silently converting to EXISTS.

Pure and deterministic; no store/network access. The graph-extraction helper is intentionally thin so the
reader can be tested in isolation and wired into the query path without coupling to the core API.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Declared numeric quantifier kinds (V7 §6.2 operator set).
AT_LEAST_N = "AT_LEAST_N"
EXACTLY_N = "EXACTLY_N"
AT_MOST_N = "AT_MOST_N"
_NUMERIC_KINDS = {AT_LEAST_N, EXACTLY_N, AT_MOST_N}

# Diagnostics (V7 §10 style): honest incompleteness, never a fabricated count.
INCOMPLETE_DOMAIN = "INCOMPLETE_DOMAIN"          # exact/upper bound without DomainCertificate
NO_BOUND_ASSERTED = "NO_BOUND_ASSERTED"         # quantifier present but no number asserted
UNKNOWN_KIND = "UNKNOWN_NUMERIC_KIND"           # not a declared numeric quantifier


@dataclass(frozen=True)
class NumericClaim:
    """An asserted numeric claim read from committed state.

    ``kind`` is one of the declared numeric quantifiers; ``bound_value`` is the asserted number (None when the
    sentence asserts the quantifier without a numeral); ``has_certificate`` records whether a DomainCertificate
    (§2.1) covers the domain — required for EXACTLY_N/AT_MOST_N to be exact, never needed for AT_LEAST_N.
    """

    kind: str
    bound_value: int | None = None
    has_certificate: bool = False


@dataclass(frozen=True)
class CountAnswer:
    status: str                       # "ANSWERED" | "UNKNOWN"
    text: str                        # rendered answer ("" when UNKNOWN)
    reason: str | None = None        # diagnostic when UNKNOWN
    lower_bound: int | None = None   # provable lower bound surfaced even on INCOMPLETE_DOMAIN


def _render(kind: str, value: int) -> str:
    if kind == AT_LEAST_N:
        return f"как минимум {value}"
    if kind == EXACTLY_N:
        return f"ровно {value}"
    if kind == AT_MOST_N:
        return f"не более {value}"
    raise ValueError(f"unknown numeric kind {kind!r}")


def answer_count(claim: NumericClaim) -> CountAnswer:
    """Render a bounded-count answer for an asserted claim, or UNKNOWN with a reason.

    * AT_LEAST_N + bound  -> "как минимум N" (a lower bound is honest over an open domain; no certificate needed).
    * EXACTLY_N/AT_MOST_N + bound + certificate -> exact / upper phrasing.
    * EXACTLY_N/AT_MOST_N without certificate   -> UNKNOWN(INCOMPLETE_DOMAIN), but the proven lower bound is still surfaced.
    * No asserted number                              -> UNKNOWN(NO_BOUND_ASSERTED).
    """
    if claim.kind not in _NUMERIC_KINDS:
        return CountAnswer("UNKNOWN", "", reason=UNKNOWN_KIND)

    value = claim.bound_value
    if value is None or value < 0:
        return CountAnswer("UNKNOWN", "", reason=NO_BOUND_ASSERTED)

    if claim.kind == AT_LEAST_N:
        # A lower bound needs no domain certificate (§17.3): it is provable over an open domain.
        return CountAnswer("ANSWERED", _render(AT_LEAST_N, value), lower_bound=value)

    # EXACTLY_N / AT_MOST_N require a DomainCertificate to be exact/upper-bounded.
    if not claim.has_certificate:
        # Exactness is impossible; but the asserted number still bounds from below (honest partial result).
        return CountAnswer(
            "UNKNOWN", "", reason=INCOMPLETE_DOMAIN, lower_bound=value
        )

    return CountAnswer("ANSWERED", _render(claim.kind, value), lower_bound=value)


def extract_claim(graph: object, predicate_id: str) -> NumericClaim | None:
    """Best-effort extraction of a numeric claim for ``predicate_id`` from a committed graph.

    Thin adapter over the core graph API (an ``AT_LEAST`` link to a value token carrying ``bound_value``, §6.2).
    Returns None when no numeric scope is attached — the caller then reports NO_BOUND_ASSERTED upstream. Kept
    deliberately small so it can be swapped for the real core accessor without touching :func:`answer_count`.
    """
    links = getattr(graph, "links", None)
    if not callable(links):
        return None
    try:
        for link in links():
            if getattr(link, "kind", None) != "AT_LEAST":
                continue
            target = getattr(link, "target", None)
            value = getattr(target, "value", None)
            if value is not None and predicate_id in str(getattr(target, "predicate_id", "")):
                return NumericClaim(kind=AT_LEAST_N, bound_value=int(value))
    except Exception:  # pragma: no cover - defensive: never let extraction break the reader
        return None
    return None


__all__ = [
    "AT_LEAST_N", "EXACTLY_N", "AT_MOST_N",
    "INCOMPLETE_DOMAIN", "NO_BOUND_ASSERTED", "UNKNOWN_KIND",
    "NumericClaim", "CountAnswer", "answer_count", "extract_claim",
]
