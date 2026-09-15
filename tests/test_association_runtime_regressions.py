from __future__ import annotations

from ah.model import ActantRole
from ah.perception.association_continuation import (
    AssociationContinuationLLMPerceptionService,
    normalize_correlative_actant_compositions,
)
from ah.perception.association_goal_semantics import AssociationGoalSemanticService
from ah.perception.association_semantics import (
    AssociationEndpointSelector,
    AssociationQueryDecision,
)
from ah.perception.contracts import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
)


def _evidence(text: str, fragment: str, *, after: int = 0) -> EvidenceSpan:
    start = text.index(fragment, after)
    return EvidenceSpan(fragment, start, start + len(fragment))


def test_correlative_object_pair_becomes_one_object_composition() -> None:
    text = "Вчера во дворе я видел и ворону, и стол"
    crow_evidence = _evidence(text, "ворону")
    table_evidence = _evidence(text, "стол")
    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate("видел", normalized_hint="видеть"),
        actants=(
            ActantCandidate(
                ActantRole.TIME,
                mention="Вчера",
                normalized_hint="вчера",
                evidence=_evidence(text, "Вчера"),
            ),
            ActantCandidate(
                ActantRole.LOCATION,
                mention="дворе",
                normalized_hint="двор",
                evidence=_evidence(text, "дворе"),
            ),
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="я",
                normalized_hint="я",
                evidence=_evidence(text, "я", after=text.index("дворе")),
            ),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="ворону",
                normalized_hint="ворона",
                evidence=crow_evidence,
            ),
            ActantCandidate(
                ActantRole.AUXILLIARY,
                mention="стол",
                normalized_hint="стол",
                evidence=table_evidence,
            ),
        ),
    )

    normalized = normalize_correlative_actant_compositions(
        PerceptionResult(source_text=text, assertions=(assertion,))
    )

    rewritten = normalized.assertions[0]
    assert tuple(item.role for item in rewritten.actants) == (
        ActantRole.TIME,
        ActantRole.LOCATION,
        ActantRole.SUBJECT,
        ActantRole.OBJECT,
    )
    grouped = rewritten.actants[-1]
    assert grouped.composition is not None
    assert grouped.role is ActantRole.OBJECT
    assert tuple(member.normalized_hint for member in grouped.composition.members) == (
        "ворона",
        "стол",
    )


def test_association_goal_probe_sees_two_participants_not_commonality_state() -> None:
    text = "Что общего между вороной и столом?"
    query = QueryCandidate(
        predicate=PredicateCandidate("быть", normalized_hint="быть"),
        actants=(
            ActantCandidate(
                ActantRole.STATE,
                mention="общего",
                normalized_hint="общий",
                evidence=_evidence(text, "общего"),
            ),
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="вороной",
                normalized_hint="ворона",
                evidence=_evidence(text, "вороной"),
            ),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="столом",
                normalized_hint="стол",
                evidence=_evidence(text, "столом"),
            ),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )

    class Classifier:
        seen_roles = None

        def classify_association_query(self, source_text, root):
            assert source_text == text
            self.seen_roles = tuple(item.role for item in root.actants)
            return AssociationQueryDecision(
                AssociationEndpointSelector(ActantRole.SUBJECT),
                AssociationEndpointSelector(ActantRole.OBJECT),
            )

    classifier = Classifier()
    completed = AssociationGoalSemanticService(classifier).complete(
        PerceptionResult(source_text=text, queries=(query,))
    )

    assert classifier.seen_roles == (ActantRole.SUBJECT, ActantRole.OBJECT)
    assert len(completed.act_relations) == 1
    relation = completed.act_relations[0]
    assert relation.canonical_relation_id == "ASSOCIATION"
    assert relation.source_role is ActantRole.SUBJECT
    assert relation.target_role is ActantRole.OBJECT


def test_production_perception_service_exposes_association_probe() -> None:
    assert callable(
        getattr(AssociationContinuationLLMPerceptionService, "classify_association_query", None)
    )
