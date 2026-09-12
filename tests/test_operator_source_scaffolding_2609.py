from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.diagnostics.semantic_oracle import _semantic_grading_record
from ah.integration import CandidateValidator, IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, FunctionSymbol, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
    TemplateCandidate,
)


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


def test_candidate_ref_content_is_valid_for_consumed_operator_source() -> None:
    result = _perception()
    CandidateValidator().validate(result)
    # Validation is projection-only: it must not rewrite the actual perception.
    source = result.assertions[0]
    assert source.actants[0].candidate_ref == "A2"
    assert source.actants[0].proposition is None


def test_consumed_operator_source_is_not_integrated_as_world_fact() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))

    commit = service.integrate_external(_perception(), context)
    assert [item.local_id for item in commit.assertions] == ["A2"]
    assert len(commit.formulas) == 1
    formula = core.store.get_element_any_domain(commit.formulas[0].ref.uid)
    assert isinstance(formula, FunctionSymbol)
    assert formula.function_id == "REQUIRED"


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
