from __future__ import annotations

import json
from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    AssociationQueryBuildResult,
    CounterfactualContext,
    CounterfactualGoal,
    ExistsGoal,
    FormulaGoal,
    FormulaPatternGoal,
    InferenceEngine,
    LogicalStatus,
    RelationGoal,
    SemanticGoalCompiler,
)
from ah.integration import (
    CandidateValidationError,
    IntegrationConfig,
    IntegrationService,
    namespace_perception_result,
)
from ah.integration.candidate_validator import CandidateValidator
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, Domain, FunctionSymbol, Property, Ref
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActRelationCandidate,
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    AssociationActRelationCandidate,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    QuantifiedQueryBinding,
    QuantifiedQuerySpec,
    QueryCandidate,
    QueryMode,
    QueryQuantifierOperator,
    TemplateCandidate,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_semantic_composition" / "a3_cases.txt"
ORACLE = ROOT / "data" / "acceptance_semantic_composition" / "a3_oracle.json"


def _runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(
        user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid)
    )
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _entity(core: AHCore, name: str) -> Ref:
    matches = core.store.find_entities_by_name(name, Domain.C)
    if matches:
        return core.ref(matches[0].uid)
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _template(
    core: AHCore, predicate: str, roles: tuple[ActantRole, ...]
) -> Ref:
    symbol = core.ensure_abstract_symbol(predicate)
    matches = tuple(
        item
        for item in core.store.find_templates_by_predicate(symbol.uid)
        if item.roles == roles
    )
    if matches:
        return core.ref(matches[0].uid)
    item = core.add_template(Domain.C, core.ref(symbol.uid), roles)
    return core.ref(item.uid)


def _assertion(
    local_id: str,
    predicate: str,
    subject: str,
    *,
    status: AssertionStatus,
) -> AssertionCandidate:
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention=subject),),
        status=status,
    )


def _quantified_query(
    predicate: str,
    *,
    operator: QueryQuantifierOperator = QueryQuantifierOperator.EXISTS,
    restriction: str | None = None,
    scope_operators: tuple[PropositionOperator, ...] = (),
) -> QueryCandidate:
    return QueryCandidate(
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="participants",
                normalized_hint="participants",
                entity_ref="QX",
            ),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
        quantified=QuantifiedQuerySpec(
            (
                QuantifiedQueryBinding(
                    "QX",
                    0,
                    operator,
                    restriction_lemma=restriction,
                ),
            )
        ),
        scope_operators=scope_operators,
    )


def _assert_formula(
    core: AHCore,
    context: InteractionContext,
    formula: Ref,
    text: str,
) -> None:
    result = ExperienceMapper(core, event_weight=0.3, follow_weight=0.2).record_turn(
        source_text=text,
        speaker_ref=context.user_ref,
        semantic_refs=(formula,),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )
    context.last_experience_ref = result.event_ref


def _formula(core: AHCore, ref: Ref) -> FunctionSymbol:
    item = core.store.get_element_any_domain(ref.uid)
    assert isinstance(item, FunctionSymbol)
    return item


def _uids(core: AHCore) -> frozenset[str]:
    return frozenset(core.store.all_uids())


def test_a3_acceptance_oracle_contract() -> None:
    cases = tuple(line for line in CASES.read_text(encoding="utf-8").splitlines() if line)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle["roadmap_step"] == "A3_RECURSIVE_ORTHOGONAL_SCOPES"
    assert oracle["case_count"] == len(cases) == len(oracle["cases"]) == 20
    assert tuple(item["text"] for item in oracle["cases"]) == cases
    compositions = {item["composition"] for item in oracle["cases"]}
    assert {
        "POSSIBLE(FORALL)",
        "COUNTERFACTUAL(POSSIBLE)",
        "COUNTERFACTUAL(EXISTS)",
        "COUNTERFACTUAL(IS-A)",
        "ASSOCIATION(EXISTS,ENTITY)",
        "COUNTERFACTUAL(POSSIBLE(FORALL))",
    }.issubset(compositions)
    assert {item["expected"] for item in oracle["cases"]} >= {
        "OPEN_WORLD",
        "AMBIGUOUS",
        "INVERSION",
        "ELLIPSIS",
        "REJECT_UNBOUND_ENDPOINTS",
    }


def test_query_scope_ast_validates_and_survives_namespacing() -> None:
    query = _quantified_query(
        "arrive",
        operator=QueryQuantifierOperator.FORALL,
        restriction="employee",
        scope_operators=(
            PropositionOperator.POSSIBLE,
            PropositionOperator.REQUIRED,
        ),
    )
    namespaced = namespace_perception_result(
        PerceptionResult("scope", queries=(query,)), 3
    ).queries[0]
    assert namespaced.local_id == "B3:Q1"
    assert namespaced.quantified is not None
    assert namespaced.quantified.bindings[0].entity_ref == "B3:QX"
    assert namespaced.scope_operators == query.scope_operators

    with pytest.raises(ValueError, match="modal operators only"):
        QueryCandidate(
            PredicateCandidate("arrive"),
            query_mode=QueryMode.EXISTS,
            scope_operators=(PropositionOperator.AND,),
        )
    with pytest.raises(ValueError, match="requires a quantified query body"):
        QueryCandidate(
            PredicateCandidate("arrive"),
            query_mode=QueryMode.EXISTS,
            scope_operators=(PropositionOperator.POSSIBLE,),
        )


def test_quantified_modal_goal_preserves_nested_scope_and_is_read_only() -> None:
    core, context, service, engine = _runtime()
    _template(core, "employee", (ActantRole.SUBJECT,))
    _template(core, "arrive", (ActantRole.SUBJECT,))
    query = _quantified_query(
        "arrive",
        operator=QueryQuantifierOperator.FORALL,
        restriction="employee",
        scope_operators=(
            PropositionOperator.POSSIBLE,
            PropositionOperator.REQUIRED,
        ),
    )
    perception = PerceptionResult("typed quantified modal", queries=(query,))
    commit = service.integrate_external(perception, context)
    quantified_ref = commit.quantified_queries[0].ref
    before = _uids(core)

    built = SemanticGoalCompiler(core).build(commit, context, perception)[0]
    assert built.goal is not None
    target = built.goal.goal.target
    assert isinstance(target, FormulaPatternGoal)
    assert target.pattern.operator == "POSSIBLE"
    assert target.pattern.members[0].operator == "REQUIRED"
    assert target.pattern.members[0].members[0].ref == quantified_ref
    assert built.diagnostics == (
        "semantic:quantified_modal_formula_goal",
        "semantic:quantified_formula_goal",
    )
    assert engine.solve(built.goal).status is LogicalStatus.UNKNOWN
    assert _uids(core) == before

    required, _ = core.ensure_function(Domain.C, "REQUIRED", (quantified_ref,))
    possible, _ = core.ensure_function(
        Domain.C, "POSSIBLE", (core.ref(required.uid),)
    )
    possible_ref = core.ref(possible.uid)
    _assert_formula(core, context, possible_ref, "typed modal assertion")
    asserted = _uids(core)
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[-1].rule_id == "POSSIBLE_ASSERTED"
    assert possible_ref in outcome.proof_support[-1].premise_refs
    assert _uids(core) == asserted


def test_counterfactual_modal_goal_keeps_context_and_exact_modal_support() -> None:
    core, context, service, engine = _runtime()
    _template(core, "operate", (ActantRole.SUBJECT,))
    _template(core, "visible", (ActantRole.SUBJECT,))
    assumption = _assertion(
        "A1", "operate", "server", status=AssertionStatus.HYPOTHETICAL
    )
    target_assertion = _assertion(
        "A2", "visible", "beacon", status=AssertionStatus.EMBEDDED
    )
    modal = PropositionExprCandidate(
        PropositionOperator.POSSIBLE,
        members=(PropositionExprCandidate.ref_expr("A2"),),
    )
    query = QueryCandidate(
        PredicateCandidate(
            "true",
            "true",
            template_candidate=TemplateCandidate((ActantRole.OBJECT,)),
        ),
        (ActantCandidate(ActantRole.OBJECT, proposition=modal),),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    perception = PerceptionResult(
        "typed counterfactual modal",
        assertions=(assumption, target_assertion),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("Q1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = service.integrate_external(perception, context)
    target_ref = next(item.ref for item in commit.assertions if item.local_id == "A2")
    scoped_target = core.store.get_hypernode(target_ref.uid)
    ordinary_target, _ = core.add_hypernode(
        Domain.C,
        scoped_target.template,
        dict(scoped_target.actants),
        0.4,
        count_occurrence=False,
        meta={},
    )
    possible, _ = core.ensure_function(
        Domain.C, "POSSIBLE", (core.ref(ordinary_target.uid),)
    )
    possible_ref = core.ref(possible.uid)
    _assert_formula(core, context, possible_ref, "possible beacon")
    before = _uids(core)

    built = SemanticGoalCompiler(core).build(commit, context, perception)[0]
    assert built.goal is not None
    target = built.goal.goal.target
    assert isinstance(target, CounterfactualGoal)
    assert isinstance(target.target, FormulaPatternGoal)
    assert target.target.pattern.operator == "POSSIBLE"
    assert built.diagnostics == (
        "semantic:counterfactual_composed_goal:FormulaPatternGoal",
        "semantic:counterfactual_modal_target",
    )
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.proof_context, CounterfactualContext)
    assert outcome.proof_support[-1].rule_id == "POSSIBLE_ASSERTED"
    assert possible_ref in outcome.proof_support[-1].premise_refs
    assert _uids(core) == before


def test_counterfactual_quantified_goal_uses_hypothesis_as_exists_witness() -> None:
    core, context, service, engine = _runtime()
    _template(core, "arrive", (ActantRole.SUBJECT,))
    assumption = _assertion(
        "A1", "arrive", "Ivan", status=AssertionStatus.HYPOTHETICAL
    )
    query = _quantified_query("arrive")
    perception = PerceptionResult(
        "typed counterfactual quantified",
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = service.integrate_external(perception, context)
    assumption_ref = next(item.ref for item in commit.assertions if item.local_id == "A1")
    quantified_ref = commit.quantified_queries[0].ref
    before = _uids(core)

    built = SemanticGoalCompiler(core).build(commit, context, perception)[0]
    assert built.goal is not None
    target = built.goal.goal.target
    assert isinstance(target, CounterfactualGoal)
    assert target.assumptions == (assumption_ref,)
    assert target.target == FormulaGoal(quantified_ref)
    assert not isinstance(target.target, ExistsGoal)
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.proof_context, CounterfactualContext)
    assert outcome.proof_support[-1].rule_id == "EXISTS_WITNESS"
    assert assumption_ref in outcome.proof_support[-1].premise_refs
    assert _uids(core) == before


def test_counterfactual_relation_goal_keeps_typed_relation_and_support() -> None:
    core, context, service, engine = _runtime()
    _template(core, "operate", (ActantRole.SUBJECT,))
    crip = _entity(core, "Crip")
    ai = _entity(core, "AI")
    link = core.add_link("IS-A", crip, ai, 0.4)
    assumption = _assertion(
        "A1", "operate", "server", status=AssertionStatus.HYPOTHETICAL
    )
    query = QueryCandidate(
        PredicateCandidate(
            "be",
            "be",
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.STATE)
            ),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Crip"),
            ActantCandidate(ActantRole.STATE, mention="AI"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    perception = PerceptionResult(
        "typed counterfactual relation",
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
        ),
        act_relations=(
            ActRelationCandidate(
                "IS-A", "Q1", ActantRole.SUBJECT, ActantRole.STATE
            ),
        ),
    )
    commit = service.integrate_external(perception, context)
    before = _uids(core)

    built = SemanticGoalCompiler(core).build(commit, context, perception)[0]
    assert built.goal is not None
    target = built.goal.goal.target
    assert isinstance(target, CounterfactualGoal)
    assert target.target == RelationGoal("IS-A", crip, ai)
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.proof_context, CounterfactualContext)
    assert outcome.proof_support[-1].rule_id == "DIRECT_RELATION"
    assert core.ref(link.uid) in outcome.proof_support[-1].premise_refs
    assert _uids(core) == before


def test_quantified_association_uses_formula_endpoint_without_compiler_writes() -> None:
    core, context, service, _engine = _runtime()
    _template(core, "associate", (ActantRole.SUBJECT, ActantRole.OBJECT))
    _template(core, "city", (ActantRole.SUBJECT,))
    river = _entity(core, "river")
    query = QueryCandidate(
        PredicateCandidate(
            "associate",
            "associate",
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.OBJECT)
            ),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="a city",
                normalized_hint="city",
                entity_ref="QX",
            ),
            ActantCandidate(ActantRole.OBJECT, mention="river"),
        ),
        local_id="Q1",
        quantified=QuantifiedQuerySpec(
            (
                QuantifiedQueryBinding(
                    "QX",
                    0,
                    QueryQuantifierOperator.EXISTS,
                    restriction_lemma="city",
                ),
            )
        ),
    )
    perception = PerceptionResult(
        "typed quantified association",
        queries=(query,),
        act_relations=(
            AssociationActRelationCandidate(
                "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
            ),
        ),
    )
    commit = service.integrate_external(perception, context)
    quantified = commit.quantified_queries[0]
    before = _uids(core)

    built = SemanticGoalCompiler(core).build(commit, context, perception)[0]
    assert isinstance(built, AssociationQueryBuildResult)
    assert built.goal is None
    assert built.association_goal is not None
    assert built.association_goal.left == quantified.ref
    assert built.association_goal.right == river
    assert built.diagnostics == ("semantic:quantified_association_goal",)
    assert quantified.ref in built.attention_refs
    assert set(quantified.member_refs).issubset(set(built.attention_refs))
    assert _uids(core) == before


def test_quantified_association_rejects_selectors_that_drop_bound_endpoint() -> None:
    query = QueryCandidate(
        PredicateCandidate(
            "associate",
            "associate",
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION)
            ),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="a city",
                entity_ref="QX",
            ),
            ActantCandidate(ActantRole.OBJECT, mention="journal"),
            ActantCandidate(ActantRole.LOCATION, mention="archive"),
        ),
        local_id="Q1",
        quantified=QuantifiedQuerySpec(
            (
                QuantifiedQueryBinding(
                    "QX", 0, QueryQuantifierOperator.EXISTS
                ),
            )
        ),
    )
    perception = PerceptionResult(
        "invalid quantified association",
        queries=(query,),
        act_relations=(
            AssociationActRelationCandidate(
                "ASSOCIATION", "Q1", ActantRole.OBJECT, ActantRole.LOCATION
            ),
        ),
    )
    with pytest.raises(
        CandidateValidationError,
        match="must select at least one bound endpoint",
    ):
        CandidateValidator().validate(perception)


def test_recursive_counterfactual_modal_quantified_scope_is_not_lowered() -> None:
    core, context, service, engine = _runtime()
    _template(core, "arrive", (ActantRole.SUBJECT,))
    assumption = _assertion(
        "A1", "arrive", "Ivan", status=AssertionStatus.HYPOTHETICAL
    )
    query = _quantified_query(
        "arrive", scope_operators=(PropositionOperator.POSSIBLE,)
    )
    perception = PerceptionResult(
        "typed recursive scopes",
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = service.integrate_external(perception, context)
    before = _uids(core)
    built = SemanticGoalCompiler(core).build(commit, context, perception)[0]
    assert built.goal is not None
    counterfactual = built.goal.goal.target
    assert isinstance(counterfactual, CounterfactualGoal)
    assert isinstance(counterfactual.target, FormulaPatternGoal)
    assert counterfactual.target.pattern.operator == "POSSIBLE"
    assert counterfactual.target.pattern.members[0].ref == commit.quantified_queries[0].ref
    assert not isinstance(counterfactual.target, ExistsGoal)
    # The hypothetical witness proves the inner EXISTS, but non-factivity forbids
    # discarding POSSIBLE.  Without an asserted modal wrapper the result stays open.
    assert engine.solve(built.goal).status is LogicalStatus.UNKNOWN
    assert _uids(core) == before


def test_counterfactual_modal_ambiguity_fails_closed_without_scope_pollution() -> None:
    core, context, service, _engine = _runtime()
    _template(core, "operate", (ActantRole.SUBJECT,))
    _template(core, "visible", (ActantRole.SUBJECT,))
    assumption = _assertion(
        "A1", "operate", "server", status=AssertionStatus.HYPOTHETICAL
    )
    target = _assertion(
        "A2", "visible", "beacon", status=AssertionStatus.EMBEDDED
    )
    possible = PropositionExprCandidate(
        PropositionOperator.POSSIBLE,
        members=(PropositionExprCandidate.ref_expr("A2"),),
    )
    required = PropositionExprCandidate(
        PropositionOperator.REQUIRED,
        members=(PropositionExprCandidate.ref_expr("A2"),),
    )
    query = QueryCandidate(
        PredicateCandidate(
            "true",
            "true",
            template_candidate=TemplateCandidate(
                (ActantRole.OBJECT, ActantRole.STATE)
            ),
        ),
        (
            ActantCandidate(ActantRole.OBJECT, proposition=possible),
            ActantCandidate(ActantRole.STATE, proposition=required),
        ),
        local_id="Q1",
    )
    perception = PerceptionResult(
        "ambiguous modal owner",
        assertions=(assumption, target),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("Q1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = service.integrate_external(perception, context)
    before = _uids(core)
    built = SemanticGoalCompiler(core).build(commit, context, perception)[0]
    assert built.goal is None
    assert built.diagnostics == (
        "semantic:counterfactual_modal_scope_not_unique:2",
    )
    assert _uids(core) == before


def test_a3_has_no_legacy_not_supported_diagnostics_or_corpus_rules() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for subtree in ("perception", "inference", "integration")
        for path in (ROOT / "src" / "ah" / subtree).rglob("*.py")
    )
    for diagnostic in (
        "semantic:counterfactual_relation_target_not_supported",
        "semantic:counterfactual_quantified_target_not_supported",
        "semantic:quantified_modal_target_not_supported",
        "semantic:counterfactual_modal_target_not_supported",
        "semantic:POSSIBLE_goal_not_supported",
        "semantic:REQUIRED_goal_not_supported",
        "semantic:PERMITTED_goal_not_supported",
    ):
        assert diagnostic not in production
    folded = production.casefold()
    for line in CASES.read_text(encoding="utf-8").splitlines():
        assert line.casefold() not in folded
