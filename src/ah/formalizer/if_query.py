# -*- coding: utf-8 -*-
"""IF / hypothetical answer surface (V7 §6.2/§6.3, Phase-1 experimental glue): wire clause detection into the goal path.

This bridges the pieces built separately this cycle — :mod:`ah.formalizer.tag_source` (pymorphy3 -> tagged tokens) and
:mod:`ah.formalizer.clause_detection` (paired IF boundaries) — with the interrogative compiler (:func:`interrogatives.compile`)
and a minimal, injectable fact store. It is deliberately an **experimental Phase-1 surface** for the IF/hypothetical class,
kept decoupled from the OR_ELIMINATION/FORALL_INST goal channel (which has its own temporal-license contract) so it can be
validated in isolation and later folded into the production GoalMode without a rewrite.

**STATUS / boundary.** This module is an *isolated experimental surface*: it keeps its own toy :class:`IfStore` and a
declared connective set (:data:`_CONNECTIVES`) purely for store-content normalization. It is **not** the production path
and must not be treated as one. The production GoalMode seam for IF/hypothetical questions is
:func:`ah.inference.if_bridge.if_to_perception`, which converts paired-clause detection into the *typed, non-lexical*
counterfactual perception (HYPOTHETICAL assumption + QUERY target + SUBORDINATE dependency) consumed by
``apply_speech_act_scoping`` -> ``CounterfactualSemanticGoalCompiler`` -> ``InferenceEngine``. Surface words are never
authority there; only paired morphological boundaries open a counterfactual scope. Do not add production logic here.

Honest outcomes (never guessed):
* ``UNBOUND``      — no paired clause boundaries (single-clause / detector absent). Reuses :func:`interrogatives.compile`'s gate.
* ``NOT_ASSERTED`` — the antecedent is not an established fact in the store; an implication with an unestablished premise
                     cannot be evaluated.
* ``INSUFFICIENT`` — the antecedent holds but the consequent is neither asserted nor derivable from it here.
* ``ANSWERED``     — both antecedent and consequent are established -> the conditional holds in this context (``holds=True``).

The connective word (если/когда/...) is a *declared* structural marker, not proposition content: it is stripped before store
matching but preserved in the reported spans. Pure module; no store/network/morphology access at import — everything injected.
Deterministic for a fixed store + text.
"""

from __future__ import annotations

from dataclasses import dataclass

from ah.formalizer.interrogatives import compile as _compile, CLAUSE_DETECTION_REQUIRED


# Declared connectives (structural markers, not content). Mirrors the detector's declared subordinators.
_CONNECTIVES = frozenset({"если", "когда", "хотя", "пока", "чтобы", "дабы"})
_PUNCT = ".,;:!?…"


@dataclass(frozen=True)
class IfAnswer:
    status: str                 # ANSWERED | UNBOUND | NOT_ASSERTED | INSUFFICIENT
    antecedent: str = ""        # full antecedent clause text (connective included)
    consequent: str = ""        # full consequent clause text
    holds: bool | None = None   # True only when status == ANSWERED
    reason: str | None = None


def _content(text: str) -> str:
    """Strip a leading declared connective so the store matches proposition content, not the marker."""
    parts = text.split()
    if len(parts) > 1 and parts[0].lower().strip(_PUNCT) in _CONNECTIVES:
        return " ".join(parts[1:])
    return text


class IfStore:
    """Minimal fact store for the IF surface. Override :meth:`asserted`; default is an in-memory set of claims."""

    def __init__(self, facts=()):
        self._facts = {f.strip().lower() for f in facts}

    def asserted(self, claim: str) -> bool:
        return _content(claim).strip().lower() in self._facts


def answer_if(text: str, tag_source, store, request_kind: str = "IF") -> IfAnswer:
    """Answer an IF/hypothetical question end-to-end: text -> tagged tokens -> paired boundaries -> store evaluation.

    ``tag_source`` is a :class:`~ah.formalizer.tag_source.TagSource` (or anything with ``detect(text) -> ClauseStructure``);
    ``store`` exposes ``asserted(claim) -> bool``. The clause-scoped gate is delegated to the interrogative compiler, so an
    IF question over a single-clause input stays UNBOUND rather than being guessed.
    """
    structure = tag_source.detect(text)

    q = _compile(request_kind, clause_detector=structure)
    if q.status != "COMPILED":
        return IfAnswer("UNBOUND", reason=q.reason or CLAUSE_DETECTION_REQUIRED)

    pairs = structure.if_pairs()
    if not pairs:  # defensive: the compiler gate already requires a pair, but stay honest regardless of detector shape
        return IfAnswer("UNBOUND", reason="NO_IF_PAIR")

    ant_idx, con_idx = pairs[0]
    clauses = structure.clauses
    ant, con = clauses[ant_idx].text, clauses[con_idx].text

    if not store.asserted(ant):
        return IfAnswer("NOT_ASSERTED", antecedent=ant, consequent=con, reason="ANTECEDENT_NOT_IN_STORE")
    if not store.asserted(con):
        return IfAnswer("INSUFFICIENT", antecedent=ant, consequent=con, reason="CONSEQUENT_NOT_DERIVED")
    return IfAnswer("ANSWERED", antecedent=ant, consequent=con, holds=True)


__all__ = ["IfAnswer", "IfStore", "answer_if"]
