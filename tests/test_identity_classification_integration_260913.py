from __future__ import annotations

from datetime import datetime, timezone

from ah.agent import InteractionContext
from ah.config import IntegrationSettings
from ah.core import AHCore
from ah.inference import QueryGoalBuilder, RelationGoal
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
)
from ah.perception.goal_semantics import GoalSemanticService


def test_user_classification_is_fact_not_identity_alias() -> None:
    core = AHCore()
    user = core.add_entity(
        Domain.P,
        {"name": Property("name", "Пользователь", "str")},
        {"identity_role": "USER"},
    )
    agent = core.add_entity(
        Domain.P,
        {"name": Property("name", "Агент", "str")},
        {"identity_role": "SELF"},
    )
    context = InteractionContext(
        user_ref=core.ref(user.uid),
        self_ref=core.ref(agent.uid),
    )
    integration = IntegrationService(
        core,
        IntegrationConfig.from_settings(IntegrationSettings()),
    )

    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "инженер",
            normalized_hint="инженер",
            sense_hint="NOMINAL_PREDICATION",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Я",
                normalized_hint="я",
                grammatical_number="sing",
            ),
        ),
    )

    class TaxonomyClassifier:
        def classify_nominal_taxonomy(self, source_text, predicate, subject):
            return "SUBJECT_IS_PREDICATE"

    perception = GoalSemanticService(TaxonomyClassifier()).complete(
        PerceptionResult(source_text="Я инженер", assertions=(assertion,))
    )
    commit = integration.integrate_external(
        perception,
        context,
        source_timestamp=datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc),
    )

    assert len(commit.assertions) == 1
    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    assert node.actants[ActantRole.SUBJECT] == core.ref(user.uid)
    assert core.store.find_entities_by_name("инженер", Domain.P) == ()
    class_entity = next(
        item
        for item in core.store.find_entities_by_name("инженер", Domain.C)
        if item.meta.get("taxonomy_class") is True
    )
    assert core.store.find_link("IS-A", user.uid, class_entity.uid) is not None

    query = QueryCandidate(
        PredicateCandidate(
            "инженер",
            normalized_hint="инженер",
            sense_hint="TAXONOMIC_PREDICATION",
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention="я", normalized_hint="я"),),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    built = QueryGoalBuilder(core).build(query, context)
    assert built.goal is not None
    assert built.goal.goal.target == RelationGoal(
        "IS-A", core.ref(user.uid), core.ref(class_entity.uid)
    )
