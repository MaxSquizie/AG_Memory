from __future__ import annotations

import json
from pathlib import Path

from ah.agent import InteractionContext
from ah.config import InferenceSettings, IntegrationSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    AnyOfGoal,
    ExactlyOneOfGoal,
    FormulaGoal,
    FormulaPatternGoal,
    InferenceEngine,
    LogicalStatus,
    MatrixFormulaPatternGoal,
    RoleBindingConclusion,
    SemanticGoalCompiler,
)
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    CommandCandidate,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
    apply_speech_act_scoping,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_semantic_composition" / "a2_cases.txt"
ORACLE = ROOT / "data" / "acceptance_semantic_composition" / "a2_oracle.json"


def runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    context = InteractionContext(self_ref=core.ref(agent.uid), user_ref=core.ref(user.uid))
    integration = IntegrationService(
        core, IntegrationConfig.from_settings(IntegrationSettings())
    )
    engine = InferenceEngine(
        core, InferenceSettings(max_depth=8, max_expanded_states=256)
    )
    return core, context, integration, engine


def assertion(local_id: str, subject: str, state: str, *, status=AssertionStatus.ASSERTED):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            "state",
            "state",
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.STATE)
            ),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention=subject),
            ActantCandidate(ActantRole.STATE, mention=state),
        ),
        status=status,
    )


def expression(operator: PropositionOperator) -> PropositionExprCandidate:
    return PropositionExprCandidate(
        operator,
        members=(
            PropositionExprCandidate.ref_expr("A1"),
            PropositionExprCandidate.ref_expr("A2"),
        ),
    )


def command(expr: PropositionExprCandidate) -> CommandCandidate:
    return CommandCandidate(
        PredicateCandidate(
            "request",
            "request",
            template_candidate=TemplateCandidate((ActantRole.OBJECT,)),
        ),
        (ActantCandidate(ActantRole.OBJECT, proposition=expr),),
        local_id="C1",
    )


def compile_expression(core, context, integration, operator):
    raw = PerceptionResult(
        "typed expression query",
        assertions=(
            assertion("A1", "Лев", "спит"),
            assertion("A2", "Мария", "читает"),
        ),
        commands=(command(expression(operator)),),
        act_dependencies=(
            ActDependencyCandidate("C1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("C1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    perception = apply_speech_act_scoping(raw)
    commit = integration.integrate_external(perception, context)
    before = len(core.store.all_elements())
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1 and built[0].goal is not None
    expected = AnyOfGoal if operator is PropositionOperator.OR else ExactlyOneOfGoal
    assert isinstance(built[0].goal.goal.target, expected)
    assert len(core.store.all_elements()) == before
    return perception, commit, built[0]


def assert_formula(core, operator: str, members):
    operands = tuple(members)
    if operator == "NOT" and len(operands) == 1:
        target = core.store.get_hypernode(operands[0].uid)
        ordinary, _ = core.add_hypernode(
            Domain.C,
            target.template,
            dict(target.actants),
            0.4,
            count_occurrence=False,
            meta={},
        )
        operands = (core.ref(ordinary.uid),)
    formula, _ = core.ensure_function(Domain.C, operator, operands)
    speaker = core.add_entity(Domain.P, {"name": Property("name", "speaker", "str")})
    symbol = core.ensure_abstract_symbol("assert")
    template = core.add_template(
        Domain.H,
        core.ref(symbol.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    core.add_hypernode(
        Domain.H,
        core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(speaker.uid), ActantRole.OBJECT: core.ref(formula.uid)},
        0.3,
        meta={"event_instance": True},
        deduplicate=False,
    )
    return core.ref(formula.uid)


def test_a2_acceptance_oracle_contract() -> None:
    cases = tuple(line for line in CASES.read_text(encoding="utf-8").splitlines() if line)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle["roadmap_step"] == "A2_PROPOSITION_QUERY_GOALS"
    assert oracle["case_count"] == len(cases) == len(oracle["cases"]) == 16
    assert tuple(item["text"] for item in oracle["cases"]) == cases
    assert {item["goal"] for item in oracle["cases"]} >= {
        "OR", "XOR", "MATRIX_OR", "MATRIX_OR_FILL", "MATRIX_XOR_FILL"
    }


def test_or_expression_goal_is_read_only_and_uses_admissible_branch_support() -> None:
    core, context, integration, engine = runtime()
    _perception, commit, built = compile_expression(
        core, context, integration, PropositionOperator.OR
    )
    before = len(core.store.all_elements())
    assert not any(
        getattr(item, "function_id", "") == "OR"
        for item in core.store.all_elements()
    )
    assert engine.solve(built.goal).status is LogicalStatus.UNKNOWN

    query_leaf = core.store.get_hypernode(commit.assertions[0].ref.uid)
    core.add_hypernode(
        Domain.C,
        query_leaf.template,
        dict(query_leaf.actants),
        0.4,
        count_occurrence=True,
        meta={},
    )
    after_assert = len(core.store.all_elements())
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[-1].rule_id == "OR_INTRO"
    assert len(core.store.all_elements()) == after_assert
    assert before < after_assert


def test_or_and_xor_keep_unknown_distinct_from_false() -> None:
    core, context, integration, engine = runtime()
    _perception, commit, or_built = compile_expression(
        core, context, integration, PropositionOperator.OR
    )
    first, second = (item.ref for item in commit.assertions)
    not_first = assert_formula(core, "NOT", (first,))
    before = len(core.store.all_elements())
    unknown_or = engine.solve(or_built.goal)
    assert unknown_or.status is LogicalStatus.UNKNOWN
    assert not_first in unknown_or.premise_refs or not unknown_or.premise_refs
    assert len(core.store.all_elements()) == before

    not_second = assert_formula(core, "NOT", (second,))
    disproved_or = engine.solve(or_built.goal)
    assert disproved_or.status is LogicalStatus.DISPROVED
    assert disproved_or.proof_support[-1].rule_id == "OR_REFUTED"
    assert {not_first.uid, not_second.uid}.issubset(
        {ref.uid for ref in disproved_or.premise_refs}
    )

    core2, context2, integration2, engine2 = runtime()
    _p2, commit2, xor_built = compile_expression(
        core2, context2, integration2, PropositionOperator.XOR
    )
    first2, second2 = (item.ref for item in commit2.assertions)
    query_first = core2.store.get_hypernode(first2.uid)
    core2.add_hypernode(
        Domain.C, query_first.template, dict(query_first.actants), 0.4,
        count_occurrence=True, meta={},
    )
    assert engine2.solve(xor_built.goal).status is LogicalStatus.UNKNOWN
    assert_formula(core2, "NOT", (second2,))
    proved_xor = engine2.solve(xor_built.goal)
    assert proved_xor.status is LogicalStatus.PROVED
    assert proved_xor.proof_support[-1].rule_id == "XOR_INTRO"


def test_xor_is_disproved_by_two_true_branches_without_materializing_xor() -> None:
    core, context, integration, engine = runtime()
    _perception, commit, built = compile_expression(
        core, context, integration, PropositionOperator.XOR
    )
    for item in commit.assertions:
        query_leaf = core.store.get_hypernode(item.ref.uid)
        core.add_hypernode(
            Domain.C, query_leaf.template, dict(query_leaf.actants), 0.4,
            count_occurrence=True, meta={},
        )
    before = len(core.store.all_elements())
    outcome = engine.solve(built.goal)
    assert outcome.status is LogicalStatus.DISPROVED
    assert outcome.proof_support[-1].rule_id == "XOR_MULTI_TRUE"
    assert len(core.store.all_elements()) == before
    assert not any(
        getattr(item, "function_id", "") == "XOR"
        for item in core.store.all_elements()
    )


def test_proposition_only_query_shell_uses_runtime_formula_pattern() -> None:
    core, context, integration, engine = runtime()
    query = QueryCandidate(
        PredicateCandidate(
            "true",
            "true",
            template_candidate=TemplateCandidate((ActantRole.OBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.OBJECT,
                proposition=expression(PropositionOperator.OR),
            ),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    perception = PerceptionResult(
        "typed proposition shell",
        assertions=(
            assertion("A1", "Лев", "спит", status=AssertionStatus.EMBEDDED),
            assertion("A2", "Мария", "читает", status=AssertionStatus.EMBEDDED),
        ),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("Q1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = integration.integrate_external(perception, context)
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert isinstance(built[0].goal.goal.target, FormulaPatternGoal)
    leaf = core.store.get_hypernode(commit.assertions[0].ref.uid)
    core.add_hypernode(
        Domain.C,
        leaf.template,
        dict(leaf.actants),
        0.4,
        count_occurrence=True,
        meta={},
    )
    before = len(core.store.all_elements())
    outcome = engine.solve(built[0].goal)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[-1].rule_id == "OR_INTRO"
    assert len(core.store.all_elements()) == before


def matrix_assertion(local_id, subject, proposition, *, status=AssertionStatus.ASSERTED):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            "believe", "believe",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention=subject),
            ActantCandidate(ActantRole.OBJECT, proposition=proposition),
        ),
        status=status,
    )


def test_compound_proposition_matrix_query_matches_existing_fact_read_only() -> None:
    core, context, integration, engine = runtime()
    stored = PerceptionResult(
        "stored matrix fact",
        assertions=(
            matrix_assertion("M1", "Анна", expression(PropositionOperator.OR)),
            assertion("A1", "Лев", "спит", status=AssertionStatus.EMBEDDED),
            assertion("A2", "Мария", "читает", status=AssertionStatus.EMBEDDED),
        ),
        act_dependencies=(
            ActDependencyCandidate("M1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("M1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    stored_commit = integration.integrate_external(stored, context)

    query = QueryCandidate(
        PredicateCandidate(
            "believe", "believe",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Анна"),
            ActantCandidate(ActantRole.OBJECT, proposition=expression(PropositionOperator.OR)),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    raw = PerceptionResult(
        "matrix query",
        assertions=(
            assertion("A1", "Лев", "спит", status=AssertionStatus.EMBEDDED),
            assertion("A2", "Мария", "читает", status=AssertionStatus.EMBEDDED),
        ),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("Q1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = integration.integrate_external(raw, context)
    before = len(core.store.all_elements())
    built = SemanticGoalCompiler(core).build(commit, context, raw)
    assert len(built) == 1 and built[0].goal is not None
    assert isinstance(built[0].goal.goal.target, MatrixFormulaPatternGoal)
    outcome = engine.solve(built[0].goal)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[0].rule_id == "FACT_MATCH"
    assert len(core.store.all_elements()) == before
    assert engine.solve(FormulaGoal(stored_commit.assertions[1].ref)).status is LogicalStatus.UNKNOWN


def test_compound_matrix_pattern_can_bind_a_requested_role() -> None:
    core, context, integration, engine = runtime()
    stored = PerceptionResult(
        "stored matrix fact",
        assertions=(
            matrix_assertion("M1", "Анна", expression(PropositionOperator.XOR)),
            assertion("A1", "маяк", "виден", status=AssertionStatus.EMBEDDED),
            assertion("A2", "сирена", "слышна", status=AssertionStatus.EMBEDDED),
        ),
        act_dependencies=(
            ActDependencyCandidate("M1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("M1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    integration.integrate_external(stored, context)
    query = QueryCandidate(
        PredicateCandidate(
            "believe", "believe",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (
            ActantCandidate(
                ActantRole.OBJECT,
                proposition=expression(PropositionOperator.XOR),
            ),
        ),
        requested_roles=(ActantRole.SUBJECT,),
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q1",
    )
    perception = PerceptionResult(
        "matrix role query",
        assertions=(
            assertion("A1", "маяк", "виден", status=AssertionStatus.EMBEDDED),
            assertion("A2", "сирена", "слышна", status=AssertionStatus.EMBEDDED),
        ),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate("Q1", "A1", ActDependencyKind.SUBORDINATE),
            ActDependencyCandidate("Q1", "A2", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = integration.integrate_external(perception, context)
    before = len(core.store.all_elements())
    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert isinstance(built[0].goal.goal.target, MatrixFormulaPatternGoal)
    outcome = engine.solve(built[0].goal)
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.conclusion, RoleBindingConclusion)
    assert outcome.conclusion.role is ActantRole.SUBJECT
    assert outcome.proof_support[0].rule_id == "FACT_MATCH"
    assert len(core.store.all_elements()) == before


def test_a2_corpus_sentences_are_not_production_rules() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "ah" / "inference").rglob("*.py")
    ).casefold()
    for line in CASES.read_text(encoding="utf-8").splitlines():
        assert line.casefold() not in production
