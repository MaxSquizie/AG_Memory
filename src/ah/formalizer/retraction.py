# -*- coding: utf-8 -*-
"""Retraction protocol (V7 §8) — decide whether a fact survives evidence retraction.

Core rule (frozen): retracting ALL of a fact's *direct observations* does NOT cancel the fact
if an INDEPENDENT, COMPLETE piece of evidence remains. Independence is judged by EXACT tag
equality for identity: two evidences are "the same" only when their tag sets match exactly, so
re-recording the same observation under a new id never manufactures independent support.

Two non-interchangeable levels (kept separate on purpose):
* OBSERVATION level — individual raw observations are retracted.
* INTERPRETATION level — an interpretation version is superseded wholesale.
This module implements the observation-level decision; interpretation-level supersession is a
whole-version transition handled by the store's status machinery, not by per-evidence logic here.

Application is atomic: :meth:`RetractionProtocol.apply` performs the decision and, when it
changes the fact's status, commits ONE durable store transaction (all-or-nothing), so a crash
mid-retraction cannot leave a half-applied state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .store_interface import AssertionStatus, Store


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence supporting a fact."""

    id: str
    tags: frozenset[str]                 # exact identity (two items are the same iff tags equal)
    source_observation_id: str | None = None  # None => independent channel, not a direct observation
    complete: bool = True                # sufficient on its own to support the fact


@dataclass(frozen=True)
class RetractionOutcome:
    survives: bool                       # does the fact remain valid after retraction?
    new_status: AssertionStatus          # LIVE if it survives, SUPERSEDED otherwise
    surviving_independent: tuple[str, ...]  # ids of independent complete evidence that kept it alive


def same_identity(a: EvidenceItem, b: EvidenceItem) -> bool:
    """EXACT tag equality — the only identity relation used for independence."""
    return a.tags == b.tags


class RetractionProtocol:
    def __init__(self, store: Store | None = None) -> None:
        self._store = store

    # -- pure decision ----------------------------------------------------- #
    def decide(self, evidence: Sequence[EvidenceItem], retracted_ids: Sequence[str]) -> RetractionOutcome:
        """Pure decision (no store needed): does the fact survive retracting ``retracted_ids``?"""
        retracted = set(retracted_ids)

        def _removed(e: EvidenceItem) -> bool:
            if e.id in retracted:
                return True
            # A direct observation whose source is being retracted is gone with it.
            return e.source_observation_id is not None and e.source_observation_id in retracted

        # Tags of everything removed — a survivor with these EXACT tags is NOT independent.
        removed_tags = [e.tags for e in evidence if _removed(e)]

        survivors_independent: list[str] = []
        for e in evidence:
            if _removed(e):
                continue
            if not e.complete:
                continue  # incomplete evidence never carries a fact alone
            # Exact-tag identity: same tags as something removed => not independent.
            if any(e.tags == t for t in removed_tags):
                continue
            survivors_independent.append(e.id)

        survives = len(survivors_independent) > 0
        status = AssertionStatus.LIVE if survives else AssertionStatus.SUPERSEDED
        return RetractionOutcome(survives, status, tuple(survivors_independent))

    # -- atomic application ------------------------------------------------ #
    def apply(self, assertion_id: str, evidence: Sequence[EvidenceItem], retracted_ids: Sequence[str]) -> RetractionOutcome:
        """Decide and, if the fact is invalidated, atomically transition its status.

        Returns the outcome; when ``self._store`` is present a SUPERSEDED result is committed as
        one durable transaction (retraction without deletion — the assertion record remains).
        """
        outcome = self.decide(evidence, retracted_ids)
        if not outcome.survives and self._store is not None:
            self._store.retract(assertion_id, AssertionStatus.SUPERSEDED, reason="independent evidence exhausted")
        return outcome
