from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from ah.model import ActantRole

from .contracts import (
    ActRelationCandidate,
    ActantCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    QueryMode,
    TemplateCandidate,
)
from .query_semantics import EntityIdentityQueryCandidate


class ActRelationClassifier(Protocol):
    def classify_act_relation(
        self,
        source_text: str,
        act_ref: str,
        predicate: PredicateCandidate,
        actants: tuple[ActantCandidate, ...],
    ) -> ActRelationCandidate | None: ...

    def classify_nominal_taxonomy(
        self,
        source_text: str,
        predicate: PredicateCandidate,
        subject: ActantCandidate,
    ) -> str | None: ...


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
        classify_nominal = getattr(
            self.classifier, "classify_nominal_taxonomy", None
        )
        if not callable(classify) and not callable(classify_nominal):
            return result

        def complete_nominal(root):
            if (
                not callable(classify_nominal)
                or isinstance(root, EntityIdentityQueryCandidate)
                or root.quoted
                or root.predicate.sense_hint != "NOMINAL_PREDICATION"
                or len(root.actants) != 1
                or root.actants[0].role is not ActantRole.SUBJECT
                or (
                    hasattr(root, "query_mode")
                    and root.query_mode is not QueryMode.EXISTS
                )
            ):
                return root
            subject = root.actants[0]
            if (
                subject.candidate_ref is not None
                or subject.entity_ref is not None
                or subject.composition is not None
                or subject.proposition is not None
                or subject.quantifier is not None
                or subject.lookup_text is None
            ):
                return root
            decision = classify_nominal(
                result.source_text, root.predicate, subject
            )
            if decision == "SUBJECT_IS_PREDICATE":
                return replace(
                    root,
                    predicate=replace(
                        root.predicate, sense_hint="TAXONOMIC_PREDICATION"
                    ),
                )
            if decision != "PREDICATE_IS_SUBJECT":
                return root

            # Normalize reversed nominal order (for example ``Инженер — это я``)
            # into the same unary class predicate as ``Я — инженер``. Both sides
            # were already isolated by Perception; the bounded classifier only
            # selects their semantic orientation.
            predicate = PredicateCandidate(
                surface=subject.mention or subject.lookup_text,
                normalized_hint=subject.normalized_hint,
                sense_hint="TAXONOMIC_PREDICATION",
                evidence=subject.evidence,
                template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
            )
            normalized_subject = ActantCandidate(
                ActantRole.SUBJECT,
                mention=root.predicate.surface,
                normalized_hint=root.predicate.normalized_hint,
                evidence=root.predicate.evidence,
            )
            return replace(root, predicate=predicate, actants=(normalized_subject,))

        assertions = tuple(complete_nominal(item) for item in result.assertions)
        queries = tuple(complete_nominal(item) for item in result.queries)
        result = replace(result, assertions=assertions, queries=queries)

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
            if assertion.predicate.sense_hint in {
                "NOMINAL_PREDICATION", "TAXONOMIC_PREDICATION"
            }:
                continue
            if not callable(classify):
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
                isinstance(query, EntityIdentityQueryCandidate)
                or query.local_id is None
                or query.local_id in covered
                or query.quoted
                or query.query_mode is not QueryMode.EXISTS
                or query.predicate.sense_hint in {
                    "NOMINAL_PREDICATION", "TAXONOMIC_PREDICATION"
                }
            ):
                continue
            if not callable(classify):
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
