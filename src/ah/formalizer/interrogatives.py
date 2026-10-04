# -*- coding: utf-8 -*-
"""Broad interrogative registry (V7 §6.3 deferred): the full class of speech interrogatives, not just "how many".

``GoalCompiler`` currently maps a fixed request_kind set. This module declares the *full* class of interrogatives
that can in principle appear in speech — which/what (open WH over roles and values), where, when (point / interval /
existential), why (CAUSAL), who (role fill over entities), how (manner), comparative/superlative, hypothetical
("что если"), indirect questions-requests (§18 DR27) — each bound to a **declared** goal kind + an explicit
UNKNOWN/insufficient fallback.

Two hard guarantees (V7 §6.3):
* **No arbitrary EXISTS.** An unknown request_kind compiles to ``QUERY_TARGET_UNBOUND``; no interrogative silently
  degrades into a bare existence check, and YESNO only yields ExistsGoal when a closed basis is available.
* **IF / hypothetical / indirect need clause detection.** Their domains require paired clause boundaries (§6.2 IMPLIES);
  without a ``clause_detector`` they stay ``QUERY_TARGET_UNBOUND`` (never guessed), and non-factual kinds never enter the
  ordinary factual GoalMode.

Coverage grows incrementally via the miss-accumulator (§2.3) — not by per-example rules (G5). Pure module; no store access.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ah.formalizer.count_reader import NumericClaim, CountAnswer, answer_count


# Declared goal kinds (V7 §6.3 GoalCompiler vocabulary).
ROLE_FILL = "RoleFillGoal"
MULTI_ROLE_FILL = "MultiRoleFillGoal"
FORMULA = "FormulaGoal"
EXISTS = "ExistsGoal"
COUNT = "CountGoal"
CAUSE = "CauseEntailmentGoal"
RELATION = "RelationGoal"
ASSOCIATION = "AssociationGoal"
COUNTERFACTUAL = "CounterfactualGoal"

# Diagnostics.
UNKNOWN_INTERROGATIVE = "UNKNOWN_INTERROGATIVE"      # request_kind not declared -> UNBOUND, never EXISTS
CLAUSE_DETECTION_REQUIRED = "CLAUSE_DETECTION_REQUIRED"  # IF/hypothetical/indirect without clause boundaries


@dataclass(frozen=True)
class InterrogativeSpec:
    request_kind: str
    goal_kinds: tuple[str, ...]   # declared goals this kind compiles to (never a bare EXISTS by default)
    fallback: str                 # explicit UNKNOWN/insufficient outcome when unanswerable
    requires_clause: bool = False  # needs paired clause boundaries (§6.2 IMPLIES / nested)
    non_factual: bool = False      # never enters the ordinary factual GoalMode (hypothetical / indirect request)


# The full declared class of speech interrogatives (V7 §6.3). Order is not significant.
REGISTRY: dict[str, InterrogativeSpec] = {
    "WH_OPEN":        InterrogativeSpec("WH_OPEN", (ROLE_FILL, MULTI_ROLE_FILL), fallback="UNKNOWN"),
    "WHO":            InterrogativeSpec("WHO", (ROLE_FILL,), fallback="UNKNOWN"),
    "WHERE":          InterrogativeSpec("WHERE", (ROLE_FILL, FORMULA), fallback="UNKNOWN"),
    "WHEN_POINT":     InterrogativeSpec("WHEN_POINT", (FORMULA,), fallback="UNKNOWN"),
    "WHEN_INTERVAL":  InterrogativeSpec("WHEN_INTERVAL", (FORMULA,), fallback="UNKNOWN"),
    "WHEN_EXISTENTIAL": InterrogativeSpec("WHEN_EXISTENTIAL", (EXISTS, FORMULA), fallback="UNKNOWN"),
    "WHY":            InterrogativeSpec("WHY", (CAUSE, RELATION), fallback="NO_CAUSAL_SUPPORT"),
    "HOW":            InterrogativeSpec("HOW", (ROLE_FILL,), fallback="INSUFFICIENT_CONTEXT"),
    "COMPARATIVE":    InterrogativeSpec("COMPARATIVE", (FORMULA,), fallback="UNKNOWN"),
    "SUPERLATIVE":    InterrogativeSpec("SUPERLATIVE", (FORMULA, COUNT), fallback="INCOMPLETE_DOMAIN"),
    # Non-factual / clause-scoped: never a bare factual goal; need paired clause boundaries.
    "HYPOTHETICAL":   InterrogativeSpec("HYPOTHETICAL", (COUNTERFACTUAL,), fallback="UNKNOWN",
                                       requires_clause=True, non_factual=True),
    "IF":             InterrogativeSpec("IF", (FORMULA,), fallback="QUERY_TARGET_UNBOUND",
                                       requires_clause=True, non_factual=True),
    "INDIRECT_REQUEST": InterrogativeSpec("INDIRECT_REQUEST", (ASSOCIATION,), fallback="NOT_ASSERTED_FACT",
                                         requires_clause=True, non_factual=True),
    # Numeric: delegates to the bounded-count reader (§6.3/§17.3).
    "COUNT":          InterrogativeSpec("COUNT", (COUNT,), fallback="UNKNOWN"),
}


@dataclass(frozen=True)
class CompiledQuery:
    request_kind: str
    status: str                       # "COMPILED" | "QUERY_TARGET_UNBOUND"
    goal_kinds: tuple[str, ...] = ()
    reason: str | None = None         # diagnostic when UNBOUND


def _has_boundaries(detector) -> bool:
    """A clause-scoped kind needs *actual* paired boundaries, not merely a present detector.

    A :class:`~ah.formalizer.clause_detection.ClauseStructure` satisfies the requirement only when it yields at least one
    IF pair; any other opaque detector is assumed to provide boundaries (it was passed deliberately).
    """
    if detector is None:
        return False
    pairs = getattr(detector, "if_pairs", None)
    if callable(pairs):
        return bool(pairs())
    return True


def compile(request_kind: str, *, clause_detector=None) -> CompiledQuery:
    """Compile a request_kind to declared goals.

    * Unknown kind            -> QUERY_TARGET_UNBOUND (UNKNOWN_INTERROGATIVE); never an arbitrary EXISTS.
    * Clause-scoped without paired boundaries -> QUERY_TARGET_UNBOUND (CLAUSE_DETECTION_REQUIRED).
    * Otherwise              -> COMPILED with the declared goal_kinds.
    """
    spec = REGISTRY.get(request_kind)
    if spec is None:
        return CompiledQuery(request_kind, "QUERY_TARGET_UNBOUND", reason=UNKNOWN_INTERROGATIVE)
    if spec.requires_clause and not _has_boundaries(clause_detector):
        return CompiledQuery(request_kind, "QUERY_TARGET_UNBOUND", reason=CLAUSE_DETECTION_REQUIRED)
    return CompiledQuery(request_kind, "COMPILED", goal_kinds=spec.goal_kinds)


def answer_count_query(claim: NumericClaim) -> CountAnswer:
    """Delegate a COUNT interrogative to the bounded-count reader (§6.3/§17.3)."""
    return answer_count(claim)


def no_arbitrary_exists() -> bool:
    """Invariant (V7 §6.3): no declared kind compiles to a *bare* EXISTS by default, and unknown kinds never do."""
    for spec in REGISTRY.values():
        if spec.goal_kinds == (EXISTS,):
            return False
    probe = compile("SOME_RANDOM_KIND")
    return probe.status == "QUERY_TARGET_UNBOUND" and not probe.goal_kinds


__all__ = [
    "ROLE_FILL", "MULTI_ROLE_FILL", "FORMULA", "EXISTS", "COUNT",
    "CAUSE", "RELATION", "ASSOCIATION", "COUNTERFACTUAL",
    "UNKNOWN_INTERROGATIVE", "CLAUSE_DETECTION_REQUIRED",
    "InterrogativeSpec", "REGISTRY", "CompiledQuery", "compile",
    "answer_count_query", "no_arbitrary_exists",
]
