from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .contracts import (
    ActRelationCandidate,
    ActantCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    QueryMode,
)


class ActRelationClassifier(Protocol):
    def classify_act_relation(
        self,
        source_text: str,
        act_ref: str,
        predicate: PredicateCandidate,
        actants: tuple[ActantCandidate, ...],
    ) -> ActRelationCandidate | None: ...


class GoalSemanticService:
    """Complete only the semantic relation type required by goal compilation.

    Deterministic Perception has already produced predicates, actants, roles,
    speech-act structure and scope.  This service may ask one bounded semantic
    question for an eligible act: whether it expresses a registered intra-act
    structural relation (currently IS-A) and which already-known roles are its
    endpoints.  It never reads or writes AH and never receives canonical UIDs.
    """

    def __init__(self, classifier: object) -> None:
        self.classifier = classifier

    def complete(self, result: PerceptionResult) -> PerceptionResult:
        classify = getattr(self.classifier, "classify_act_relation", None)
        if not callable(classify):
            return result

        relations = list(result.act_relations)
        covered = {item.act_ref for item in relations}

        # Ordinary asserted facts are classified too, so a statement such as a
        # class-membership proposition can create the canonical IS-A L used by
        # future inference. EMBEDDED content is classified for goal compilation
        # but Integration must not materialize it as truth.
        for assertion in result.assertions:
            if assertion.local_id in covered or assertion.quoted:
                continue
            if assertion.status not in {AssertionStatus.ASSERTED, AssertionStatus.EMBEDDED}:
                continue
            # A noun-headed copular/nominal-predication frame already encodes its
            # predicate relation in T/N.  Treating an arbitrary complement of that
            # nominal predicate as the target of IS-A (e.g. NAME(X, owner's Y)) is
            # a category error.  Unary class predicates still work directly as N;
            # explicit non-nominal classification frames remain eligible below.
            if assertion.predicate.sense_hint == "NOMINAL_PREDICATION":
                continue
            relation = classify(
                result.source_text,
                assertion.local_id,
                assertion.predicate,
                assertion.actants,
            )
            if relation is not None:
                relations.append(relation)
                covered.add(assertion.local_id)

        for query in result.queries:
            if (
                query.local_id is None
                or query.local_id in covered
                or query.quoted
                or query.query_mode is not QueryMode.EXISTS
                or query.predicate.sense_hint == "NOMINAL_PREDICATION"
            ):
                continue
            relation = classify(
                result.source_text,
                query.local_id,
                query.predicate,
                query.actants,
            )
            if relation is not None:
                relations.append(relation)
                covered.add(query.local_id)

        completed = tuple(relations)
        if completed == result.act_relations:
            return result
        return replace(result, act_relations=completed)
