# -*- coding: utf-8 -*-
"""FormalizationCache (R-X) — adaptive experience layer (V7 §5.10).

The cache stores *experience, not truth*. It may influence the PRIORITY of candidates but has
no right to forbid a new interpretation and never contributes a ground by itself (no
self-confirmation): the current sentence is always re-analysed from scratch, and a cached hit
only reorders admissible candidates — it can never remove one.

Hard contracts enforced here:
* STAGE ISOLATION — one physical store, stage-dependent read contract. A T1 caller reads only
  R-X1 (morphological/lexical) payloads; it is structurally impossible for it to see role or
  semantic fields, because :meth:`read_for_stage` returns only the requested stage's payload.
* RANKING != EXCLUSION — :meth:`rank` reorders the FULL admissible set by priority hint and
  never drops a candidate (a budget-exhausted search is SEARCH_INCOMPLETE upstream, not a cache
  exclusion).
* NEGATIVE EXPERIENCE ONLY FROM D/C/R — a rejection becomes negative experience only when it was
  decided on semantic/structural grounds {D, C, R}; computational diagnostics
  (PROVIDER_UNAVAILABLE / SEARCH_INCOMPLETE / BUDGET_EXHAUSTED) are NOT negative experience.
* VERSIONING — a record is readable only while its versions match the current ones; on mismatch it
  is excluded (never auto-applied) and must be explicitly migrated or superseded.
* SUPERSESSION WITHOUT DELETION — :meth:`supersede` flips a version's records LIVE -> SUPERSEDED
  (audit preserved); "the formalizer does not learn from its own already-acknowledged errors."

Construction entries are keyed by a StructuralPattern (frame_1, connector+evidence, frame_2), NOT
a string template, so the cache cannot degenerate into an auto-learned lexical rule table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

LIVE = "LIVE"
SUPERSEDED = "SUPERSEDED"
STALE = "STALE"

# Ground types that may create NEGATIVE experience (semantic/structural rejections).
_NEGATIVE_GROUNDS = {"D", "C", "R"}


@dataclass(frozen=True)
class RxRecord:
    record_id: str
    key: dict                                   # stage-appropriate matching key
    stages: dict[str, dict]                     # per-stage payload (isolation unit)
    polarity: int = 0                           # +1 positive / -1 negative / 0 neutral
    priority_hint: float = 0.0                  # ordering only; NEVER a ground
    provenance: dict = field(default_factory=dict)   # {observation_id, interpretation_version, decision_id}
    versions: dict = field(default_factory=dict)     # {formalizer_schema_version, framegen_version, ...}
    status: str = LIVE


class FormalizationCache:
    def __init__(self, current_versions: dict[str, str]) -> None:
        self._current = dict(current_versions)
        self._records: dict[str, RxRecord] = {}

    # -- writes ------------------------------------------------------------ #
    def record(self, rec: RxRecord) -> None:
        self._records[rec.record_id] = rec

    def note_rejection(self, key: dict, stage: str, ground_type: str, *, versions: dict | None = None) -> bool:
        """Record NEGATIVE experience only for D/C/R rejections. Returns False (no-op) otherwise."""
        if ground_type not in _NEGATIVE_GROUNDS:
            return False  # computational diagnostics are NOT negative experience
        rid = f"neg-{abs(hash((tuple(sorted(key.items())), stage, ground_type)))}"
        self._records[rid] = RxRecord(
            record_id=rid, key=dict(key), stages={stage: {"rejected": True}},
            polarity=-1, priority_hint=-1.0, versions=dict(self._current if versions is None else versions),
        )
        return True

    # -- reads (stage-isolated) ------------------------------------------- #
    def _versions_match(self, rec: RxRecord) -> bool:
        for k, v in self._current.items():
            if rec.versions.get(k) != v:
                return False
        return True

    def read_for_stage(self, stage: str, key: dict) -> list[tuple[str, dict]]:
        """Return (record_id, payload) for LIVE, version-matching records of THIS stage only."""
        out = []
        for rec in self._records.values():
            if rec.status != LIVE or not self._versions_match(rec):
                continue
            if stage not in rec.stages:
                continue  # hard isolation: a T1 read can never surface R-X3 semantic fields
            if _key_matches(rec.key, key):
                out.append((rec.record_id, dict(rec.stages[stage])))
        return out

    def rank(self, stage: str, candidates: Sequence[str], key: dict) -> list[str]:
        """Reorder the FULL admissible set by cached priority; NEVER exclude a candidate."""
        hints: dict[str, float] = {}
        for _rid, payload in self.read_for_stage(stage, key):
            for cand, hint in (payload.get("priorities") or {}).items():
                # most negative wins the ordering slot but the candidate is still present
                hints[cand] = max(hints.get(cand, float("-inf")), float(hint))
        return sorted(candidates, key=lambda c: (-hints.get(c, 0.0), c))

    # -- supersession ------------------------------------------------------ #
    def supersede(self, interpretation_version: str) -> int:
        """Flip a version's LIVE records to SUPERSEDED (no deletion). Returns count changed."""
        n = 0
        for rid, rec in self._records.items():
            if rec.status == LIVE and rec.provenance.get("interpretation_version") == interpretation_version:
                self._records[rid] = RxRecord(
                    record_id=rec.record_id, key=rec.key, stages=rec.stages, polarity=rec.polarity,
                    priority_hint=rec.priority_hint, provenance=rec.provenance, versions=rec.versions,
                    status=SUPERSEDED,
                )
                n += 1
        return n

    def migrate(self, record_id: str, new_versions: dict) -> bool:
        """Explicitly re-version a stale record (never auto-applied).

        ``new_versions`` is merged over the record's existing versions so unspecified keys keep
        their prior value; the result must still satisfy :meth:`_versions_match` to become readable.
        """
        rec = self._records.get(record_id)
        if rec is None or rec.status != LIVE:
            return False
        merged = {**rec.versions, **new_versions}
        self._records[record_id] = RxRecord(
            record_id=rec.record_id, key=rec.key, stages=rec.stages, polarity=rec.polarity,
            priority_hint=rec.priority_hint, provenance=rec.provenance, versions=merged, status=LIVE,
        )
        return True

    def all_records(self) -> tuple[RxRecord, ...]:  # audit view (includes superseded/stale)
        return tuple(self._records.values())


def _key_matches(rec_key: dict, query: dict) -> bool:
    """Exact key equality on the shared fields (StructuralPattern for R-X2, etc.)."""
    return all(rec_key.get(k) == v for k, v in query.items())
