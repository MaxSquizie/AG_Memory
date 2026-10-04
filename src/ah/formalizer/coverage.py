# -*- coding: utf-8 -*-
"""Coverage / miss accumulator (V7 §2.3): aggregate *honest incompleteness* across a batch so the oracle can see what to extend.

The whole point of §2.3 is that coverage grows by **accumulating declared gaps**, not by per-example rules (G5). This module
turns a batch of :class:`~ah.formalizer.state.FormalizationState` into one :class:`CoverageReport` the oracle can read:

* **Honest incompleteness** — the mechanism ran correctly and reported a *declared* gap it cannot close with current resources
  (no declared relation fits, an incomplete/blocked search, no admissible antecedent in the window, an uncovered structure).
  These are the signals that say "extend the schema / grammar / window here" — never a reason to invent an answer.
* **Provider failures** — ``PROVIDER_UNAVAILABLE`` / ``PROTOCOL_ERROR``. These are *infrastructure*, NOT coverage gaps: a live-model
  outage or a malformed response must not be counted as "the system doesn't know this", so they are reported separately and excluded
  from the honest-incompleteness total (V7 §0.8: an outage never becomes AMBIGUOUS).

Pure module; no store/network access. Deterministic for a fixed batch of states.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Declared gaps the mechanism may honestly report (mechanism worked; resource is missing).
HONEST_GAPS = frozenset({
    "NO_CANDIDATE",          # demo boundary: no declared relation fits this input
    "COMPUTATION_LIMIT",     # search incomplete / budget exhausted — not exhaustive, so not NO_CANDIDATE
    "REFERENCE_UNKNOWN",     # no admissible antecedent in the observation/memory window
    "STRUCTURE_NOT_COVERED", # e.g. OP5 COORD: declared in grammar, exercised later
})

# Infrastructure failures — reported separately, never counted as semantic coverage gaps.
PROVIDER_CODES = frozenset({"PROVIDER_UNAVAILABLE", "PROTOCOL_ERROR"})

#: A decision reached a *proven* semantic outcome (RESOLVED or AMBIGUOUS with per-value grounds).
_PROVEN = {"RESOLVED", "AMBIGUOUS"}


@dataclass(frozen=True)
class CoverageReport:
    sentences: int
    decisions: int
    proven_outcomes: int                 # decisions with a proven semantic outcome (RESOLVED/AMBIGUOUS)
    answered_sentences: int             # sentences whose predicate decision reached a proven outcome
    honest_gaps: dict[str, int] = field(default_factory=dict)      # diagnostic code -> count
    provider_failures: dict[str, int] = field(default_factory=dict)  # diagnostic code -> count

    @property
    def coverage_ratio(self) -> float:
        """Fraction of sentences that reached a proven predicate outcome (0.0 when no sentences)."""
        return self.answered_sentences / self.sentences if self.sentences else 0.0

    @property
    def honest_gap_total(self) -> int:
        return sum(self.honest_gaps.values())

    @property
    def provider_failure_total(self) -> int:
        return sum(self.provider_failures.values())


def _count_by_code(diagnostics, codes: frozenset) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in diagnostics:
        code = getattr(d, "code", None)
        if code in codes:
            out[code] = out.get(code, 0) + 1
    return out


def summarize(states) -> CoverageReport:
    """Aggregate a batch of formalization states into one coverage report (V7 §2.3)."""
    sentences = len(states)
    decisions = proven = answered = 0

    honest: dict[str, int] = {}
    provider: dict[str, int] = {}

    for st in states:
        sentence_answered = False
        for dec in getattr(st, "decisions", {}).values():
            decisions += 1
            if dec.outcome in _PROVEN:
                proven += 1
                if dec.slot_id == "predicate_value":
                    sentence_answered = True
        if sentence_answered:
            answered += 1

        diags = getattr(st, "diagnostics", []) or []
        for code, n in _count_by_code(diags, HONEST_GAPS).items():
            honest[code] = honest.get(code, 0) + n
        for code, n in _count_by_code(diags, PROVIDER_CODES).items():
            provider[code] = provider.get(code, 0) + n

    return CoverageReport(
        sentences=sentences, decisions=decisions, proven_outcomes=proven,
        answered_sentences=answered, honest_gaps=honest, provider_failures=provider,
    )


__all__ = ["CoverageReport", "summarize", "HONEST_GAPS", "PROVIDER_CODES"]
