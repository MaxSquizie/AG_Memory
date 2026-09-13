from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ah.agent import InteractionContext
from ah.config import InferenceSettings, IntegrationSettings
from ah.core import AHCore
from ah.inference import CompositeConclusion, ExistingRefConclusion, InferenceEngine, LogicalStatus, QueryGoalBuilder
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EventSetQueryCandidate,
    NamingAssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryMode,
    TemplateCandidate,
)


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
    context = InteractionContext(
        user_ref=core.ref(user.uid),
        self_ref=core.ref(agent.uid),
    )
    integration = IntegrationService(
        core,
        IntegrationConfig.from_settings(IntegrationSettings()),
    )
    return core, context, integration


def _assertion(predicate: str, object_name: str, local_id: str) -> AssertionCandidate:
    return AssertionCandidate(
        local_id=local_id,
        predicate=PredicateCandidate(
            predicate,
            normalized_hint=predicate,
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME)
            ),
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="я",
                normalized_hint="я",
            ),
            ActantCandidate(
                ActantRole.OBJECT,
                mention=object_name,
                normalized_hint=object_name,
            ),
            ActantCandidate(
                ActantRole.TIME,
                mention="вчера",
                normalized_hint="вчера",
            ),
        ),
    )


def test_naming_assertion_enriches_user_identity_without_false_world_fact() -> None:
    core, context, integration = _runtime()
    naming = NamingAssertionCandidate(
        local_id="NAME1",
        predicate=PredicateCandidate(
            "Илья",
            normalized_hint="Илья",
            sense_hint="NOMINAL_PREDICATION",
        ),
        actants=(
            ActantCandidate(
                ActantRole.STATE,
                mention="Моё имя",
                normalized_hint="имя",
            ),
        ),
        owner=ActantCandidate(ActantRole.SUBJECT, mention="моё"),
        name_value="Илья",
        name_normalized_hint="Илья",
    )

    commit = integration.integrate_external(
        PerceptionResult("Моё имя — Илья", assertions=(naming,)),
        context,
        source_timestamp=datetime(2026, 9, 13, 18, 0, tzinfo=timezone(timedelta(hours=3))),
    )

    assert commit.assertions == ()
    matches = core.store.find_entities_by_name("Илья")
    assert tuple(item.uid for item in matches) == (context.user_ref.uid,)
    assert core.store.find_symbols_by_form("Илья") == ()
    experience = core.store.get_hypernode(commit.experience_ref.uid)
    assert "ASSERTION" in tuple(experience.meta.get("speech_act_kinds", ()))


def test_open_event_query_reuses_identity_and_exact_relative_time() -> None:
    core, context, integration = _runtime()
    turn_time = datetime(
        2026, 9, 13, 18, 0, tzinfo=timezone(timedelta(hours=3))
    )

    naming = NamingAssertionCandidate(
        local_id="NAME1",
        predicate=PredicateCandidate(
            "Илья",
            normalized_hint="Илья",
            sense_hint="NOMINAL_PREDICATION",
        ),
        actants=(ActantCandidate(ActantRole.STATE, mention="Моё имя", normalized_hint="имя"),),
        owner=ActantCandidate(ActantRole.SUBJECT, mention="моё"),
        name_value="Илья",
    )
    integration.integrate_external(
        PerceptionResult("Моё имя — Илья", assertions=(naming,)),
        context,
        source_timestamp=turn_time,
    )

    first = integration.integrate_external(
        PerceptionResult(
            "Я вчера сделал последний запрос к системе",
            assertions=(_assertion("сделать", "запрос", "A1"),),
        ),
        context,
        source_timestamp=turn_time,
    )
    second = integration.integrate_external(
        PerceptionResult(
            "Вчера я выпил зелёного чаю",
            assertions=(_assertion("выпить", "чай", "A2"),),
        ),
        context,
        source_timestamp=turn_time,
    )

    first_node = core.store.get_hypernode(first.assertions[0].ref.uid)
    second_node = core.store.get_hypernode(second.assertions[0].ref.uid)
    assert first_node.actants[ActantRole.TIME] == second_node.actants[ActantRole.TIME]

    event_query = EventSetQueryCandidate(
        predicate=PredicateCandidate("делал", normalized_hint="делать"),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Илья",
                normalized_hint="Илья",
            ),
            ActantCandidate(
                ActantRole.TIME,
                mention="вчера",
                normalized_hint="вчера",
            ),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    query_commit = integration.integrate_external(
        PerceptionResult("Что вчера делал Илья?", queries=(event_query,)),
        context,
        source_timestamp=turn_time,
    )

    assert len(query_commit.unresolved_queries) == 1
    normalized_query = query_commit.unresolved_queries[0]
    assert isinstance(normalized_query, EventSetQueryCandidate)
    time_actant = next(
        item for item in normalized_query.actants if item.role is ActantRole.TIME
    )
    assert time_actant.temporal is not None and time_actant.temporal.resolved
    assert time_actant.temporal.value.start == "2026-09-12"
    # The interrogative shell is runtime semantics, not a canonical predicate/T.
    assert core.store.find_symbols_by_form("делать") == ()

    built = QueryGoalBuilder(core).build(normalized_query, context)
    assert built.goal is not None, built.diagnostics
    outcome = InferenceEngine(core, InferenceSettings()).solve(built.goal)

    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.conclusion, CompositeConclusion)
    assert len(outcome.conclusion.conclusions) == 2
    assert all(
        isinstance(item, ExistingRefConclusion)
        for item in outcome.conclusion.conclusions
    )
    assert {item.ref.uid for item in outcome.conclusion.conclusions} == {
        first.assertions[0].ref.uid,
        second.assertions[0].ref.uid,
    }
