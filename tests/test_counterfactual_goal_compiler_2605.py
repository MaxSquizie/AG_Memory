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
from ah.model import ActantRole, Domain, Property, Ref
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
        Domain.P, {"name": Property("name", "Агент", "str")}, uid="M_SELF"
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")}, uid="M_USER"
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid)
    )
    service = IntegrationService(
        core, IntegrationConfig.from_settings(IntegrationSettings())
    )
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _entity(core: AHCore, name: str) -> Ref:
    found = core.store.find_entities_by_name(name, Domain.C)
    if found:
        return core.ref(found[0].uid)
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _template(core: AHCore, predicate: str) -> Ref:
    symbol = core.ensure_abstract_symbol(predicate)
    found = core.store.find_templates_by_predicate(symbol.uid)
    if found:
        return core.ref(found[0].uid)
    template = core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT,)
    )
    return core.ref(template.uid)


def _atom(
    core: AHCore,
    predicate: str,
    subject: str,
    *,
    asserted: bool = False,
) -> Ref:
    node, _ = core.add_hypernode(
        Domain.C,
        _template(core, predicate),
        {ActantRole.SUBJECT: _entity(core, subject)},
        0.4,
        count_occurrence=asserted,
    )
    return core.ref(node.uid)


def _assert_formula(
    core: AHCore, context: InteractionContext, ref: Ref, text: str = "rule"
) -> None:
    recorded = ExperienceMapper(
        core, event_weight=0.3, follow_weight=0.2
    ).record_turn(
        source_text=text,
        speaker_ref=context.user_ref,
        semantic_refs=(ref,),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )
    context.last_experience_ref = recorded.event_ref


def _rule(core: AHCore, context: InteractionContext, left: Ref, right: Ref) -> Ref:
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (left, right))
    ref = core.ref(rule.uid)
    _assert_formula(core, context, ref)
    return ref


def _assertion(
    local_id: str,
    predicate: str,
    subject: str,
    *,
    status: AssertionStatus,
    negated: bool = False,
    quoted: bool = False,
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
        quoted=quoted,
    )


def _query(
    predicate: str,
    subject: str,
    *,
    mode: QueryMode = QueryMode.EXISTS,
) -> QueryCandidate:
    if mode is QueryMode.EXISTS:
        actants = (ActantCandidate(ActantRole.SUBJECT, mention=subject),)
        requested = ()
    else:
        actants = ()
        requested = (ActantRole.SUBJECT,)
    return QueryCandidate(
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        actants,
        requested_roles=requested,
        query_mode=mode,
        local_id="Q1",
    )


def _direct(
    assumptions: tuple[AssertionCandidate, ...], query: QueryCandidate
) -> PerceptionResult:
    raw = PerceptionResult(
        "typed counterfactual",
        assertions=assumptions,
        queries=(query,),
        act_dependencies=tuple(
            ActDependencyCandidate(
                "Q1", item.local_id, ActDependencyKind.SUBORDINATE
            )
            for item in assumptions
        ),
    )
    return apply_speech_act_scoping(raw)


def _compile(core, context, service, perception):
    commit = service.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1
    return commit, built[0]


def _cf(built) -> CounterfactualGoal:
    assert built.goal is not None
    goal = built.goal.goal.target
    assert isinstance(goal, CounterfactualGoal)
    return goal


def test_direct_polar_counterfactual_compiles_and_solves_without_ah_mutation() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    q = _atom(core, "отвечать", "сервис")
    _rule(core, context, p, q)

    perception = _direct(
        (_assertion("A1", "работать", "сервер", status=AssertionStatus.HYPOTHETICAL),),
        _query("отвечать", "сервис"),
    )
    assert any(
        item.local_id == "Q1:__CF_TARGET__" and item.status is AssertionStatus.EMBEDDED
        for item in perception.assertions
    )

    commit, built = _compile(core, context, service, perception)
    goal = _cf(built)
    by_id = {item.local_id: item for item in commit.assertions}
    assert goal.assumptions == (by_id["A1"].ref,)
    assert goal.target.expression == by_id["Q1:__CF_TARGET__"].ref
    assert built.diagnostics == ("semantic:counterfactual_formula_goal",)

    for ref in (by_id["A1"].ref, goal.target.expression):
        if ref.kind.value == "N":
            assert core.store.get_hypernode(ref.uid).meta["occurrence_count"] == 0

    before = set(core.store.all_uids())
    outcome = engine.solve(built.goal)
    assert set(core.store.all_uids()) == before
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.proof_context, CounterfactualContext)
    assert engine.solve(FormulaGoal(goal.target.expression)).status is LogicalStatus.UNKNOWN


def test_sibling_hypotheses_are_one_simultaneous_assumption_set() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    r = _atom(core, "быть доступным", "сеть")
    q = _atom(core, "отвечать", "сервис")
    both, _ = core.ensure_function(Domain.C, "AND", (p, r))
    _rule(core, context, core.ref(both.uid), q)

    perception = _direct(
        (
            _assertion("A1", "работать", "сервер", status=AssertionStatus.HYPOTHETICAL),
            _assertion("A2", "быть доступным", "сеть", status=AssertionStatus.HYPOTHETICAL),
        ),
        _query("отвечать", "сервис"),
    )
    commit, built = _compile(core, context, service, perception)
    by_id = {item.local_id: item for item in commit.assertions}
    assert _cf(built).assumptions == (by_id["A1"].ref, by_id["A2"].ref)
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_opposite_sibling_hypotheses_stop_as_conflicted() -> None:
    core, context, service, engine = _runtime()
    _atom(core, "работать", "сервер")
    _atom(core, "отвечать", "сервис")
    perception = _direct(
        (
            _assertion("A1", "работать", "сервер", status=AssertionStatus.HYPOTHETICAL),
            _assertion(
                "A2", "работать", "сервер",
                status=AssertionStatus.HYPOTHETICAL, negated=True,
            ),
        ),
        _query("отвечать", "сервис"),
    )
    _commit, built = _compile(core, context, service, perception)
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.CONFLICTED


def test_explicit_embedded_target_wins_and_no_shadow_is_created() -> None:
    core, context, service, engine = _runtime()
    p = _atom(core, "работать", "сервер")
    q = _atom(core, "отвечать", "сервис")
    _rule(core, context, p, q)
    assumption = _assertion(
        "A1", "работать", "сервер", status=AssertionStatus.HYPOTHETICAL
    )
    target = _assertion(
        "A2", "отвечать", "сервис", status=AssertionStatus.ASSERTED
    )
    root = QueryCandidate(
        PredicateCandidate("спросить", "спросить", template_candidate=TemplateCandidate(())),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    raw = PerceptionResult(
        "typed explicit target",
        assertions=(assumption, target),
        queries=(root,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("Q1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    assert all(item.local_id != "Q1:__CF_TARGET__" for item in perception.assertions)
    assert next(item for item in perception.assertions if item.local_id == "A2").status is AssertionStatus.EMBEDDED

    commit, built = _compile(core, context, service, perception)
    by_id = {item.local_id: item for item in commit.assertions}
    assert _cf(built).target.expression == by_id["A2"].ref
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_nested_content_of_hypothesis_is_not_selected_as_target() -> None:
    core, context, service, _engine = _runtime()
    for predicate, subject in (
        ("думать", "Анна"), ("работать", "сервер"), ("отвечать", "сервис")
    ):
        _atom(core, predicate, subject)
    outer = _assertion("A1", "думать", "Анна", status=AssertionStatus.HYPOTHETICAL)
    nested = _assertion("A1C", "работать", "сервер", status=AssertionStatus.ASSERTED)
    query = _query("отвечать", "сервис")
    raw = PerceptionResult(
        "typed nested hypothesis",
        assertions=(outer, nested),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("A1", "A1C", ActDependencyKind.SUBORDINATE),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    commit, built = _compile(core, context, service, perception)
    by_id = {item.local_id: item for item in commit.assertions}
    goal = _cf(built)
    assert goal.assumptions == (by_id["A1"].ref,)
    assert goal.target.expression == by_id["Q1:__CF_TARGET__"].ref
    assert goal.target.expression != by_id["A1C"].ref


def test_fill_role_counterfactual_fails_closed_without_synthetic_target() -> None:
    core, context, service, _engine = _runtime()
    assumption = _assertion(
        "A1", "работать", "сервер", status=AssertionStatus.HYPOTHETICAL
    )
    query = _query("произойти", "", mode=QueryMode.FILL_ROLE)
    perception = _direct((assumption,), query)
    assert all(item.local_id != "Q1:__CF_TARGET__" for item in perception.assertions)
    _commit, built = _compile(core, context, service, perception)
    assert built.goal is None
    assert built.diagnostics == ("semantic:counterfactual_formula_target_required",)


def test_structural_relation_counterfactual_fails_closed() -> None:
    core, context, service, _engine = _runtime()
    _entity(core, "Крипл")
    _entity(core, "ИИ")
    assumption = _assertion(
        "A1", "работать", "сервер", status=AssertionStatus.HYPOTHETICAL
    )
    query = QueryCandidate(
        PredicateCandidate(
            "быть", "быть",
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
        "typed relation counterfactual",
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
    _commit, built = _compile(core, context, service, perception)
    assert built.goal is None
    assert built.diagnostics == ("semantic:counterfactual_relation_target_not_supported",)


def test_quoted_hypothesis_edge_does_not_open_counterfactual_scope() -> None:
    core, context, service, engine = _runtime()
    _atom(core, "отвечать", "сервис", asserted=True)
    assumption = _assertion(
        "A1", "работать", "сервер",
        status=AssertionStatus.HYPOTHETICAL, quoted=True,
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
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_ordinary_query_dispatch_remains_unchanged() -> None:
    core, context, service, engine = _runtime()
    _atom(core, "отвечать", "сервис", asserted=True)
    perception = PerceptionResult(
        "ordinary query", queries=(_query("отвечать", "сервис"),)
    )
    _commit, built = _compile(core, context, service, perception)
    assert built.goal is not None
    assert not isinstance(built.goal.goal.target, CounterfactualGoal)
    assert engine.solve(built.goal).status is LogicalStatus.PROVED
