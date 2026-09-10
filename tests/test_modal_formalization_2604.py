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
    SourceToken,
)
from ah.perception.modal_formalization import ModalScopeBuilder
from ah.perception.morphology import MorphInfo


@dataclass(frozen=True)
class _Span:
    start_index: int
    end_index: int


def _tokens(text: str, specs: tuple[tuple[str, str | None], ...]) -> tuple[SourceToken, ...]:
    out = []
    cursor = 0
    for index, (surface, pos) in enumerate(specs, 1):
        start = text.index(surface, cursor)
        end = start + len(surface)
        cursor = end
        analyses = () if pos is None else (MorphInfo(surface.casefold(), pos),)
        out.append(SourceToken(index, surface, start, end, analyses))
    return tuple(out)


def _graph(text: str, specs: tuple[tuple[str, str | None], ...]) -> LinguisticCandidateGraph:
    tokens = _tokens(text, specs)
    span = CandidateSpan(
        1,
        len(tokens),
        text,
        EvidenceSpan(text, 0, len(text)),
    )
    clause = ClauseCandidate("CL1", 0, span, ())
    return LinguisticCandidateGraph(text, tokens, (clause,), (), ())


def _assertion(
    local_id: str,
    predicate: str,
    subject: str,
    evidence_text: str,
    source_text: str,
    *,
    negated: bool = False,
) -> AssertionCandidate:
    start = source_text.index(evidence_text)
    predicate_start = source_text.rindex(predicate, start, start + len(evidence_text))
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            evidence=EvidenceSpan(
                predicate,
                predicate_start,
                predicate_start + len(predicate),
            ),
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention=subject,
                evidence=EvidenceSpan(
                    subject,
                    source_text.index(subject, start),
                    source_text.index(subject, start) + len(subject),
                ),
            ),
        ),
        evidence=EvidenceSpan(
            evidence_text, start, start + len(evidence_text)
        ),
        negated=negated,
    )


def _render(expr: PropositionExprCandidate) -> str:
    if expr.operator is PropositionOperator.REF:
        return expr.ref or ""
    return (
        f"{expr.operator.value}("
        + ",".join(_render(member) for member in expr.members)
        + ")"
    )


def _env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(
        user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid)
    )
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    engine = InferenceEngine(
        core, InferenceSettings(max_depth=8, max_expanded_states=128)
    )
    return core, context, service, engine


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def test_leading_epistemic_modifier_wraps_one_bare_proposition() -> None:
    text = "Возможно, сервер работает."
    graph = _graph(
        text,
        (
            ("Возможно", "PRED"),
            (",", None),
            ("сервер", "NOUN"),
            ("работает", "VERB"),
            (".", None),
        ),
    )
    assertion = _assertion(
        "A1", "работает", "сервер", "сервер работает", text
    )

    def probe(stage: str, _prompt: str, _choices: tuple[str, ...]) -> str:
        assert stage == "modal_operator"
        return "POSSIBLE"

    result = ModalScopeBuilder(graph, probe).build(
        text, (assertion,), {"A1": _Span(4, 4)}
    )
    assert result.unresolved is None
    assert len(result.roots) == 1
    assert _render(result.roots[0].expression) == "POSSIBLE(A1)"


def test_modal_scope_can_select_one_leaf_inside_existing_and() -> None:
    text = "Иван пришёл и, возможно, Мария ушла."
    graph = _graph(
        text,
        (
            ("Иван", "NOUN"),
            ("пришёл", "VERB"),
            ("и", "CONJ"),
            (",", None),
            ("возможно", "ADVB"),
            (",", None),
            ("Мария", "NOUN"),
            ("ушла", "VERB"),
            (".", None),
        ),
    )
    a1 = _assertion("A1", "пришёл", "Иван", "Иван пришёл", text)
    a2 = _assertion("A2", "ушла", "Мария", "Мария ушла", text)
    root = PropositionRootCandidate(
        "F1",
        PropositionExprCandidate(
            PropositionOperator.AND,
            members=(
                PropositionExprCandidate.ref_expr("A1"),
                PropositionExprCandidate.ref_expr("A2"),
            ),
        ),
    )

    def probe(stage: str, prompt: str, choices: tuple[str, ...]) -> str:
        if stage == "modal_operator":
            return "POSSIBLE"
        if stage == "modal_scope":
            for line in prompt.splitlines():
                if line.endswith(": A2"):
                    label = line.split(":", 1)[0]
                    assert label in choices
                    return label
            raise AssertionError(prompt)
        raise AssertionError(stage)

    result = ModalScopeBuilder(graph, probe).build(
        text,
        (a1, a2),
        {"A1": _Span(2, 2), "A2": _Span(8, 8)},
        (root,),
    )
    assert result.unresolved is None
    assert _render(result.roots[0].expression) == "AND(A1,POSSIBLE(A2))"


def test_leading_modal_can_take_scope_over_complete_and_formula() -> None:
    text = "Возможно, Иван пришёл и Мария ушла."
    graph = _graph(
        text,
        (
            ("Возможно", "PRED"),
            (",", None),
            ("Иван", "NOUN"),
            ("пришёл", "VERB"),
            ("и", "CONJ"),
            ("Мария", "NOUN"),
            ("ушла", "VERB"),
            (".", None),
        ),
    )
    a1 = _assertion("A1", "пришёл", "Иван", "Иван пришёл", text)
    a2 = _assertion("A2", "ушла", "Мария", "Мария ушла", text)
    root = PropositionRootCandidate(
        "F1",
        PropositionExprCandidate(
            PropositionOperator.AND,
            members=(
                PropositionExprCandidate.ref_expr("A1"),
                PropositionExprCandidate.ref_expr("A2"),
            ),
        ),
    )

    def probe(stage: str, prompt: str, choices: tuple[str, ...]) -> str:
        if stage == "modal_operator":
            return "POSSIBLE"
        if stage == "modal_scope":
            for line in prompt.splitlines():
                if line.endswith(": AND(A1,A2)"):
                    label = line.split(":", 1)[0]
                    assert label in choices
                    return label
            raise AssertionError(prompt)
        raise AssertionError(stage)

    result = ModalScopeBuilder(graph, probe).build(
        text,
        (a1, a2),
        {"A1": _Span(4, 4), "A2": _Span(7, 7)},
        (root,),
    )
    assert _render(result.roots[0].expression) == "POSSIBLE(AND(A1,A2))"


def test_nonmodal_adverb_does_not_create_modal_formula() -> None:
    text = "Вчера сервер работал."
    graph = _graph(
        text,
        (
            ("Вчера", "ADVB"),
            ("сервер", "NOUN"),
            ("работал", "VERB"),
            (".", None),
        ),
    )
    assertion = _assertion(
        "A1", "работал", "сервер", "сервер работал", text
    )
    calls = []

    def probe(stage: str, _prompt: str, _choices: tuple[str, ...]) -> str:
        calls.append(stage)
        return "NONE"

    result = ModalScopeBuilder(graph, probe).build(
        text, (assertion,), {"A1": _Span(3, 3)}
    )
    assert result.roots == ()
    assert result.unresolved is None
    assert calls == ["modal_operator"]


def test_modal_operator_unclear_fails_closed() -> None:
    text = "Вероятно, сервер работает."
    graph = _graph(
        text,
        (
            ("Вероятно", "ADVB"),
            (",", None),
            ("сервер", "NOUN"),
            ("работает", "VERB"),
            (".", None),
        ),
    )
    assertion = _assertion(
        "A1", "работает", "сервер", "сервер работает", text
    )
    result = ModalScopeBuilder(
        graph, lambda *_args: "UNCLEAR"
    ).build(text, (assertion,), {"A1": _Span(4, 4)})
    assert result.roots == ()
    assert result.unresolved is not None
    assert "modal operator unresolved" in result.unresolved


def test_modal_wrapper_preserves_local_not() -> None:
    text = "Возможно, Иван не придёт."
    graph = _graph(
        text,
        (
            ("Возможно", "PRED"),
            (",", None),
            ("Иван", "NOUN"),
            ("не", "PRCL"),
            ("придёт", "VERB"),
            (".", None),
        ),
    )
    assertion = _assertion(
        "A1", "придёт", "Иван", "Иван не придёт", text, negated=True
    )
    result = ModalScopeBuilder(
        graph, lambda stage, *_args: "POSSIBLE" if stage == "modal_operator" else "UNCLEAR"
    ).build(text, (assertion,), {"A1": _Span(5, 5)})
    assert result.unresolved is None
    assert _render(result.roots[0].expression) == "POSSIBLE(NOT(A1))"


def test_asserted_modal_wrapper_never_proves_its_operand() -> None:
    core, context, service, engine = _env()
    text = "Возможно, сервер работает."
    assertion = _assertion(
        "A1", "работает", "сервер", "сервер работает", text
    )
    root = PropositionRootCandidate(
        "F_MODAL_1",
        PropositionExprCandidate(
            PropositionOperator.POSSIBLE,
            members=(PropositionExprCandidate.ref_expr("A1"),),
        ),
    )
    commit = service.integrate_external(
        PerceptionResult(
            text,
            assertions=(assertion,),
            proposition_roots=(root,),
        ),
        context,
    )
    assert len(commit.formulas) == 1
    modal_ref = commit.formulas[0].ref
    modal = core.store.get_element_any_domain(modal_ref.uid)
    assert isinstance(modal, FunctionSymbol)
    assert modal.function_id == "POSSIBLE"
    assert _solve(engine, modal_ref).status is LogicalStatus.PROVED

    leaf = commit.assertions[0].ref
    node = core.store.get_hypernode(leaf.uid)
    assert node.meta.get("semantic_scope") == "LOGICAL"
    assert int(node.meta.get("occurrence_count", 0)) == 0
    assert _solve(engine, leaf).status is LogicalStatus.UNKNOWN


def test_required_and_permitted_are_equally_nonfactive() -> None:
    core, context, service, engine = _env()
    for operator in (
        PropositionOperator.REQUIRED,
        PropositionOperator.PERMITTED,
    ):
        text = f"{operator.value}: сервер работает."
        assertion = _assertion(
            "A1", "работает", "сервер", "сервер работает", text
        )
        root = PropositionRootCandidate(
            "F_MODAL_1",
            PropositionExprCandidate(
                operator,
                members=(PropositionExprCandidate.ref_expr("A1"),),
            ),
        )
        commit = service.integrate_external(
            PerceptionResult(
                text,
                assertions=(assertion,),
                proposition_roots=(root,),
            ),
            context,
        )
        assert _solve(engine, commit.formulas[0].ref).status is LogicalStatus.PROVED
        assert _solve(engine, commit.assertions[0].ref).status is LogicalStatus.UNKNOWN
