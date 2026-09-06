from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ah.agent import InteractionContext
from ah.config import PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.integration import (
    IntegrationConfig,
    IntegrationService,
    UnresolvedTemporalReferenceError,
)
from ah.model import ActantRole, Domain, FunctionSymbol, Hypernode, Property, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
    TemporalMode,
    TransitionOperator,
)
from ah.temporal import (
    TemporalAnchorContext,
    TemporalKind,
    TemporalNormalizer,
    TemporalPrecision,
    TemporalReasoner,
    TemporalRelation,
    TemporalTruth,
    StateTracker,
    StateTruth,
    TemporalValue,
    ensure_time_entity,
    temporal_value_from_ref,
)


def services():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.02))
    return core, context, integration


def assertion(local_id: str, predicate: str, *actants: ActantCandidate, **kwargs) -> AssertionCandidate:
    roles = tuple(dict.fromkeys(item.role for item in actants))
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate(roles),
        ),
        tuple(actants),
        **kwargs,
    )


def test_temporal_normalizer_preserves_partial_time_without_invented_fields():
    normalizer = TemporalNormalizer()

    month = normalizer.normalize("сентябрь")
    assert month is not None and month.resolved
    assert month.value is not None
    assert month.value.start == "--09"
    assert month.value.precision is TemporalPrecision.MONTH

    clock = normalizer.normalize("12:30")
    assert clock is not None and clock.resolved
    assert clock.value is not None
    assert clock.value.start == "T12:30"
    assert clock.value.precision is TemporalPrecision.MINUTE

    full = normalizer.normalize("5 сентября 2026")
    assert full is not None and full.value is not None
    assert full.value.start == "2026-09-05"
    assert full.value.precision is TemporalPrecision.DAY


def test_relative_time_without_anchor_stays_runtime_unresolved_and_cannot_commit():
    core, context, integration = services()
    result = PerceptionResult(
        "Сервер работал вчера.",
        assertions=(
            assertion(
                "A1",
                "работать",
                ActantCandidate(ActantRole.SUBJECT, mention="сервер"),
                ActantCandidate(ActantRole.TIME, mention="вчера"),
                temporal_mode=TemporalMode.STATE,
            ),
        ),
    )
    before = set(core.store.all_uids())
    plan = integration.prepare_external_plan(result, context)
    assert len(plan.candidate_ir.temporal_refs) == 1
    assert plan.candidate_ir.temporal_refs[0].mention == "вчера"
    with pytest.raises(UnresolvedTemporalReferenceError):
        integration.integrate_plan(plan, context)
    assert set(core.store.all_uids()) == before


def test_document_or_message_source_timestamp_resolves_relative_time_but_is_not_auto_time_for_other_facts():
    core, context, integration = services()
    source_timestamp = datetime(2026, 9, 5, 14, 30, tzinfo=timezone.utc)
    result = PerceptionResult(
        "Сервер работал вчера. Датчик исправен.",
        assertions=(
            assertion(
                "A1",
                "работать",
                ActantCandidate(ActantRole.SUBJECT, mention="сервер"),
                ActantCandidate(ActantRole.TIME, mention="вчера"),
                temporal_mode=TemporalMode.STATE,
            ),
            assertion(
                "A2",
                "быть исправным",
                ActantCandidate(ActantRole.SUBJECT, mention="датчик"),
            ),
        ),
    )
    plan = integration.prepare_external_plan(result, context, source_timestamp=source_timestamp)
    assert plan.candidate_ir.temporal_refs == ()
    commit = integration.integrate_plan(plan, context)

    first = core.store.get_hypernode(commit.assertions[0].ref.uid)
    time_ref = first.actants[ActantRole.TIME]
    assert time_ref.kind is RefKind.M
    temporal = temporal_value_from_ref(core, time_ref)
    assert temporal is not None
    assert temporal.kind is TemporalKind.POINT
    assert temporal.start == "2026-09-04"
    assert first.meta["temporal_mode"] == TemporalMode.STATE.value

    second = core.store.get_hypernode(commit.assertions[1].ref.uid)
    assert ActantRole.TIME not in second.actants
    # Technical ingestion time is not copied into every semantic proposition.
    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert ActantRole.TIME not in event.actants


def test_temporal_reasoner_derives_registered_relations_as_ordinary_n_with_support():
    core = AHCore(uid_generator=SequentialUidGenerator())
    left, _ = ensure_time_entity(
        core,
        TemporalValue(TemporalKind.INTERVAL, "2026-09-01", "2026-09-03", TemporalPrecision.DAY),
    )
    right, _ = ensure_time_entity(
        core,
        TemporalValue(TemporalKind.POINT, "2026-09-05", None, TemporalPrecision.DAY),
    )
    reasoner = TemporalReasoner(core)
    result = reasoner.compare(left, right)
    assert result.status is TemporalTruth.PROVED
    assert result.relation is TemporalRelation.BEFORE

    materialized = reasoner.materialize(left, right)
    assert materialized.ref is not None and materialized.ref.kind is RefKind.N
    node = core.store.get_hypernode(materialized.ref.uid)
    template = core.store.get_template(node.template.uid)
    symbol = core.store.get_symbol(template.predicate.uid)
    assert "BEFORE" in symbol.forms
    assert core.store.find_link("BEFORE", left.uid, right.uid) is None
    supports = core.supports.get(materialized.ref.uid)
    assert len(supports) == 1
    assert supports[0].rule_id == "TEMPORAL_INTERVAL_COMPARISON"


def test_unorderable_partial_temporal_values_return_unknown_not_false():
    core = AHCore(uid_generator=SequentialUidGenerator())
    month, _ = ensure_time_entity(
        core,
        TemporalValue(TemporalKind.POINT, "--09", None, TemporalPrecision.MONTH),
    )
    clock, _ = ensure_time_entity(
        core,
        TemporalValue(TemporalKind.POINT, "T12:30", None, TemporalPrecision.MINUTE),
    )
    result = TemporalReasoner(core).compare(month, clock)
    assert result.status is TemporalTruth.UNKNOWN
    assert result.relation is None


def test_start_then_stop_builds_state_intervals_and_transition_wrappers():
    core, context, integration = services()

    start_result = PerceptionResult(
        "Сервер начал работать 1 сентября 2026.",
        assertions=(
            assertion(
                "A1",
                "работать",
                ActantCandidate(ActantRole.SUBJECT, mention="сервер"),
                ActantCandidate(ActantRole.TIME, mention="1 сентября 2026"),
                temporal_mode=TemporalMode.TRANSITION,
                transition_operator=TransitionOperator.START,
            ),
        ),
    )
    start = integration.integrate_external(start_result, context)
    start_ref = start.assertions[0].ref
    assert start_ref.kind is RefKind.G
    start_g = core.store.get_element_any_domain(start_ref.uid)
    assert isinstance(start_g, FunctionSymbol) and start_g.function_id == "START"

    open_states = [
        node for node in core.store.all_elements()
        if isinstance(node, Hypernode)
        and node.meta.get("temporal_mode") == TemporalMode.STATE.value
        and node.meta.get("semantic_scope") is None
    ]
    assert len(open_states) == 1
    open_time = temporal_value_from_ref(core, open_states[0].actants[ActantRole.TIME])
    assert open_time is not None
    assert open_time.kind is TemporalKind.INTERVAL
    assert open_time.start == "2026-09-01"
    assert open_time.end is None

    stop_result = PerceptionResult(
        "Сервер перестал работать 5 сентября 2026.",
        assertions=(
            assertion(
                "A1",
                "работать",
                ActantCandidate(ActantRole.SUBJECT, mention="сервер"),
                ActantCandidate(ActantRole.TIME, mention="5 сентября 2026"),
                temporal_mode=TemporalMode.TRANSITION,
                transition_operator=TransitionOperator.STOP,
            ),
        ),
    )
    stop = integration.integrate_external(stop_result, context)
    stop_ref = stop.assertions[0].ref
    stop_g = core.store.get_element_any_domain(stop_ref.uid)
    assert isinstance(stop_g, FunctionSymbol) and stop_g.function_id == "STOP"

    positive_states = [
        node for node in core.store.all_elements()
        if isinstance(node, Hypernode)
        and node.meta.get("temporal_mode") == TemporalMode.STATE.value
        and node.meta.get("semantic_scope") is None
    ]
    assert len(positive_states) == 1
    closed = temporal_value_from_ref(core, positive_states[0].actants[ActantRole.TIME])
    assert closed is not None
    assert closed.start == "2026-09-01"
    assert closed.end == "2026-09-05"

    negative_operands = [
        node for node in core.store.all_elements()
        if isinstance(node, Hypernode)
        and node.meta.get("semantic_scope") == "NEGATED_STATE"
    ]
    assert len(negative_operands) == 1
    negative_time = temporal_value_from_ref(core, negative_operands[0].actants[ActantRole.TIME])
    assert negative_time is not None and negative_time.start == "2026-09-05" and negative_time.end is None
    assert any(
        isinstance(element, FunctionSymbol)
        and element.function_id == "NOT"
        and element.operands == (core.ref(negative_operands[0].uid),)
        for element in core.store.all_elements()
    )


def test_stop_without_prior_open_state_fails_atomically():
    core, context, integration = services()
    result = PerceptionResult(
        "Сервер перестал работать 5 сентября 2026.",
        assertions=(
            assertion(
                "A1",
                "работать",
                ActantCandidate(ActantRole.SUBJECT, mention="сервер"),
                ActantCandidate(ActantRole.TIME, mention="5 сентября 2026"),
                temporal_mode=TemporalMode.TRANSITION,
                transition_operator=TransitionOperator.STOP,
            ),
        ),
    )
    before = set(core.store.all_uids())
    with pytest.raises(ValueError, match="STOP requires"):
        integration.integrate_external(result, context)
    assert set(core.store.all_uids()) == before


def _transition(core, context, integration, operator: TransitionOperator, when: str):
    verb = {
        TransitionOperator.START: "начал работать",
        TransitionOperator.STOP: "перестал работать",
        TransitionOperator.CONTINUE: "продолжил работать",
        TransitionOperator.AGAIN: "снова начал работать",
        TransitionOperator.NO_LONGER: "больше не работает",
    }[operator]
    return integration.integrate_external(
        PerceptionResult(
            f"Сервер {verb} {when}.",
            assertions=(
                assertion(
                    "A1",
                    "работать",
                    ActantCandidate(ActantRole.SUBJECT, mention="сервер"),
                    ActantCandidate(ActantRole.TIME, mention=when),
                    temporal_mode=TemporalMode.TRANSITION,
                    transition_operator=operator,
                ),
            ),
        ),
        context,
    )


def test_state_truth_is_computed_from_interval_coverage_not_latest_mention():
    core, context, integration = services()
    started = _transition(core, context, integration, TransitionOperator.START, "1 сентября 2026")
    start_g = core.store.get_element_any_domain(started.assertions[0].ref.uid)
    assert isinstance(start_g, FunctionSymbol)
    prototype = start_g.operands[0]

    _transition(core, context, integration, TransitionOperator.STOP, "5 сентября 2026")

    september_3, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-09-03", None, TemporalPrecision.DAY)
    )
    september_6, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-09-06", None, TemporalPrecision.DAY)
    )
    august_31, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-08-31", None, TemporalPrecision.DAY)
    )

    tracker = StateTracker(core)
    assert tracker.current_truth(prototype, september_3) is StateTruth.POSITIVE
    assert tracker.current_truth(prototype, september_6) is StateTruth.NEGATIVE
    assert tracker.current_truth(prototype, august_31) is StateTruth.UNKNOWN


def test_temporal_state_and_supports_roundtrip_through_canonical_persistence(tmp_path):
    core, context, integration = services()
    started = _transition(core, context, integration, TransitionOperator.START, "1 сентября 2026")
    stopped = _transition(core, context, integration, TransitionOperator.STOP, "5 сентября 2026")

    start_g = core.store.get_element_any_domain(started.assertions[0].ref.uid)
    stop_g = core.store.get_element_any_domain(stopped.assertions[0].ref.uid)
    assert isinstance(start_g, FunctionSymbol) and start_g.function_id == "START"
    assert isinstance(stop_g, FunctionSymbol) and stop_g.function_id == "STOP"
    prototype = start_g.operands[0]

    negative_nodes = [
        node for node in core.store.all_elements()
        if isinstance(node, Hypernode) and node.meta.get("semantic_scope") == "NEGATED_STATE"
    ]
    assert len(negative_nodes) == 1
    not_functions = [
        element for element in core.store.all_elements()
        if isinstance(element, FunctionSymbol)
        and element.function_id == "NOT"
        and element.operands == (core.ref(negative_nodes[0].uid),)
    ]
    assert len(not_functions) == 1
    negative_ref = core.ref(not_functions[0].uid)
    before_supports = core.resolve_supports(negative_ref)
    assert before_supports and before_supports[0].rule_id == "STATE_STOP"

    path = tmp_path / "ah_temporal.json"
    persistence = JsonPersistence(
        path, PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False)
    )
    persistence.save(core)
    loaded = persistence.load().core

    loaded_start = loaded.store.get_element_any_domain(start_g.uid)
    loaded_stop = loaded.store.get_element_any_domain(stop_g.uid)
    assert isinstance(loaded_start, FunctionSymbol) and loaded_start.function_id == "START"
    assert isinstance(loaded_stop, FunctionSymbol) and loaded_stop.function_id == "STOP"
    assert loaded.resolve_supports(loaded.ref(negative_ref.uid)) == before_supports

    september_6, _ = ensure_time_entity(
        loaded, TemporalValue(TemporalKind.POINT, "2026-09-06", None, TemporalPrecision.DAY)
    )
    assert StateTracker(loaded).current_truth(loaded.ref(prototype.uid), september_6) is StateTruth.NEGATIVE


def test_continue_uses_only_open_positive_state_not_open_negation():
    core, context, integration = services()
    _transition(core, context, integration, TransitionOperator.START, "1 сентября 2026")
    continued = _transition(core, context, integration, TransitionOperator.CONTINUE, "3 сентября 2026")
    continue_g = core.store.get_element_any_domain(continued.assertions[0].ref.uid)
    assert isinstance(continue_g, FunctionSymbol) and continue_g.function_id == "CONTINUE"

    # Once P has stopped, an open NOT(P) interval must not satisfy CONTINUE(P).
    _transition(core, context, integration, TransitionOperator.STOP, "5 сентября 2026")
    before = set(core.store.all_uids())
    with pytest.raises(ValueError, match="CONTINUE requires"):
        _transition(core, context, integration, TransitionOperator.CONTINUE, "6 сентября 2026")
    assert set(core.store.all_uids()) == before


def test_again_closes_existing_negative_interval_and_reopens_positive_state():
    core, context, integration = services()
    started = _transition(core, context, integration, TransitionOperator.START, "1 сентября 2026")
    start_g = core.store.get_element_any_domain(started.assertions[0].ref.uid)
    assert isinstance(start_g, FunctionSymbol)
    prototype = start_g.operands[0]
    _transition(core, context, integration, TransitionOperator.STOP, "5 сентября 2026")
    again = _transition(core, context, integration, TransitionOperator.AGAIN, "7 сентября 2026")
    again_g = core.store.get_element_any_domain(again.assertions[0].ref.uid)
    assert isinstance(again_g, FunctionSymbol) and again_g.function_id == "AGAIN"

    negative_nodes = [
        node for node in core.store.all_elements()
        if isinstance(node, Hypernode)
        and node.meta.get("semantic_scope") == "NEGATED_STATE"
        and node.meta.get("temporal_mode") == TemporalMode.STATE.value
    ]
    assert len(negative_nodes) == 1
    negative_interval = temporal_value_from_ref(core, negative_nodes[0].actants[ActantRole.TIME])
    assert negative_interval is not None
    assert negative_interval.start == "2026-09-05"
    assert negative_interval.end == "2026-09-07"

    day_6, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-09-06", None, TemporalPrecision.DAY)
    )
    day_8, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-09-08", None, TemporalPrecision.DAY)
    )
    tracker = StateTracker(core)
    assert tracker.current_truth(prototype, day_6) is StateTruth.NEGATIVE
    assert tracker.current_truth(prototype, day_8) is StateTruth.POSITIVE


def test_transition_cannot_close_state_before_its_start_and_rolls_back():
    core, context, integration = services()
    _transition(core, context, integration, TransitionOperator.START, "5 сентября 2026")
    before_uids = set(core.store.all_uids())
    with pytest.raises(ValueError, match="before it starts"):
        _transition(core, context, integration, TransitionOperator.STOP, "1 сентября 2026")
    assert set(core.store.all_uids()) == before_uids
    # Atomic transaction rollback also restores the previously open interval.
    open_states = [
        node for node in core.store.all_elements()
        if isinstance(node, Hypernode)
        and node.meta.get("temporal_mode") == TemporalMode.STATE.value
        and node.meta.get("semantic_scope") is None
    ]
    assert len(open_states) == 1
    interval = temporal_value_from_ref(core, open_states[0].actants[ActantRole.TIME])
    assert interval is not None and interval.start == "2026-09-05" and interval.end is None


def test_relative_time_anchor_priority_is_explicit_then_source_then_experience():
    normalizer = TemporalNormalizer()
    explicit = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    source = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
    experience = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

    with_explicit = normalizer.normalize(
        "вчера", TemporalAnchorContext(explicit, source, experience)
    )
    assert with_explicit is not None and with_explicit.value is not None
    assert with_explicit.value.start == "2026-09-09"

    with_source = normalizer.normalize(
        "вчера", TemporalAnchorContext(None, source, experience)
    )
    assert with_source is not None and with_source.value is not None
    assert with_source.value.start == "2026-09-04"

    with_experience = normalizer.normalize(
        "вчера", TemporalAnchorContext(None, None, experience)
    )
    assert with_experience is not None and with_experience.value is not None
    assert with_experience.value.start == "2026-08-31"


def test_state_interval_end_is_exclusive_at_exact_transition_instant():
    core, context, integration = services()
    started = _transition(
        core, context, integration, TransitionOperator.START, "2026-09-01T10:00"
    )
    start_g = core.store.get_element_any_domain(started.assertions[0].ref.uid)
    assert isinstance(start_g, FunctionSymbol)
    prototype = start_g.operands[0]
    _transition(core, context, integration, TransitionOperator.STOP, "2026-09-05T15:00")

    before, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-09-05T14:59", None, TemporalPrecision.MINUTE)
    )
    boundary, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-09-05T15:00", None, TemporalPrecision.MINUTE)
    )
    after, _ = ensure_time_entity(
        core, TemporalValue(TemporalKind.POINT, "2026-09-05T15:01", None, TemporalPrecision.MINUTE)
    )
    tracker = StateTracker(core)
    assert tracker.current_truth(prototype, before) is StateTruth.POSITIVE
    assert tracker.current_truth(prototype, boundary) is StateTruth.NEGATIVE
    assert tracker.current_truth(prototype, after) is StateTruth.NEGATIVE
