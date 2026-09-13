from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ah.agent import InteractionContext
from ah.config import ContextSettings, InferenceSettings, IntegrationSettings
from ah.core import AHCore
from ah.inference import ExistingRefConclusion, InferenceEngine, LogicalStatus, QueryGoalBuilder
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.identity_entity_resolver import IdentityAwareEntityResolver
from ah.integration.identity_graph import (
    IDENTITY_NAME_RELATION,
    identity_name_refs_for_owner,
    is_identity_name_entity,
)
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    EntityIdentityQueryCandidate,
    NamingAssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryMode,
)
from ah.projection import ContextProjector


def _runtime():
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
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    integration = IntegrationService(
        core, IntegrationConfig.from_settings(IntegrationSettings())
    )
    return core, context, integration


def _name_user(integration, context, when):
    naming = NamingAssertionCandidate(
        local_id="NAME1",
        predicate=PredicateCandidate(
            "быть", normalized_hint="быть", sense_hint="IMPLICIT"
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT, mention="Я", normalized_hint="я",
                grammatical_number="sing",
            ),
            ActantCandidate(
                ActantRole.OBJECT, mention="Илья", normalized_hint="Илья",
                grammatical_number="sing",
            ),
        ),
        owner=ActantCandidate(
            ActantRole.SUBJECT, mention="Я", normalized_hint="я",
            grammatical_number="sing",
        ),
        name_value="Илья",
        name_normalized_hint="Илья",
    )
    integration.integrate_external(
        PerceptionResult("Я Илья", assertions=(naming,)),
        context,
        source_timestamp=when,
    )


def _identity_query(name: str) -> EntityIdentityQueryCandidate:
    target = ActantCandidate(
        ActantRole.OBJECT,
        mention=name,
        normalized_hint=name,
        grammatical_number="sing",
    )
    return EntityIdentityQueryCandidate(
        predicate=PredicateCandidate("быть", normalized_hint="быть", sense_hint="IMPLICIT"),
        actants=(target,),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
        target=target,
    )


def test_naming_creates_excitable_name_m_and_identity_link() -> None:
    core, context, integration = _runtime()
    when = datetime(2026, 9, 14, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    _name_user(integration, context, when)

    refs = identity_name_refs_for_owner(core, context.user_ref)
    assert len(refs) == 1
    name_ref = refs[0]
    assert core.store.domain_of(name_ref.uid) is Domain.C
    name_node = core.store.get_element_any_domain(name_ref.uid)
    assert is_identity_name_entity(name_node)
    assert name_node.properties["name"].value == "Илья"
    assert core.store.find_link(
        IDENTITY_NAME_RELATION, context.user_ref.uid, name_ref.uid
    ) is not None
    # C/P M nodes own runtime excitation state; the name is not hidden metadata.
    assert core.store.runtime_state(name_ref.uid) is not None


def test_reverse_name_resolution_returns_named_user_not_label_node() -> None:
    core, context, integration = _runtime()
    when = datetime(2026, 9, 14, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    _name_user(integration, context, when)

    candidate = ActantCandidate(
        ActantRole.SUBJECT,
        mention="Илья",
        normalized_hint="Илья",
        grammatical_number="sing",
    )
    resolved = IdentityAwareEntityResolver(core).resolve(candidate, context)
    assert resolved.ref == context.user_ref


def test_who_is_ilya_proves_identity_through_explicit_graph() -> None:
    core, context, integration = _runtime()
    when = datetime(2026, 9, 14, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    _name_user(integration, context, when)
    query = _identity_query("Илья")

    commit = integration.integrate_external(
        PerceptionResult("Кто такой Илья?", queries=(query,)),
        context,
        source_timestamp=when,
    )
    normalized = commit.unresolved_queries[0]
    built = QueryGoalBuilder(core).build(normalized, context)
    assert built.goal is not None, built.diagnostics
    outcome = InferenceEngine(core, InferenceSettings()).solve(built.goal)

    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.conclusion, ExistingRefConclusion)
    assert outcome.conclusion.ref == context.user_ref
    name_refs = identity_name_refs_for_owner(core, context.user_ref)
    assert name_refs[0] in outcome.uid_trace

    projected = ContextProjector(core, ContextSettings()).project(
        "Кто такой Илья?", (), (outcome,)
    )
    text = projected.rendered.casefold()
    assert "пользователь" in text
    assert "илья" in text
