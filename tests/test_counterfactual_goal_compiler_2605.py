from __future__ import annotations

from ah.agent import InteractionContext
from ah.config import InferenceSettings, IntegrationSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    CounterfactualContext,
    CounterfactualGoal,
    FormulaGoal,
    InferenceEngine,
    LogicalStatus,
    SemanticGoalCompiler,
    StopReason,
)
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, Domain, FunctionSymbol, Property, Ref
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActRelationCandidate,
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
    apply_speech_act_scoping,
)


def _runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P,
        {"name": Property("name", "Агент", "str")},
        uid="M_SELF",
    )
    user_entity = core.add_entity(
        Domain.P,
        {"name": Property("name", "Пользователь", "str")},
        uid="M_USER",
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid),
        user_ref=core.ref(user_entity.uid),
    )
    service = IntegrationService(
        core,
        IntegrationConfig.from_settings(IntegrationSettings()),
    )
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _entity(core: AHCore, name: str) -> Ref:
    existing = core.store.find_entities_by_name(name, Domain.C)
    if existing:
        return core.ref(existing[0].uid)
    item = core.add_entity(
        Domain.C,
        {"name": Property("name", name, "str")},
    )
    return core.ref(item.uid)


def _template(core: AHCore, predicate: str) -> Ref:
    symbol = core.ensure_abstract_symbol(predicate)
    templates = core.store.find_templates_by_predicate(symbol.uid)
    if templates:
        return core.ref(templates[0].uid)
    template = core.add_template(
        Domain.C,
        core.ref(symbol.uid),
        (ActantRole.SUBJECT,),
    )
    return core.ref(template.uid)


def _atom(
    core: AHCore,
    predicate: str,
    subject: str,
    *,
    asserted: bool = False,
) -> Ref:
    template = _template(core, predicate)
    node, _ = core.add_hypernode(
        Domain.C,
        template,
        {ActantRole.SUBJECT: _entity(core, subject)},
        0.4,
        count_occurrence=asserted,
    )
    return core.ref(node.uid)


def _assert_formula(
    core: AHCore,
    context: InteractionContext,
    ref: Ref,
    text: str = "rule",
) -> None:
    recorded = ExperienceMapper(
        core,
        event_weight=0.3,
        follow_weight=0.2,
    ).record_turn(
        source_text=text,
        speaker_ref=context.user_ref,
        semantic_refs=(ref,),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )
    context.last_experience_ref = recorded.event_ref


def _rule(
    core: AHCore,
    context: InteractionContext,
    antecedent: Ref,
    consequent: Ref,
) -> Ref:
    function, _ = core.ensure_function(
        Domain.C,
        "IMPLIES",
        (antecedent, consequent),
    )
    ref = core.ref(function.uid)
    _assert_formula(core, context, ref)
    return ref


def _and_rule(
    core: AHCore,
    context: InteractionContext,
    antecedents: tuple[Ref, ...],
    consequent: Ref,
) -> Ref:
    conjunction, _ = core.ensure_function(
        Domain.C,
        "AND",
        antecedents,
    )
    return _rule(core, context, core.ref(conjunction.uid), consequent)


def _assertion(
    local_id: str,
    predicate: str,
    subject: str,
    *,
    status: AssertionStatus,
    negated: bool = False,
) -> AssertionCandidate:
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention=subject),),
        negated=negated,
        status=status,
    )


def _query(
    predicate: str,
    subject: str,
    *,
    local_id: str = "Q1",
    mode: QueryMode = QueryMode.EXISTS,
) -> QueryCandidate:
    requested = () if mode is QueryMode.EXISTS else (ActantRole.SUBJECT,)
    actants = (
        (ActantCandidate(ActantRole.SUBJECT, mention=subject),)
        if mode is QueryMode.EXISTS
        else ()
    )
    return QueryCandidate(
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        actants,
        requested_roles=requested,
        query_mode=mode,
        local_id=local_id,
    )


def _direct_counterfactual(
    assumption: AssertionCandidate,
    query: QueryCandidate,
    *,
    extra_assumptions: tuple[AssertionCandidate, ...] = (),
) -> PerceptionResult:
    assumptions = (assumption, *extra_assumptions)
    raw = PerceptionResult(
        source_text="counterfactual query",
        assertions=assumptions,
        queries=(query,),
        act_dependencies=tuple(
            ActDependencyCandidate(
                query.local_id,
                item.local_id,
                ActDependencyKind.SUBORDINATE,
            )
            for item in assumptions
        ),
    )
    return apply_speech_act_scoping(raw)


def _compile(
    core: AHCore,
    context: InteractionContext,
    service: IntegrationService,
    perception: PerceptionResult,
):
    commit = service.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(
        commit,
        context,
        perception,
    )
    assert len(built) == 1
    return commit, built[0]


def _counterfactual_target(built) -> CounterfactualGoal:
    assert built.goal is not None
    target = built.goal.goal.target
    assert isinstance(target, CounterfactualGoal)
    return target


def test_direct_polar_query_creates_scoped_shadow_and_compiles_counterfactual_goal() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    q = _atom(core, "отвечать", "сервис")
    _rule(core, context, p, q)

    perception = _direct_counterfactual(
        _assertion(
            "A1",
            "работать",
            "сервер",
            status=AssertionStatus.HYPOTHETICAL,
        ),
        _query("отвечать", "сервис"),
    )
    shadow = next(
        item for item in perception.assertions
        if item.local_id == "Q1:__CF_TARGET__"
    )
    assert shadow.status is AssertionStatus.EMBEDDED

    commit, built = _compile(core, context, service, perception)
    goal = _counterfactual_target(built)
    by_id = {item.local_id: item for item in commit.assertions}
    assert goal.assumptions == (by_id["A1"].ref,)
    assert goal.target.expression == by_id["Q1:__CF_TARGET__"].ref
    assert built.diagnostics == ("semantic:counterfactual_formula_goal",)

    assumption_node = core.store.get_hypernode(by_id["A1"].ref.uid)
    target_node = core.store.get_hypernode(goal.target.expression.uid)
    assert assumption_node.meta["semantic_scope"] == "HYPOTHETICAL"
    assert target_node.meta["semantic_scope"] == "EMBEDDED"
    assert assumption_node.meta["occurrence_count"] == 0
    assert target_node.meta["occurrence_count"] == 0

    before = set(core.store.all_uids())
    outcome = engine.solve(built.goal)
    after = set(core.store.all_uids())
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.proof_context, CounterfactualContext)
    assert before == after

    # The same target remains unproved in the ordinary world after the sandbox ends.
    ordinary = engine.solve(FormulaGoal(goal.target.expression))
    assert ordinary.status is LogicalStatus.UNKNOWN


def test_multiple_sibling_hypotheses_enter_one_overlay_simultaneously() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    r = _atom(core, "быть доступным", "сеть")
    q = _atom(core, "отвечать", "сервис")
    _and_rule(core, context, (p, r), q)

    perception = _direct_counterfactual(
        _assertion(
            "A1", "работать", "сервер",
            status=AssertionStatus.HYPOTHETICAL,
        ),
        _query("отвечать", "сервис"),
        extra_assumptions=(
            _assertion(
                "A2", "быть доступным", "сеть",
                status=AssertionStatus.HYPOTHETICAL,
            ),
        ),
    )
    commit, built = _compile(core, context, service, perception)
    goal = _counterfactual_target(built)
    by_id = {item.local_id: item for item in commit.assertions}
    assert goal.assumptions == (by_id["A1"].ref, by_id["A2"].ref)
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_missing_required_counterfactual_assumption_keeps_target_unknown() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    r = _atom(core, "быть доступным", "сеть")
    q = _atom(core, "отвечать", "сервис")
    _and_rule(core, context, (p, r), q)

    perception = _direct_counterfactual(
        _assertion(
            "A1", "работать", "сервер",
            status=AssertionStatus.HYPOTHETICAL,
        ),
        _query("отвечать", "сервис"),
    )
    _commit, built = _compile(core, context, service, perception)
    assert engine.solve(built.goal).status is LogicalStatus.UNKNOWN


def test_negative_assumption_locally_suppresses_positive_world_fact() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер", asserted=True)
    q = _atom(core, "включиться", "резерв")
    not_p, _ = core.ensure_function(Domain.C, "NOT", (p,))
    _rule(core, context, core.ref(not_p.uid), q)

    perception = _direct_counterfactual(
        _assertion(
            "A1",
            "работать",
            "сервер",
            status=AssertionStatus.HYPOTHETICAL,
            negated=True,
        ),
        _query("включиться", "резерв"),
    )
    _commit, built = _compile(core, context, service, perception)
    assert engine.solve(built.goal).status is LogicalStatus.PROVED
    assert engine.solve(FormulaGoal(p)).status is LogicalStatus.PROVED


def test_positive_assumption_locally_overrides_asserted_not() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    q = _atom(core, "отвечать", "сервис")
    not_p, _ = core.ensure_function(Domain.C, "NOT", (p,))
    _assert_formula(core, context, core.ref(not_p.uid), "server does not work")
    _rule(core, context, p, q)

    perception = _direct_counterfactual(
        _assertion(
            "A1", "работать", "сервер",
            status=AssertionStatus.HYPOTHETICAL,
        ),
        _query("отвечать", "сервис"),
    )
    _commit, built = _compile(core, context, service, perception)
    assert engine.solve(built.goal).status is LogicalStatus.PROVED
    assert engine.solve(FormulaGoal(p)).status is LogicalStatus.DISPROVED


def test_incompatible_simultaneous_assumptions_stop_as_conflicted() -> None:
    core, context, service, engine = _runtime()
    _atom(core, "работать", "сервер")
    _atom(core, "отвечать", "сервис")

    perception = _direct_counterfactual(
        _assertion(
            "A1", "работать", "сервер",
            status=AssertionStatus.HYPOTHETICAL,
        ),
        _query("отвечать", "сервис"),
        extra_assumptions=(
            _assertion(
                "A2", "работать", "сервер",
                status=AssertionStatus.HYPOTHETICAL,
                negated=True,
            ),
        ),
    )
    _commit, built = _compile(core, context, service, perception)
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.CONFLICTED


def test_explicit_embedded_target_wins_over_synthetic_shadow() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    q = _atom(core, "отвечать", "сервис")
    _rule(core, context, p, q)

    assumption = _assertion(
        "A1", "работать", "сервер",
        status=AssertionStatus.HYPOTHETICAL,
    )
    target = _assertion(
        "A2", "отвечать", "сервис",
        status=AssertionStatus.ASSERTED,
    )
    root = QueryCandidate(
        PredicateCandidate("спрашивать", "спрашивать", template_candidate=TemplateCandidate(())),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    raw = PerceptionResult(
        "counterfactual with explicit target",
        assertions=(assumption, target),
        queries=(root,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("Q1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    assert all(
        item.local_id != "Q1:__CF_TARGET__"
        for item in perception.assertions
    )
    assert next(item for item in perception.assertions if item.local_id == "A2").status is AssertionStatus.EMBEDDED

    commit, built = _compile(core, context, service, perception)
    goal = _counterfactual_target(built)
    by_id = {item.local_id: item for item in commit.assertions}
    assert goal.target.expression == by_id["A2"].ref
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_embedded_content_inside_hypothesis_is_not_mistaken_for_query_target() -> None:
    core, context, service, _engine = _runtime()
    _atom(core, "думать", "Анна")
    _atom(core, "работать", "сервер")
    _atom(core, "отвечать", "сервис")

    outer = _assertion(
        "A1", "думать", "Анна",
        status=AssertionStatus.HYPOTHETICAL,
    )
    nested = _assertion(
        "A1C", "работать", "сервер",
        status=AssertionStatus.ASSERTED,
    )
    query = _query("отвечать", "сервис")
    raw = PerceptionResult(
        "nested hypothetical content",
        assertions=(outer, nested),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("A1", "A1C", ActDependencyKind.SUBORDINATE),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    assert next(item for item in perception.assertions if item.local_id == "A1C").status is AssertionStatus.EMBEDDED
    assert any(item.local_id == "Q1:__CF_TARGET__" for item in perception.assertions)

    commit, built = _compile(core, context, service, perception)
    goal = _counterfactual_target(built)
    by_id = {item.local_id: item for item in commit.assertions}
    assert goal.assumptions == (by_id["A1"].ref,)
    assert goal.target.expression == by_id["Q1:__CF_TARGET__"].ref


def test_scoping_is_idempotent_before_and_after_document_namespace_shape() -> None:
    assumption = _assertion(
        "A1", "работать", "сервер",
        status=AssertionStatus.HYPOTHETICAL,
    )
    query = _query("отвечать", "сервис")
    once = _direct_counterfactual(assumption, query)
    twice = apply_speech_act_scoping(once)
    assert twice == once

    # Reproduce the namespace shape used by merge_formalization_units. The suffix
    # must still be derived from the namespaced query id without creating a second
    # shadow on a later consolidation pass.
    namespaced = PerceptionResult(
        once.source_text,
        assertions=tuple(
            AssertionCandidate(
                f"B0:{item.local_id}",
                item.predicate,
                item.actants,
                evidence=item.evidence,
                negated=item.negated,
                alternatives=item.alternatives,
                status=item.status,
                quoted=item.quoted,
                transition_operator=item.transition_operator,
            )
            for item in once.assertions
        ),
        queries=(
            QueryCandidate(
                once.queries[0].predicate,
                once.queries[0].actants,
                query_mode=once.queries[0].query_mode,
                local_id="B0:Q1",
            ),
        ),
        act_dependencies=tuple(
            ActDependencyCandidate(
                f"B0:{edge.parent_ref}",
                f"B0:{edge.child_ref}",
                edge.kind,
            )
            for edge in once.act_dependencies
        ),
    )
    rescoped = apply_speech_act_scoping(namespaced)
    ids = [item.local_id for item in rescoped.assertions]
    assert ids.count("B0:Q1:__CF_TARGET__") == 1


def test_open_ended_fill_role_counterfactual_fails_closed() -> None:
    core, context, service, _engine = _runtime()
    assumption = _assertion(
        "A1", "работать", "сервер",
        status=AssertionStatus.HYPOTHETICAL,
    )
    query = _query(
        "произойти",
        "",
        mode=QueryMode.FILL_ROLE,
    )
    raw = PerceptionResult(
        "what would happen",
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    assert all(item.local_id != "Q1:__CF_TARGET__" for item in perception.assertions)
    _commit, built = _compile(core, context, service, perception)
    assert built.goal is None
    assert built.diagnostics == ("semantic:counterfactual_formula_target_required",)


def test_structural_relation_counterfactual_target_fails_closed() -> None:
    core, context, service, _engine = _runtime()
    _entity(core, "Крипл")
    _entity(core, "ИИ")
    assumption = _assertion(
        "A1", "работать", "сервер",
        status=AssertionStatus.HYPOTHETICAL,
    )
    query = QueryCandidate(
        PredicateCandidate(
            "быть",
            "быть",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Крипл"),
            ActantCandidate(ActantRole.STATE, mention="ИИ"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    raw = PerceptionResult(
        "counterfactual relation query",
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
        ),
        act_relations=(
            ActRelationCandidate("IS-A", "Q1", ActantRole.SUBJECT, ActantRole.STATE),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    assert all(item.local_id != "Q1:__CF_TARGET__" for item in perception.assertions)
    _commit, built = _compile(core, context, service, perception)
    assert built.goal is None
    assert built.diagnostics == ("semantic:counterfactual_relation_target_not_supported",)


def test_quoted_hypothetical_edge_does_not_create_counterfactual_scope() -> None:
    core, context, service, _engine = _runtime()
    _atom(core, "отвечать", "сервис", asserted=True)
    assumption = _assertion(
        "A1", "работать", "сервер",
        status=AssertionStatus.HYPOTHETICAL,
    )
    query = _query("отвечать", "сервис")
    raw = PerceptionResult(
        "quoted hypothesis",
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.QUOTED),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    assert all(item.local_id != "Q1:__CF_TARGET__" for item in perception.assertions)
    _commit, built = _compile(core, context, service, perception)
    assert built.goal is not None
    assert not isinstance(built.goal.goal.target, CounterfactualGoal)


def test_ordinary_noncounterfactual_goal_dispatch_is_unchanged() -> None:
    core, context, service, engine = _runtime()
    _atom(core, "отвечать", "сервис", asserted=True)
    perception = PerceptionResult(
        "service responds?",
        queries=(_query("отвечать", "сервис"),),
    )
    commit, built = _compile(core, context, service, perception)
    assert built.goal is not None
    assert not isinstance(built.goal.goal.target, CounterfactualGoal)
    assert engine.solve(built.goal).status is LogicalStatus.PROVED
