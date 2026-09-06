from __future__ import annotations

from ah.config import IgnitionSettings, InferenceSettings, LifecycleSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import (
    CognitiveEventKind,
    FormulaGoal,
    GoalMode,
    GoalSpec,
    IgnitionInferenceAttention,
    InferenceEngine,
    InferenceQuery,
    LogicalStatus,
    RelationGoal,
    RoleFillGoal,
    StopReason,
)
from ah.model import ActantRole, Domain, Property, Ref


def _core_engine_attention():
    core = AHCore(uid_generator=SequentialUidGenerator())
    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    ignition = IgnitionEngine(
        core,
        IgnitionSettings(),
        WorkspaceSettings(threshold=0.35),
        LifecycleSettings(gc_enabled=False, orphan_cleanup=False),
    )
    return core, engine, ignition, IgnitionInferenceAttention(ignition)


def _entity(core: AHCore, name: str) -> Ref:
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _zero_fact(core: AHCore, label: str) -> Ref:
    symbol = core.ensure_abstract_symbol(label)
    template = core.add_template(Domain.C, core.ref(symbol.uid), ())
    node, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {},
        0.4,
        deduplicate=False,
        count_occurrence=False,
    )
    return core.ref(node.uid)


def _assert_formula_occurrence(core: AHCore, formula_ref: Ref) -> None:
    speaker = _entity(core, "Пользователь")
    predicate = core.ensure_abstract_symbol("утверждать")
    templates = core.store.find_templates_by_predicate(predicate.uid)
    template = templates[0] if templates else core.add_template(
        Domain.H,
        core.ref(predicate.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    core.add_hypernode(
        Domain.H,
        core.ref(template.uid),
        {ActantRole.SUBJECT: speaker, ActantRole.OBJECT: formula_ref},
        0.3,
        meta={"event_instance": True},
        deduplicate=False,
    )


def _unary_atom(core: AHCore, predicate: str, subject: Ref, *, asserted: bool) -> Ref:
    symbol = core.ensure_abstract_symbol(predicate)
    templates = core.store.find_templates_by_predicate(symbol.uid)
    template = templates[0] if templates else core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT,)
    )
    node, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: subject},
        0.4,
        count_occurrence=asserted,
    )
    return core.ref(node.uid)


def test_role_fill_runs_goal_seed_query_fact_focus_and_rule_through_one_runtime_trace() -> None:
    core, engine, ignition, attention = _core_engine_attention()
    person = _entity(core, "Иван")
    book = _entity(core, "Книга")
    pred = core.ensure_abstract_symbol("читать")
    template = core.add_template(
        Domain.C,
        core.ref(pred.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    fact, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: person, ActantRole.OBJECT: book},
        0.4,
    )

    outcome = engine.solve(
        InferenceQuery(
            GoalSpec(
                RoleFillGoal(core.ref(template.uid), {ActantRole.SUBJECT: person}, ActantRole.OBJECT),
                mode=GoalMode.FACTUAL,
            )
        ),
        ignition.workspace_refs(),
        attention=attention,
    )

    assert outcome.status is LogicalStatus.PROVED
    kinds = tuple(event.kind for event in outcome.cognitive_trace)
    assert kinds[0] is CognitiveEventKind.GOAL_START
    assert kinds[-1] is CognitiveEventKind.GOAL_STOP
    assert any(
        event.kind is CognitiveEventKind.MEMORY_QUERY
        and event.query_kind == "TEMPLATE_FACTS"
        and event.query_key is not None
        and template.uid in event.query_key
        for event in outcome.cognitive_trace
    )
    assert any(
        event.kind is CognitiveEventKind.RULE_SELECTED and event.rule_id == "FACT_MATCH"
        for event in outcome.cognitive_trace
    )
    assert [event.ref.uid for event in attention.events] == [template.uid, fact.uid]
    assert core.store.runtime_state(template.uid).excitation > 0.0
    assert core.store.runtime_state(fact.uid).excitation > 0.0


def test_relation_goal_stops_immediately_at_target_and_never_expands_tail() -> None:
    core, engine, ignition, attention = _core_engine_attention()
    nodes = [_entity(core, f"node_{i}") for i in range(4)]
    for a, b in zip(nodes, nodes[1:]):
        core.add_link("IS-A", a, b, 0.4)

    outcome = engine.solve(
        InferenceQuery(GoalSpec(RelationGoal("IS-A", nodes[0], nodes[2]))),
        ignition.workspace_refs(),
        attention=attention,
    )
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.stop_reason is StopReason.GOAL_SATISFIED
    assert [event.ref.uid for event in attention.events] == [nodes[0].uid, nodes[1].uid, nodes[2].uid]

    outgoing_keys = tuple(
        event.query_key
        for event in outcome.cognitive_trace
        if event.kind is CognitiveEventKind.MEMORY_QUERY
        and event.query_kind == "OUTGOING_RELATION"
    )
    assert any(nodes[0].uid in key for key in outgoing_keys if key)
    assert any(nodes[1].uid in key for key in outgoing_keys if key)
    assert all(nodes[2].uid not in key for key in outgoing_keys if key)
    assert core.store.runtime_state(nodes[3].uid).excitation == 0.0


def test_reasoner_does_not_need_full_store_iteration_for_transitive_relation_proof() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    engine = InferenceEngine(core, InferenceSettings(max_depth=6, max_expanded_states=32))
    nodes = [_entity(core, f"main_{i}") for i in range(4)]
    for a, b in zip(nodes, nodes[1:]):
        core.add_link("FOLLOW", a, b, 0.4)
    for i in range(200):
        a = _entity(core, f"noise_a_{i}")
        b = _entity(core, f"noise_b_{i}")
        core.add_link("IS-A", a, b, 0.2)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unrestricted global store iteration used by reasoner")

    # These broad enumerators are valid for diagnostics/GC but not for a GoalSpec proof.
    core.store.all_elements = forbidden  # type: ignore[method-assign]
    core.store.all_uids = forbidden  # type: ignore[method-assign]
    core.store.elements = forbidden  # type: ignore[method-assign]
    core.store.links = forbidden  # type: ignore[method-assign]

    outcome = engine.solve(InferenceQuery(GoalSpec(RelationGoal("FOLLOW", nodes[0], nodes[3]))))
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.logical_depth == 3
    assert any(
        event.kind is CognitiveEventKind.MEMORY_QUERY
        and event.query_kind == "REVERSE_DISTANCE_HEURISTIC"
        for event in outcome.cognitive_trace
    )


def test_formula_implication_exposes_backward_subgoal_then_forward_rule_validation() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    subject = _entity(core, "сервер")
    premise = _unary_atom(core, "включён", subject, asserted=True)
    target = _unary_atom(core, "работает", subject, asserted=False)
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (premise, target))
    _assert_formula_occurrence(core, core.ref(rule.uid))

    outcome = engine.solve(InferenceQuery(GoalSpec(FormulaGoal(target))))
    assert outcome.status is LogicalStatus.PROVED
    assert any(
        event.kind is CognitiveEventKind.MEMORY_QUERY
        and event.query_kind == "FUNCTION_PARENTS"
        and event.query_key is not None
        and "IMPLIES" in event.query_key
        for event in outcome.cognitive_trace
    )
    assert any(
        event.kind is CognitiveEventKind.SUBGOAL and event.ref == premise
        for event in outcome.cognitive_trace
    )
    assert any(
        event.kind is CognitiveEventKind.RULE_SELECTED and event.rule_id == "IMPLIES_MP"
        for event in outcome.cognitive_trace
    )
    assert outcome.cognitive_trace[-1].kind is CognitiveEventKind.GOAL_STOP
