from types import SimpleNamespace

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.diagnostics.semantic_oracle import _semantic_grading_record
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.candidate_validator import CandidateValidator
from ah.model import ActantRole, Domain, FunctionSymbol, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
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


def _perception() -> PerceptionResult:
    child = AssertionCandidate(
        "A2",
        PredicateCandidate(
            "работать",
            "работать",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention="сервер"),),
        status=AssertionStatus.EMBEDDED,
    )
    # The adaptive parser can carry the matrix->content edge as candidate_ref until
    # logical/modal formalization consumes the matrix as a source operator.
    source = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "необходимо",
            "необходимо",
            template_candidate=TemplateCandidate((ActantRole.OBJECT,)),
        ),
        (ActantCandidate(ActantRole.OBJECT, candidate_ref="A2"),),
    )
    root = PropositionRootCandidate(
        "F1",
        PropositionExprCandidate(
            PropositionOperator.REQUIRED,
            members=(PropositionExprCandidate.ref_expr("A2"),),
        ),
        operator_source_refs=("A1",),
    )
    return PerceptionResult(
        "Необходимо, чтобы сервер работал.",
        assertions=(source, child),
        proposition_roots=(root,),
    )


def _runtime() -> tuple[AHCore, InteractionContext, IntegrationService]:
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    return core, context, IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))


def _assertion(
    local_id: str,
    predicate: str,
    subject: str,
    source: str,
    evidence_text: str,
) -> AssertionCandidate:
    start = source.index(evidence_text)
    predicate_start = source.index(predicate, start, start + len(evidence_text))
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            evidence=EvidenceSpan(
                predicate, predicate_start, predicate_start + len(predicate)
            ),
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention=subject),),
        evidence=EvidenceSpan(evidence_text, start, start + len(evidence_text)),
    )


def _detached_operator_case():
    text = "Ровно одно из двух: Иван придёт или Мария позвонит."
    preamble = _assertion("A0", "одно", "ровно", text, "Ровно одно из двух")
    left = _assertion("A1", "придёт", "Иван", text, "Иван придёт")
    right = _assertion("A2", "позвонит", "Мария", text, "Мария позвонит")
    graph = LinguisticCandidateGraph(
        text,
        (),
        (
            ClauseCandidate(
                "CL1",
                0,
                CandidateSpan(1, 3, text, EvidenceSpan(text, 0, len(text))),
                (),
            ),
        ),
        (),
        (),
    )
    spans = {
        "A0": SimpleNamespace(start_index=1, end_index=1),
        "A1": SimpleNamespace(start_index=2, end_index=2),
        "A2": SimpleNamespace(start_index=3, end_index=3),
    }
    return text, graph, (preamble, left, right), spans


def test_candidate_ref_content_is_valid_for_consumed_operator_source() -> None:
    result = _perception()
    CandidateValidator().validate(result)
    # Validation is projection-only: it must not rewrite the actual perception.
    source = result.assertions[0]
    assert source.actants[0].candidate_ref == "A2"
    assert source.actants[0].proposition is None


def test_consumed_operator_source_is_not_integrated_as_world_fact() -> None:
    core, context, service = _runtime()
    commit = service.integrate_external(_perception(), context)
    assert [item.local_id for item in commit.assertions] == ["A2"]
    assert len(commit.formulas) == 1
    formula = core.store.get_element_any_domain(commit.formulas[0].ref.uid)
    assert isinstance(formula, FunctionSymbol)
    assert formula.function_id == "REQUIRED"


def test_detached_preamble_is_bound_to_formula_without_phrase_dictionary() -> None:
    text, graph, assertions, spans = _detached_operator_case()
    calls: list[str] = []

    def probe(stage: str, _prompt: str, _choices: tuple[str, ...]) -> str:
        calls.append(stage)
        if stage == "logical_relation":
            # A0 is a parser frame for the preamble, not a proposition connected
            # truth-functionally to A1.  This leaves A0 available as source material.
            return "NONE"
        if stage == "logical_or_exclusivity":
            return "EXCLUSIVE"
        if stage == "logical_operator_source":
            return "OPERATOR_SOURCE"
        raise AssertionError(stage)

    result = LogicalFormBuilder(graph, probe).build(text, assertions, spans)
    assert result.unresolved is None
    assert len(result.roots) == 1
    root = result.roots[0]
    assert root.expression.operator is PropositionOperator.XOR
    assert root.expression.leaf_refs() == ("A1", "A2")
    assert root.operator_source_refs == ("A0",)
    assert calls == [
        "logical_relation",
        "logical_or_exclusivity",
        "logical_operator_source",
    ]


def test_detached_operator_source_validates_and_never_becomes_world_fact() -> None:
    text, graph, assertions, spans = _detached_operator_case()

    def probe(stage: str, _prompt: str, _choices: tuple[str, ...]) -> str:
        if stage == "logical_relation":
            return "NONE"
        if stage == "logical_or_exclusivity":
            return "EXCLUSIVE"
        if stage == "logical_operator_source":
            return "OPERATOR_SOURCE"
        raise AssertionError(stage)

    logical = LogicalFormBuilder(graph, probe).build(text, assertions, spans)
    perception = PerceptionResult(
        text,
        assertions=assertions,
        proposition_roots=logical.roots,
    )
    CandidateValidator().validate(perception)

    core, context, service = _runtime()
    commit = service.integrate_external(perception, context)
    assert {item.local_id for item in commit.assertions} == {"A1", "A2"}
    assert all(item.local_id != "A0" for item in commit.assertions)
    assert len(commit.formulas) == 1
    formula = core.store.get_element_any_domain(commit.formulas[0].ref.uid)
    assert isinstance(formula, FunctionSymbol)
    assert formula.function_id == "XOR"


def test_semantic_grading_projects_operator_source_without_mutating_record() -> None:
    record = {
        "status": "OK",
        "perception_result": {
            "assertions": [
                {"local_id": "A1", "predicate": {"surface": "необходимо"}},
                {"local_id": "A2", "predicate": {"surface": "работать"}},
            ],
            "proposition_roots": [
                {
                    "local_id": "F1",
                    "expression": {
                        "operator": "REQUIRED",
                        "members": [{"operator": "REF", "ref": "A2"}],
                    },
                    "operator_source_refs": ["A1"],
                }
            ],
        },
    }
    projected, sources = _semantic_grading_record(record)
    assert sources == frozenset({"A1"})
    assert [item["local_id"] for item in projected["perception_result"]["assertions"]] == ["A2"]
    assert projected["perception_result"]["proposition_roots"][0]["operator_source_refs"] == []
    assert record["perception_result"]["assertions"][0]["local_id"] == "A1"
    assert record["perception_result"]["proposition_roots"][0]["operator_source_refs"] == ["A1"]
