from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ah.agent import InteractionContext
from ah.config import ContextSettings, InferenceSettings, IntegrationSettings
from ah.core import AHCore
from ah.diagnostics.m1_presentation import build_m1_formalization_view
from ah.inference import ExistingRefConclusion, InferenceEngine, LogicalStatus, QueryGoalBuilder
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EntityIdentityQueryCandidate,
    EventSetQueryCandidate,
    EvidenceSpan,
    NamingAssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryMode,
    TemplateCandidate,
)
from ah.projection import ContextProjector


def _runtime():
    core = AHCore()
    user = core.add_entity(
        Domain.P,
        {"name": Property("name", "пользователь", "str")},
        {"identity_role": "USER"},
    )
    agent = core.add_entity(
        Domain.P,
        {"name": Property("name", "агент", "str")},
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


def _name_user_ilya(integration, context, turn_time) -> None:
    naming = NamingAssertionCandidate(
        local_id="NAME1",
        predicate=PredicateCandidate(
            "Илья",
            normalized_hint="Илья",
            sense_hint="NOMINAL_PREDICATION",
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="я",
                normalized_hint="я",
            ),
        ),
        owner=ActantCandidate(ActantRole.SUBJECT, mention="я", normalized_hint="я"),
        name_value="Илья",
        name_normalized_hint="Илья",
    )
    integration.integrate_external(
        PerceptionResult("Я Илья", assertions=(naming,)),
        context,
        source_timestamp=turn_time,
    )


def _identity_query() -> EntityIdentityQueryCandidate:
    source = "А пользователь кто?"
    target_start = source.index("пользователь")
    target_end = target_start + len("пользователь")
    who_start = source.index("кто")
    who_end = who_start + len("кто")
    target = ActantCandidate(
        ActantRole.STATE,
        mention="пользователь",
        normalized_hint="пользователь",
        evidence=EvidenceSpan("пользователь", target_start, target_end),
        grammatical_number="sing",
    )
    return EntityIdentityQueryCandidate(
        predicate=PredicateCandidate("быть", normalized_hint="быть"),
        actants=(target,),
        query_mode=QueryMode.EXISTS,
        local_id="QID1",
        target=target,
        query_operator_evidence=(EvidenceSpan("кто", who_start, who_end),),
    )


def test_identity_query_is_detached_resolved_and_projected_with_alias() -> None:
    core, context, integration = _runtime()
    turn_time = datetime(
        2026, 9, 13, 23, 0, tzinfo=timezone(timedelta(hours=3))
    )
    _name_user_ilya(integration, context, turn_time)
    query = _identity_query()

    commit = integration.integrate_external(
        PerceptionResult("А пользователь кто?", queries=(query,)),
        context,
        source_timestamp=turn_time,
    )

    assert commit.assertions == ()
    assert tuple(commit.unresolved_queries) == (query,)
    # The surface copula is a query shell, not a fact/schema mutation.
    assert core.store.find_symbols_by_form("быть") == ()
    experience = core.store.get_hypernode(commit.experience_ref.uid)
    assert tuple(experience.meta.get("speech_act_kinds", ())) == ("QUERY",)

    built = QueryGoalBuilder(core).build(query, context)
    assert built.goal is not None, built.diagnostics
    outcome = InferenceEngine(core, InferenceSettings()).solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.conclusion, ExistingRefConclusion)
    assert outcome.conclusion.ref == context.user_ref

    projected = ContextProjector(core, ContextSettings()).project(
        "А пользователь кто?",
        (),
        (outcome,),
    )
    assert "пользователь" in projected.rendered.casefold()
    assert "илья" in projected.rendered.casefold()
    assert "одного и того же объекта" in projected.rendered.casefold()


def test_event_proof_keeps_alias_of_canonical_subject_visible() -> None:
    core, context, integration = _runtime()
    turn_time = datetime(
        2026, 9, 13, 23, 0, tzinfo=timezone(timedelta(hours=3))
    )
    _name_user_ilya(integration, context, turn_time)

    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "сделал",
            normalized_hint="сделать",
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.OBJECT)
            ),
        ),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="я", normalized_hint="я"),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="запрос",
                normalized_hint="запрос",
            ),
        ),
    )
    fact = integration.integrate_external(
        PerceptionResult("Я сделал запрос", assertions=(assertion,)),
        context,
        source_timestamp=turn_time,
    )
    assert len(fact.assertions) == 1

    query = EventSetQueryCandidate(
        predicate=PredicateCandidate("делал", normalized_hint="делать"),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Илья",
                normalized_hint="Илья",
                grammatical_number="sing",
            ),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="QE1",
    )
    query_commit = integration.integrate_external(
        PerceptionResult("Что делал Илья?", queries=(query,)),
        context,
        source_timestamp=turn_time,
    )
    normalized = query_commit.unresolved_queries[0]
    built = QueryGoalBuilder(core).build(normalized, context)
    assert built.goal is not None, built.diagnostics
    outcome = InferenceEngine(core, InferenceSettings()).solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.conclusion, ExistingRefConclusion)

    projected = ContextProjector(core, ContextSettings()).project(
        "Что делал Илья?",
        (),
        (outcome,),
    )
    rendered = projected.rendered.casefold()
    assert "пользователь" in rendered
    assert "илья" in rendered
    assert "тот же объект" in rendered


def test_identity_query_m1_shows_identity_not_copular_truth_check() -> None:
    query = _identity_query()
    view = build_m1_formalization_view(
        PerceptionResult("А пользователь кто?", queries=(query,))
    )

    assert view.prompt_type == "ЗАПРОС"
    assert view.prompt_detail == "Найти имя / идентичность сущности"
    assert len(view.frames) == 1
    frame = view.frames[0]
    assert frame.kind == "ЗАПРОС ИДЕНТИЧНОСТИ"
    assert frame.predicate == "IDENTITY_OF"
    assert [(role.role, role.value, role.requested) for role in frame.roles] == [
        ("ENTITY", "пользователь", False),
        ("NAME", "?", True),
    ]
    words = {word.text: (word.label, word.detail) for word in view.words}
    assert words["пользователь"] == ("ENTITY", "идентифицируемая сущность")
    assert words["кто"] == ("Оператор запроса", "IDENTITY")
    assert "истинность события" not in view.interpretation
