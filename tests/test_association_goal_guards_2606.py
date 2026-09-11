from __future__ import annotations

from pathlib import Path

import pytest

from ah.integration.candidate_validator import CandidateValidator
from ah.integration.errors import CandidateValidationError
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception import (
    ActRelationCandidate,
    ActantCandidate,
    AssociationActRelationCandidate,
    AssociationSemanticClassifier,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
)


class _Backend:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict[str, object]] = []

    def generate(self, prompt: str, *, system: str = "", override=None, role: str = "generic"):
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "override": dict(override or {}),
                "role": role,
            }
        )
        return LLMResponse(self.answer, {})


def _query() -> QueryCandidate:
    return QueryCandidate(
        PredicateCandidate("connect"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="fire", normalized_hint="fire"),
            ActantCandidate(ActantRole.OBJECT, mention="smoke", normalized_hint="smoke"),
        ),
        local_id="Q1",
    )


def test_association_probe_is_bounded_uid_free_and_non_thinking() -> None:
    backend = _Backend("ASSOCIATION:E1:E2")
    prompt_dir = Path(__file__).resolve().parents[1] / "prompts" / "perception"
    classifier = AssociationSemanticClassifier(backend, prompt_dir, retry_attempts=0)

    decision, attempts = classifier.classify("What connects fire and smoke?", _query())

    assert decision is not None
    assert decision.left.role is ActantRole.SUBJECT
    assert decision.right.role is ActantRole.OBJECT
    assert len(attempts) == 1
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call["role"] == "semantic_association_query"
    override = call["override"]
    assert isinstance(override, dict)
    assert override["temperature"] == 0.0
    assert override["enable_thinking"] is False
    assert "ASSOCIATION:E1:E2" in str(call["prompt"])
    assert "UID" not in str(call["prompt"]).upper()


def test_association_and_world_relation_cannot_compete_by_relation_order() -> None:
    query = _query()
    association = AssociationActRelationCandidate(
        "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
    )
    world_relation = ActRelationCandidate(
        "IS-A", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
    )
    for relations in ((association, world_relation), (world_relation, association)):
        perception = PerceptionResult(
            "mixed operation",
            queries=(query,),
            act_relations=relations,
        )
        with pytest.raises(CandidateValidationError, match="cannot share one act"):
            CandidateValidator().validate(perception)
