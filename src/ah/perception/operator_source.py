from __future__ import annotations

"""Common source-consumption boundary for semantic operator material.

Semantic formalizers run after the initial frame extraction because they need
complete proposition candidates.  Consequently an operator cue may already have
been provisionally attached as an ordinary actant.  Once a bounded formalizer has
registered the exact cue span, this module guarantees that the same source bytes
cannot survive as ordinary predicate/actant semantics.
"""

from dataclasses import replace
from typing import Sequence

from .contracts import (
    AssertionCandidate,
    EvidenceSpan,
    PropositionRootCandidate,
    TemplateCandidate,
)


class OperatorSourceConsumptionError(ValueError):
    """Raised when consuming a registered operator span would break its formula."""


def _bounds(evidence: EvidenceSpan | None) -> tuple[int, int] | None:
    if evidence is None or evidence.start is None or evidence.end is None:
        return None
    return int(evidence.start), int(evidence.end)


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and left[1] > right[0]


def consume_operator_source_spans(
    assertions: Sequence[AssertionCandidate],
    spans: Sequence[EvidenceSpan],
    roots: Sequence[PropositionRootCandidate],
    *,
    discard_source_refs: Sequence[str] = (),
) -> tuple[AssertionCandidate, ...]:
    """Remove registered operator material from provisional ordinary frames.

    Whole operator-source frames referenced by a proposition root are retained as
    provenance records; Integration already excludes those frames from world facts.
    A source ref with no semantic wrapper (for example an actuality discourse
    marker) is explicitly discarded.  Any actant overlapping a consumed span is
    removed as one provisional semantic unit, and its template role is removed with
    it.  A consumed predicate may be discarded only when no formula leaf references
    that assertion.
    """

    consumed = tuple(bound for item in spans if (bound := _bounds(item)) is not None)
    if not consumed and not discard_source_refs:
        return tuple(assertions)

    operator_refs = {
        ref for root in roots for ref in root.operator_source_refs
    }
    leaf_refs = {ref for root in roots for ref in root.expression.leaf_refs()}
    discard = set(discard_source_refs) - operator_refs
    rewritten: list[AssertionCandidate] = []

    for assertion in assertions:
        if assertion.local_id in discard:
            if assertion.local_id in leaf_refs:
                raise OperatorSourceConsumptionError(
                    "Consumed operator source is still referenced as a formula leaf: "
                    f"{assertion.local_id}"
                )
            continue
        if assertion.local_id in operator_refs:
            rewritten.append(assertion)
            continue

        predicate_span = _bounds(assertion.predicate.evidence)
        if predicate_span is not None and any(
            _overlaps(predicate_span, span) for span in consumed
        ):
            if assertion.local_id in leaf_refs:
                raise OperatorSourceConsumptionError(
                    "Consumed operator span overlaps a formula-leaf predicate: "
                    f"{assertion.local_id}"
                )
            continue

        actants = tuple(
            actant
            for actant in assertion.actants
            if not (
                (actant_span := _bounds(actant.evidence)) is not None
                and any(_overlaps(actant_span, span) for span in consumed)
            )
        )
        if actants == assertion.actants:
            rewritten.append(assertion)
            continue

        predicate = assertion.predicate
        proposed = predicate.template_candidate
        if proposed is not None:
            remaining_roles = {item.role for item in actants}
            predicate = replace(
                predicate,
                template_candidate=TemplateCandidate(
                    tuple(role for role in proposed.roles if role in remaining_roles)
                ),
            )
        rewritten.append(
            replace(assertion, predicate=predicate, actants=actants)
        )

    return tuple(rewritten)
