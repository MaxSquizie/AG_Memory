from __future__ import annotations

from datetime import datetime, timezone

from ah.agent import InteractionContext
from ah.config import IntegrationSettings
from ah.core import AHCore
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)


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

    commit = integration.integrate_external(
        PerceptionResult(source_text="Я инженер", assertions=(assertion,)),
        context,
        source_timestamp=datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc),
    )

    assert len(commit.assertions) == 1
    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    assert node.actants[ActantRole.SUBJECT] == core.ref(user.uid)
    assert core.store.find_entities_by_name("инженер", Domain.P) == ()
