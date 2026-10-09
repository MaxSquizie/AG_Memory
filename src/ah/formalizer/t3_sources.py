# -*- coding: utf-8 -*-
"""The exhaustive 5-source candidate contract for T3 (V7 §5.1 / WP1.2).

T3 creates a slot on every sealed frame and checks the FIVE declared candidate sources in a stable
order, writing one :class:`CandidateSourceTrace` per source. This module is pure (no store, no LLM):
it turns per-source inputs into the ordered trace set and exposes the decision rules that T4 must
honor — most importantly that a BLOCKED applicable source forbids BOTH NO_CANDIDATE and RESOLVED,
and that NO_CANDIDATE may be granted only after FOUND=0 with all five sources terminal-empty.

It does not reinvent candidate gathering: source (1) reuses ``candidates_for_slot``; the other
sources are supplied as inputs so the resource layer (R-S / R-X3 / W-C reads / open-lexical) can be
wired in later without touching this contract.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- status vocabulary ------------------------------------------------------ #
FOUND = "FOUND"
CHECKED_EMPTY = "CHECKED_EMPTY"
NOT_APPLICABLE = "NOT_APPLICABLE"
BLOCKED = "BLOCKED"
SOURCE_STATUSES = (FOUND, CHECKED_EMPTY, NOT_APPLICABLE, BLOCKED)
TERMINAL_EMPTY = (CHECKED_EMPTY, NOT_APPLICABLE)

# The five declared sources in STABLE order (§5.1). ValueExpansionRule is considered exactly once,
# in source 1; it is not re-run in source 5.
SOURCES: tuple[tuple[int, str], ...] = (
    (1, "SCHEMA_VALUE_IDS"),   # value_ids + declared ValueExpansionRule expansions
    (2, "RS_SENSES"),          # R-S senses
    (3, "RX3_PRIOR"),         # compatible R-X3 — a prior only, never a truth-ground
    (4, "WC_READS"),          # W/C from declared reads; absence of a fact is not negation
    (5, "OPEN_LEXICAL"),      # new lexical sense: deterministic open or validated proposal
)


@dataclass(frozen=True)
class CandidateSourceTrace:
    """One source's exhaustive check for one decision slot (§5.1)."""

    frame_id: str
    semantic_slot_id: str
    source_id: int                       # 1..5, stable order
    status: str                          # FOUND | CHECKED_EMPTY | NOT_APPLICABLE | BLOCKED
    candidate_ids: tuple[str, ...] = ()
    reason: str | None = None           # required for NOT_APPLICABLE (checkable premise) / BLOCKED (original diagnostic)
    resource_versions: tuple[str, ...] = ()
    provider_call_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source_id not in {1, 2, 3, 4, 5}:
            raise ValueError(f"source_id must be 1..5, got {self.source_id}")
        if self.status not in SOURCE_STATUSES:
            raise ValueError(f"unknown source status {self.status!r}")
        # NOT_APPLICABLE needs a checkable incompatible-premise reason; BLOCKED carries the original diagnostic.
        if self.status in (NOT_APPLICABLE, BLOCKED) and not self.reason:
            raise ValueError(f"source {self.source_id} {self.status} requires a reason")
        # FOUND with no candidates is contradictory; CHECKED_EMPTY/NOT_APPLICABLE carry none.
        if self.status == FOUND and not self.candidate_ids:
            raise ValueError(f"FOUND source {self.source_id} must list candidate_ids")
        if self.status in TERMINAL_EMPTY and self.candidate_ids:
            raise ValueError('INTEGRITY_ERROR: empty source carries candidates')


def validate_source_traces(traces) -> None:
    """Five distinct, ordered sources for one slot are mandatory, even if empty."""
    if ([t.source_id for t in traces] != [1, 2, 3, 4, 5]
            or len({(t.frame_id, t.semantic_slot_id) for t in traces}) != 1):
        raise ValueError('INTEGRITY_ERROR: incomplete or mixed candidate source traces')


def build_source_traces(
    frame_id: str,
    semantic_slot_id: str,
    *,
    schema_candidates=(),          # source 1 (value_ids + declared expansions)
    rs_senses=(),                 # source 2
    rx3_prior=(),                 # source 3 (prior only — never a truth-ground)
    wc_reads=(),                  # source 4 (provenance candidates from declared reads)
    open_candidate=None,          # source 5: a validated new-sense id, or None
    rs_applicable: bool = True,   # False -> NOT_APPLICABLE with reason
    rx3_applicable: bool = False,  # Phase 1: no R-X3 store wired
    wc_applicable: bool = True,
    open_path_verified: bool = True,  # source 5 CHECKED_EMPTY precondition (deterministic path checked)
    blocked=frozenset(),          # source_ids that are BLOCKED
    blocked_reasons=None,         # {source_id: original diagnostic}
    resource_versions=(),
) -> list[CandidateSourceTrace]:
    """Emit exactly five ordered traces for one decision, honoring the §5.1 status rules."""
    blocked = set(blocked)
    reasons = dict(blocked_reasons or {})
    out: list[CandidateSourceTrace] = []

    def emit(source_id: int, *, candidates=(), applicable: bool = True,
             empty_reason: str | None = None, na_reason: str | None = None) -> None:
        if source_id in blocked:
            out.append(CandidateSourceTrace(frame_id, semantic_slot_id, source_id, BLOCKED,
                                           reason=reasons.get(source_id, "blocked")))
            return
        cands = tuple(sorted(set(candidates)))
        if not applicable:
            out.append(CandidateSourceTrace(frame_id, semantic_slot_id, source_id, NOT_APPLICABLE,
                                           reason=na_reason or f"source {source_id} not applicable"))
            return
        if cands:
            out.append(CandidateSourceTrace(frame_id, semantic_slot_id, source_id, FOUND,
                                           candidate_ids=cands, resource_versions=tuple(resource_versions)))
        else:
            # CHECKED_EMPTY = a valid resource was read and yielded nothing (or the deterministic
            # open path was verified). Source 5 additionally requires open_path_verified.
            if source_id == 5 and not open_path_verified:
                out.append(CandidateSourceTrace(frame_id, semantic_slot_id, source_id, BLOCKED,
                                               reason="open-lexical path not verified"))
                return
            out.append(CandidateSourceTrace(frame_id, semantic_slot_id, source_id, CHECKED_EMPTY,
                                           reason=empty_reason))

    emit(1, candidates=schema_candidates)
    emit(2, candidates=rs_senses, applicable=rs_applicable, na_reason="no R-S sense resource in this release")
    emit(3, candidates=rx3_prior, applicable=rx3_applicable, na_reason="no R-X3 store wired (Phase 1)")
    emit(4, candidates=wc_reads, applicable=wc_applicable,
         empty_reason="declared reads supply C-grounds only; no additional value candidate")
    emit(5, candidates=(open_candidate,) if open_candidate else (),
         empty_reason="deterministic open path checked; no admissible new sense")

    return out


# -- decision rules T4 must honor ------------------------------------------ #
def found_count(traces) -> int:
    """Total candidates surfaced by any FOUND source."""
    return sum(len(t.candidate_ids) for t in traces if t.status == FOUND)


def search_blocked(traces) -> bool:
    """A BLOCKED applicable source makes the search incomplete.

    §5.1: this forbids BOTH NO_CANDIDATE and RESOLVED — a candidate found by another source is not
    unique under an incomplete search; the outcome is UNRESOLVED (or COMPUTATION_LIMIT for budget)."""
    return any(t.status == BLOCKED for t in traces)


def no_candidate_allowed(traces) -> bool:
    """NO_CANDIDATE only after FOUND=0 AND all five sources terminal CHECKED_EMPTY|NOT_APPLICABLE."""
    validate_source_traces(traces)
    if search_blocked(traces):
        return False
    if found_count(traces) != 0:
        return False
    return all(t.status in TERMINAL_EMPTY for t in traces)


def resolved_allowed(traces, has_positive_grounds: bool = True) -> bool:
    """RESOLVED is forbidden under an incomplete (BLOCKED) search even with a found candidate."""
    validate_source_traces(traces)
    return not search_blocked(traces) and has_positive_grounds
