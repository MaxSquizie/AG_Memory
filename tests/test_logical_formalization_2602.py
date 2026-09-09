from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import FormulaGoal, GoalSpec, InferenceEngine, InferenceQuery, LogicalStatus
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, FunctionSymbol, Property, Ref
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    ConditionalCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
    TemplateCandidate,
)
from ah.perception.linguistic_candidates import (
    CandidateSpan,
    ClauseCandidate,
    LinguisticCandidateGraph,
)
from ah.perception.logical_formalization import LogicalFormBuilder


@dataclass(frozen=True)
class _Span:
    start_index: int
    end_index: int


def _assertion(
    local_id: str,
    predicate: str,
    subject: str,
    evidence: EvidenceSpan,
    *,
    negated: bool = False,
    status: AssertionStatus = AssertionStatus.ASSERTED,
    proposition: PropositionExprCandidate | None = None,
) -> AssertionCandidate:
    actants = [ActantCandidate(ActantRole.SUBJECT, mention=subject)]
    roles = [ActantRole.SUBJECT]
    if proposition is not None:
        actants.append(
            ActantCandidate(
                ActantRole.OBJECT,
                mention="content",
                proposition=proposition,
            )
        )
        roles.append(ActantRole.OBJECT)
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate(tuple(roles)),
        ),
        tuple(actants),
        evidence=evidence,
        negated=negated,
        status=status,
    )


def _graph(text: str) -> LinguisticCandidateGraph:
    span = CandidateSpan(1, 1, text, EvidenceSpan(text, 0, len(text)))
    clause = ClauseCandidate("CL1", 0, span, ())
    return LinguisticCandidateGraph(text, (), (clause,), (), ())


def _render(expr: PropositionExprCandidate) -> str:
    if expr.operator is PropositionOperator.REF:
        return expr.ref or ""
    if expr.operator is PropositionOperator.NOT:
        return f"NOT({_render(expr.members[0])})"
    return f"{expr.operator.value}(" + ",".join(_render(x) for x in expr.members) + ")"


def test_semantic_paraphrase_can_form_or_without_keyword_authority() -> None:
    text = "Одно из двух: Иван придёт, Мария позвонит."
    e1 = EvidenceSpan("Иван придёт", text.index("Иван"), text.index("Иван") + len("Иван придёт"))
    e2 = EvidenceSpan("Мария позвонит", text.index("Мария"), text.index("Мария") + len("Мария позвонит"))
    assertions = (
        _assertion("A1", "прийти", "Иван", e1),
        _assertion("A2", "позвонить", "Мария", e2),
    )
    calls: list[str] = []

    def probe(stage: str, prompt: str, choices: tuple[str, ...]) -> str:
        calls.append(stage)
        assert stage == "logical_relation"
        assert "Одно из двух" in prompt
        return "OR"

    result = LogicalFormBuilder(_graph(text), probe).build(
        text, assertions, {"A1": None, "A2": None}
    )
    assert len(result.roots) == 1
    assert _render(result.roots[0].expression) == "OR(A1,A2)"
    assert calls == ["logical_relation"]


def test_mixed_and_or_scope_is_chosen_only_from_deterministic_candidate_trees() -> None:
    text = "Иван пришёл и Мария позвонила или Пётр ушёл."
    parts = ("Иван пришёл", "Мария позвонила", "Пётр ушёл")
    assertions = []
    for index, part in enumerate(parts, 1):
        start = text.index(part)
        assertions.append(
            _assertion(
                f"A{index}",
                ("прийти", "позвонить", "уйти")[index - 1],
                ("Иван", "Мария", "Пётр")[index - 1],
                EvidenceSpan(part, start, start + len(part)),
            )
        )

    def probe(stage: str, prompt: str, choices: tuple[str, ...]) -> str:
        assert stage == "logical_scope"
        wanted = "OR(AND(A1,A2),A3)"
        for line in prompt.splitlines():
            if ": " not in line:
                continue
            label, rendered = line.split(": ", 1)
            if rendered == wanted:
                assert label in choices
                return label
        raise AssertionError(prompt)

    result = LogicalFormBuilder(_graph(text), probe).build(
        text, tuple(assertions), {f"A{i}": None for i in range(1, 4)}
    )
    assert len(result.roots) == 1
    assert _render(result.roots[0].expression) == "OR(AND(A1,A2),A3)"


def test_local_negation_is_explicit_inside_compound_formula_ast() -> None:
    text = "Иван пришёл и Мария не ушла."
    p1 = "Иван пришёл"
    p2 = "Мария не ушла"
    s1, s2 = text.index(p1), text.index(p2)
    assertions = (
        _assertion("A1", "прийти", "Иван", EvidenceSpan(p1, s1, s1 + len(p1))),
        _assertion(
            "A2", "уйти", "Мария", EvidenceSpan(p2, s2, s2 + len(p2)),
            negated=True,
        ),
    )
    result = LogicalFormBuilder(_graph(text), lambda *_: "UNCLEAR").build(
        text, assertions, {"A1": None, "A2": None}
    )
    assert len(result.roots) == 1
    assert _render(result.roots[0].expression) == "AND(A1,NOT(A2))"


def test_existing_conditional_is_exposed_as_common_implies_ast_without_new_probe() -> None:
    text = "Если Иван придёт, Мария уйдёт."
    a = _assertion(
        "A1", "прийти", "Иван", EvidenceSpan("Иван придёт", 5, 16),
        status=AssertionStatus.CONDITIONAL,
    )
    b = _assertion(
        "A2", "уйти", "Мария", EvidenceSpan("Мария уйдёт", 18, 29),
        status=AssertionStatus.CONDITIONAL,
    )
    conditional = ConditionalCandidate(("A1",), ("A2",))

    def forbidden(*_args):
        raise AssertionError("known conditional topology must not need a new semantic probe")

    result = LogicalFormBuilder(_graph(text), forbidden).build(
        text, (a, b), {"A1": None, "A2": None}, (conditional,)
    )
    assert len(result.roots) == 1
    assert _render(result.roots[0].expression) == "IMPLIES(A1,A2)"


def _env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    service = IntegrationService(
        core,
        IntegrationConfig(0.4, 0.3, 0.2),
    )
    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    return core, context, service, engine


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def test_or_formula_root_is_asserted_while_both_leaf_propositions_remain_scoped() -> None:
    core, context, service, engine = _env()
    e1 = EvidenceSpan("Иван пришёл", 0, 11)
    e2 = EvidenceSpan("Мария ушла", 16, 26)
    a1 = _assertion("A1", "прийти", "Иван", e1)
    a2 = _assertion("A2", "уйти", "Мария", e2)
    root = PropositionRootCandidate(
        "F1",
        PropositionExprCandidate(
            PropositionOperator.OR,
            members=(
                PropositionExprCandidate.ref_expr("A1"),
                PropositionExprCandidate.ref_expr("A2"),
            ),
        ),
    )
    commit = service.integrate_external(
        PerceptionResult(
            "Иван пришёл или Мария ушла.",
            assertions=(a1, a2),
            proposition_roots=(root,),
        ),
        context,
    )

    assert len(commit.formulas) == 1
    formula_ref = commit.formulas[0].ref
    formula = core.store.get_element_any_domain(formula_ref.uid)
    assert isinstance(formula, FunctionSymbol)
    assert formula.function_id == "OR"
    assert _solve(engine, formula_ref).status is LogicalStatus.PROVED

    for item in commit.assertions:
        node = core.store.get_hypernode(item.ref.uid)
        assert node.meta.get("semantic_scope") == "LOGICAL"
        assert int(node.meta.get("occurrence_count", 0)) == 0
        assert _solve(engine, item.ref).status is LogicalStatus.UNKNOWN


def test_compound_formula_materializes_local_not_once_at_ast_level() -> None:
    core, context, service, _engine = _env()
    a1 = _assertion("A1", "прийти", "Иван", EvidenceSpan("Иван пришёл", 0, 11))
    a2 = _assertion(
        "A2", "уйти", "Мария", EvidenceSpan("Мария не ушла", 14, 27),
        negated=True,
    )
    expr = PropositionExprCandidate(
        PropositionOperator.AND,
        members=(
            PropositionExprCandidate.ref_expr("A1"),
            PropositionExprCandidate(
                PropositionOperator.NOT,
                members=(PropositionExprCandidate.ref_expr("A2"),),
            ),
        ),
    )
    commit = service.integrate_external(
        PerceptionResult(
            "Иван пришёл и Мария не ушла.",
            assertions=(a1, a2),
            proposition_roots=(PropositionRootCandidate("F1", expr),),
        ),
        context,
    )
    assert len(commit.formulas) == 1
    assert all(item.ref.kind.value == "N" for item in commit.assertions)
    root = core.store.get_element_any_domain(commit.formulas[0].ref.uid)
    assert isinstance(root, FunctionSymbol) and root.function_id == "AND"
    second = root.operands[1]
    assert isinstance(second, Ref)
    not_g = core.store.get_element_any_domain(second.uid)
    assert isinstance(not_g, FunctionSymbol) and not_g.function_id == "NOT"
    assert not_g.operands == (commit.assertions[1].ref,)


def test_truth_negating_matrix_can_be_consumed_as_operator_source_not_world_fact() -> None:
    core, context, service, _engine = _env()
    child = _assertion(
        "A1",
        "прийти",
        "Иван",
        EvidenceSpan("Иван пришёл", 10, 21),
        status=AssertionStatus.EMBEDDED,
    )
    content = PropositionExprCandidate.ref_expr("A1")
    parent = _assertion(
        "A2",
        "верно",
        "это",
        EvidenceSpan("Не верно, что Иван пришёл", 0, 21),
        negated=True,
        proposition=content,
    )
    root = PropositionRootCandidate(
        "F1",
        PropositionExprCandidate(
            PropositionOperator.NOT,
            members=(content,),
        ),
        operator_source_refs=("A2",),
    )
    commit = service.integrate_external(
        PerceptionResult(
            "Не верно, что Иван пришёл.",
            assertions=(parent, child),
            proposition_roots=(root,),
        ),
        context,
    )
    assert len(commit.assertions) == 1
    assert commit.assertions[0].local_id == "A1"
    assert len(commit.formulas) == 1
    formula = core.store.get_element_any_domain(commit.formulas[0].ref.uid)
    assert isinstance(formula, FunctionSymbol) and formula.function_id == "NOT"
