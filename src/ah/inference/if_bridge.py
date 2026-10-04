# -*- coding: utf-8 -*-
"""IF / hypothetical -> production GoalMode seam (V7 §6.2/§6.3).

Bridges the experimental text-level IF surface (:mod:`ah.formalizer.if_query`, which keeps a toy in-memory store and a
declared connective set) to the *production* counterfactual path, which is deliberately **typed and non-lexical**:
Perception marks an assumption ``AssertionStatus.HYPOTHETICAL`` + a QUERY root linked by a SUBORDINATE act dependency;
:func:`ah.perception.apply_speech_act_scoping` then exposes the shadow target and :class:`CounterfactualSemanticGoalCompiler`
owns the goal. Surface words such as ``если`` are *not* authority here — only paired clause boundaries (from morphological
categories via :mod:`ah.formalizer.tag_source`) open a counterfactual scope, matching the two-tier invariant.

:func:`if_to_perception` converts IF clause detection into that typed perception boundary so the existing production
machinery consumes it unchanged. It is additive: it never writes canonical AH and never invents a world from unpaired text.
"""

from __future__ import annotations

import re

from ah.formalizer.tag_source import tokenize
from ah.model import ActantRole
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
)

_NOUN = frozenset({"NOUN"})
_VERB = frozenset({"VERB", "INFN"})
_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+$")


def _first_pos(tag_source, clause_text: str, pos_set: frozenset[str]) -> str | None:
    """First content word whose morph category is in ``pos_set`` (morph category -> syntax; never lexical)."""
    for word in tokenize(clause_text):
        if not _LETTER_RE.match(word):
            continue
        if tag_source.label(word) in pos_set:
            return word
    return None


def _clause_predicate(tag_source, clause_text: str) -> tuple[PredicateCandidate, tuple[ActantCandidate, ...]]:
    """Minimal structurally-derived predicate + subject for one clause (enough for the scoping boundary)."""
    subject = _first_pos(tag_source, clause_text, _NOUN)
    predicate = _first_pos(tag_source, clause_text, _VERB) or subject or "P"
    actants = (ActantCandidate(ActantRole.SUBJECT, mention=subject),) if subject else ()
    return PredicateCandidate(predicate, predicate, template_candidate=TemplateCandidate((ActantRole.SUBJECT,))), actants


def if_to_perception(text: str, tag_source=None) -> PerceptionResult | None:
    """Convert IF clause detection into a typed counterfactual perception.

    Returns ``None`` (honest UNBOUND) when there are no paired IF boundaries — a single-clause input or an unpaired
    subordinator never opens a counterfactual scope, regardless of surface words. Otherwise the antecedent becomes a
    HYPOTHETICAL assertion and the consequent a QUERY target linked by a SUBORDINATE dependency, exactly the shape
    :func:`ah.perception.apply_speech_act_scoping` consumes.
    """
    if tag_source is None:
        from ah.formalizer.tag_source import TagSource

        tag_source = TagSource()
    structure = tag_source.detect(text)
    pairs = structure.if_pairs()
    if not pairs:
        return None

    ant_idx, con_idx = pairs[0]
    clauses = structure.clauses
    assumption_pred, assumption_actants = _clause_predicate(tag_source, clauses[ant_idx].text)
    target_pred, target_actants = _clause_predicate(tag_source, clauses[con_idx].text)

    assumption = AssertionCandidate(
        "A1",
        assumption_pred,
        assumption_actants,
        status=AssertionStatus.HYPOTHETICAL,
    )
    query = QueryCandidate(
        target_pred,
        target_actants,
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    return PerceptionResult(
        text,
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),),
    )


__all__ = ["if_to_perception"]
