from __future__ import annotations

from ah.agent import InteractionContext
from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    FormulaGoal,
    InferenceEngine,
    LogicalStatus,
    SemanticGoalCompiler,
)
from ah.integration import IntegrationConfig, IntegrationService, namespace_perception_result
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Property, Ref, VariableSort
from ah.perception import (
    ActantCandidate,
    PerceptionResult,
    PredicateCandidate,
    QuantifiedQueryBinding,
    QuantifiedQuerySpec,
    QueryCandidate,
    QueryMode,
    QueryQuantifierOperator,
    TemplateCandidate,
)


def _env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(
        Domain.P, {"name": Property("name", "user", "str")}
    )
    agent = core.add_entity(
        Domain.P, {"name": Property("name", "agent", "str")}
    )
    context = InteractionContext(
        user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid)
    )
    service = IntegrationService(
        core, IntegrationConfig(0.4, 0.3, 0.2)
    )
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _template(
    core: AHCore, name: str, roles: tuple[ActantRole, ...]
) -> Ref:
    symbol = core.ensure_abstract_symbol(name)
    template = core.add_template(
        Domain.C, core.ref(symbol.uid), roles
    )
    return core.ref(template.uid)


def _entity(core: AHCore, name: str) -> Ref:
    entity = core.add_entity(
        Domain.C, {"name": Property("name", name, "str")}
    )
    return core.ref(entity.uid)


def _ground(
    core: AHCore,
    template: Ref,
    actants: dict[ActantRole, Ref],
) -> Ref:
    node, _ = core.add_hypernode(
        Domain.C, template, actants, 0.5
    )
    return core.ref(node.uid)


def _pattern(
    core: AHCore,
    template: Ref,
    actants,
) -> Ref:
    node, _ = core.add_hypernode(
        Domain.C,
        template,
        actants,
        0.5,
        meta={"semantic_scope": "QUANTIFIED"},
        count_occurrence=False,
    )
    return core.ref(node.uid)


def _assert_formula(
    core: AHCore,
    context: InteractionContext,
    ref: Ref,
    text: str,
) -> None:
    result = ExperienceMapper(
        core, event_weight=0.3, follow_weight=0.2
    ).record_turn(
        source_text=text,
        speaker_ref=context.user_ref,
        semantic_refs=(ref,),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )
    context.last_experience_ref = result.event_ref


def _query(
    predicate: str,
    actants: tuple[ActantCandidate, ...],
    bindings: tuple[QuantifiedQueryBinding, ...],
    *,
    body_negated: bool = False,
    local_id: str = "Q1",
) -> QueryCandidate:
    return QueryCandidate(
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate(
                tuple(item.role for item in actants)
            ),
        ),
        actants,
        query_mode=QueryMode.EXISTS,
        local_id=local_id,
        quantified=QuantifiedQuerySpec(
            bindings, body_negated=body_negated
        ),
    )


def _bound(
    role: ActantRole,
    handle: str,
    mention: str,
) -> ActantCandidate:
    return ActantCandidate(
        role,
        mention=mention,
        normalized_hint=mention.casefold(),
        entity_ref=handle,
    )


def _binding(
    handle: str,
    variable_id: int,
    operator: QueryQuantifierOperator,
    *,
    restriction: str | None = None,
    negated: bool = False,
) -> QuantifiedQueryBinding:
    return QuantifiedQueryBinding(
        handle,
        variable_id,
        operator,
        restriction_lemma=restriction,
        negated=negated,
    )


def _compile(
    service: IntegrationService,
    core: AHCore,
    context: InteractionContext,
    query: QueryCandidate,
    text: str,
):
    perception = PerceptionResult(text, queries=(query,))
    commit = service.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(
        commit, context, perception
    )
    assert len(built) == 1
    return perception, commit, built[0]


def _function(core: AHCore, ref: Ref) -> FunctionSymbol:
    obj = core.store.get_element_any_domain(ref.uid)
    assert isinstance(obj, FunctionSymbol)
    return obj


def test_forall_query_compiles_to_formula_goal_and_reuses_asserted_formula() -> None:
    core, context, service, engine = _env()
    t_employee = _template(core, "employee", (ActantRole.SUBJECT,))
    t_arrive = _template(core, "arrive", (ActantRole.SUBJECT,))
    x = BoundVar(0, VariableSort.ENTITY)
    employee = _pattern(
        core, t_employee, {ActantRole.SUBJECT: x}
    )
    arrive = _pattern(
        core, t_arrive, {ActantRole.SUBJECT: x}
    )
    implication = core.add_function(
        Domain.C, "IMPLIES", (employee, arrive)
    )
    universal = core.add_function(
        Domain.C, "FORALL", (x, core.ref(implication.uid))
    )
    universal_ref = core.ref(universal.uid)
    _assert_formula(
        core, context, universal_ref, "Every employee arrived."
    )

    query = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "employees"),),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
        ),
    )
    _perception, commit, built = _compile(
        service, core, context, query, "Did every employee arrive?"
    )

    assert len(commit.quantified_queries) == 1
    assert commit.quantified_queries[0].ref == universal_ref
    assert built.goal is not None
    assert isinstance(built.goal.goal.target, FormulaGoal)
    assert built.goal.goal.target.expression == universal_ref
    assert built.diagnostics == ("semantic:quantified_formula_goal",)
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_forall_query_does_not_use_closed_world_enumeration() -> None:
    core, context, service, engine = _env()
    t_employee = _template(core, "employee", (ActantRole.SUBJECT,))
    t_arrive = _template(core, "arrive", (ActantRole.SUBJECT,))
    ivan = _entity(core, "Ivan")
    _ground(core, t_employee, {ActantRole.SUBJECT: ivan})
    _ground(core, t_arrive, {ActantRole.SUBJECT: ivan})

    query = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "employees"),),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
        ),
    )
    _perception, commit, built = _compile(
        service, core, context, query, "Did every employee arrive?"
    )
    assert len(commit.quantified_queries) == 1
    assert engine.solve(built.goal).status is LogicalStatus.UNKNOWN

    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert ActantRole.OBJECT not in event.actants


def test_exists_query_can_be_proved_by_one_witness() -> None:
    core, context, service, engine = _env()
    t_arrive = _template(core, "arrive", (ActantRole.SUBJECT,))
    ivan = _entity(core, "Ivan")
    _ground(core, t_arrive, {ActantRole.SUBJECT: ivan})

    query = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "someone"),),
        (
            _binding(
                "QX", 0, QueryQuantifierOperator.EXISTS
            ),
        ),
    )
    _perception, commit, built = _compile(
        service, core, context, query, "Did someone arrive?"
    )
    root = _function(core, commit.quantified_queries[0].ref)
    assert root.function_id == "EXISTS"
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_restricted_exists_requires_one_shared_witness() -> None:
    core, context, service, engine = _env()
    t_employee = _template(core, "employee", (ActantRole.SUBJECT,))
    t_arrive = _template(core, "arrive", (ActantRole.SUBJECT,))
    ivan = _entity(core, "Ivan")
    maria = _entity(core, "Maria")
    _ground(core, t_employee, {ActantRole.SUBJECT: ivan})
    _ground(core, t_arrive, {ActantRole.SUBJECT: maria})

    query = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "an employee"),),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.EXISTS,
                restriction="employee",
            ),
        ),
    )
    _perception, _commit, built = _compile(
        service, core, context, query, "Did at least one employee arrive?"
    )
    assert engine.solve(built.goal).status is LogicalStatus.UNKNOWN

    _ground(core, t_arrive, {ActantRole.SUBJECT: ivan})
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_not_exists_query_is_unknown_from_absence_but_proved_when_explicit() -> None:
    core, context, service, engine = _env()
    t_arrive = _template(core, "arrive", (ActantRole.SUBJECT,))

    query = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "nobody"),),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.EXISTS,
                negated=True,
            ),
        ),
    )
    _perception, commit, built = _compile(
        service, core, context, query, "Did nobody arrive?"
    )
    root_ref = commit.quantified_queries[0].ref
    assert _function(core, root_ref).function_id == "NOT"
    assert engine.solve(built.goal).status is LogicalStatus.UNKNOWN

    _assert_formula(core, context, root_ref, "Nobody arrived.")
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_not_forall_and_forall_not_are_distinct_goal_topologies() -> None:
    core, context, service, _engine = _env()
    _template(core, "employee", (ActantRole.SUBJECT,))
    _template(core, "arrive", (ActantRole.SUBJECT,))

    not_all = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "employees"),),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
                negated=True,
            ),
        ),
        local_id="Q1",
    )
    _, c1, _ = _compile(
        service, core, context, not_all, "Did not every employee arrive?"
    )

    all_not = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QY", "employees"),),
        (
            _binding(
                "QY",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
        ),
        body_negated=True,
        local_id="Q2",
    )
    _, c2, _ = _compile(
        service, core, context, all_not, "Did every employee not arrive?"
    )

    first = c1.quantified_queries[0].ref
    second = c2.quantified_queries[0].ref
    assert first != second
    assert _function(core, first).function_id == "NOT"
    assert _function(core, second).function_id == "FORALL"


def test_nested_forall_exists_query_preserves_binding_order_and_exact_formula() -> None:
    core, context, service, engine = _env()
    t_employee = _template(core, "employee", (ActantRole.SUBJECT,))
    t_manager = _template(core, "manager", (ActantRole.SUBJECT,))
    t_know = _template(
        core, "know", (ActantRole.SUBJECT, ActantRole.OBJECT)
    )
    x = BoundVar(0, VariableSort.ENTITY)
    y = BoundVar(1, VariableSort.ENTITY)
    employee = _pattern(
        core, t_employee, {ActantRole.SUBJECT: x}
    )
    manager = _pattern(
        core, t_manager, {ActantRole.SUBJECT: y}
    )
    know = _pattern(
        core,
        t_know,
        {ActantRole.SUBJECT: x, ActantRole.OBJECT: y},
    )
    inner_body = core.add_function(
        Domain.C, "AND", (manager, know)
    )
    exists = core.add_function(
        Domain.C, "EXISTS", (y, core.ref(inner_body.uid))
    )
    outer_body = core.add_function(
        Domain.C, "IMPLIES", (employee, core.ref(exists.uid))
    )
    forall = core.add_function(
        Domain.C, "FORALL", (x, core.ref(outer_body.uid))
    )
    forall_ref = core.ref(forall.uid)
    _assert_formula(
        core,
        context,
        forall_ref,
        "Every employee knows at least one manager.",
    )

    query = _query(
        "know",
        (
            _bound(ActantRole.SUBJECT, "QX", "employees"),
            _bound(ActantRole.OBJECT, "QY", "a manager"),
        ),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
            _binding(
                "QY",
                1,
                QueryQuantifierOperator.EXISTS,
                restriction="manager",
            ),
        ),
    )
    _, commit, built = _compile(
        service,
        core,
        context,
        query,
        "Does every employee know at least one manager?",
    )
    integrated = commit.quantified_queries[0]
    assert integrated.variable_ids == (0, 1)
    assert integrated.ref == forall_ref
    assert engine.solve(built.goal).status is LogicalStatus.PROVED


def test_unresolved_nonquantified_operand_does_not_create_entity_or_fake_goal() -> None:
    core, context, service, _engine = _env()
    _template(
        core, "sign", (ActantRole.SUBJECT, ActantRole.OBJECT)
    )
    query = _query(
        "sign",
        (
            _bound(ActantRole.SUBJECT, "QX", "employees"),
            ActantCandidate(ActantRole.OBJECT, mention="GhostDocument"),
        ),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
        ),
    )
    perception = PerceptionResult(
        "Did every employee sign GhostDocument?", queries=(query,)
    )
    commit = service.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(
        commit, context, perception
    )

    assert commit.quantified_queries == ()
    assert len(built) == 1
    assert built[0].goal is None
    assert built[0].diagnostics == (
        "semantic:quantified_query_not_materialized",
    )
    assert core.store.find_entities_by_name("GhostDocument", Domain.C) == ()


def test_document_namespace_rewrites_quantified_binding_handles() -> None:
    query = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "employees"),),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
        ),
    )
    namespaced = namespace_perception_result(
        PerceptionResult("Did every employee arrive?", queries=(query,)),
        3,
    )
    item = namespaced.queries[0]
    assert item.local_id == "B3:Q1"
    assert item.actants[0].entity_ref == "B3:QX"
    assert item.quantified is not None
    assert item.quantified.bindings[0].entity_ref == "B3:QX"



def test_quantified_query_domain_matches_personal_fixed_actant() -> None:
    core, context, service, _engine = _env()
    _template(
        core, "know", (ActantRole.SUBJECT, ActantRole.OBJECT)
    )
    query = _query(
        "know",
        (
            _bound(ActantRole.SUBJECT, "QX", "employees"),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="you",
                normalized_hint="you",
            ),
        ),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
        ),
    )
    # In external input second person resolves to the agent/self P entity.
    perception = PerceptionResult(
        "Does every employee know you?", queries=(query,)
    )
    commit = service.integrate_external(perception, context)
    assert len(commit.quantified_queries) == 1
    root = commit.quantified_queries[0].ref
    assert core.store.domain_of(root.uid) is Domain.P
    body = commit.quantified_queries[0].member_refs[0]
    assert core.store.domain_of(body.uid) is Domain.P



def test_quantified_formula_goal_compiles_without_perception_argument() -> None:
    core, context, service, _engine = _env()
    _template(core, "employee", (ActantRole.SUBJECT,))
    _template(core, "arrive", (ActantRole.SUBJECT,))
    query = _query(
        "arrive",
        (_bound(ActantRole.SUBJECT, "QX", "employees"),),
        (
            _binding(
                "QX",
                0,
                QueryQuantifierOperator.FORALL,
                restriction="employee",
            ),
        ),
    )
    perception = PerceptionResult(
        "Did every employee arrive?", queries=(query,)
    )
    commit = service.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(
        commit, context, perception=None
    )
    assert len(built) == 1
    assert built[0].goal is not None
    assert isinstance(built[0].goal.goal.target, FormulaGoal)
    assert built[0].goal.goal.target.expression == (
        commit.quantified_queries[0].ref
    )
