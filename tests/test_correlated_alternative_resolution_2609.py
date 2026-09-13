from __future__ import annotations

from pathlib import Path

import pytest

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    LLMPerceptionSettings,
    PerceptionParseError,
    PerceptionResult,
    PredicateCandidate,
)
from ah.perception.correlated_alternatives import CorrelatedAlternativeLLMPerceptionService


ROOT = Path(__file__).resolve().parents[1]


class _Backend:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        del system, override
        self.calls.append((role, prompt))
        assert role == "semantic_correlated_frame"
        return LLMResponse(self.answer, {})


def _service(answer: str) -> CorrelatedAlternativeLLMPerceptionService:
    return CorrelatedAlternativeLLMPerceptionService(
        _Backend(answer),
        LLMPerceptionSettings(
            protocol="adaptive_v3",
            probe_prompt_dir=ROOT / "prompts" / "perception",
            probe_retry_attempts=0,
            generation=LLMRoleSettings(max_new_tokens=8, temperature=0.0),
            morphology_backend="none",
        ),
    )


def _act(role: ActantRole, text: str, entity_ref: str) -> ActantCandidate:
    return ActantCandidate(role, mention=text, entity_ref=entity_ref)


def _correlated() -> AssertionCandidate:
    predicate = PredicateCandidate("положила", "положить")
    first = AssertionCandidate(
        "A2",
        predicate,
        (
            _act(ActantRole.SUBJECT, "Она", "E_OLGA"),
            _act(ActantRole.OBJECT, "её", "E_BOOK"),
            _act(ActantRole.LOCATION, "на стол", "E_TABLE"),
        ),
    )
    second = AssertionCandidate(
        "A2",
        predicate,
        (
            _act(ActantRole.SUBJECT, "Она", "E_BOOK"),
            _act(ActantRole.OBJECT, "её", "E_OLGA"),
            _act(ActantRole.LOCATION, "на стол", "E_TABLE"),
        ),
    )
    return AssertionCandidate(
        "A2",
        predicate,
        first.actants,
        alternatives=(first, second),
    )


def test_correlated_choice_selects_one_complete_frame_without_role_cross_product() -> None:
    service = _service("A1")
    source = "Ольга взяла книгу. Она положила её на стол."
    result = service._resolve_correlated_alternatives(
        source,
        PerceptionResult(source, assertions=(_correlated(),)),
    )

    assertion = result.assertions[0]
    assert assertion.alternatives == ()
    assert [(a.role, a.entity_ref) for a in assertion.actants] == [
        (ActantRole.SUBJECT, "E_OLGA"),
        (ActantRole.OBJECT, "E_BOOK"),
        (ActantRole.LOCATION, "E_TABLE"),
    ]
    backend = service.backend
    assert len(backend.calls) == 1
    assert "A1:" in backend.calls[0][1] and "A2:" in backend.calls[0][1]


def test_correlated_unknown_remains_fail_closed() -> None:
    service = _service("UNKNOWN")
    source = "Она положила её на стол."
    with pytest.raises(PerceptionParseError, match="remain semantically unresolved"):
        service._resolve_correlated_alternatives(
            source,
            PerceptionResult(source, assertions=(_correlated(),)),
        )


def test_one_role_ambiguity_stays_for_canonical_ambiguity_group() -> None:
    predicate = PredicateCandidate("видит", "видеть")
    first = AssertionCandidate(
        "A1",
        predicate,
        (_act(ActantRole.SUBJECT, "Анна", "E_ANNA"), _act(ActantRole.OBJECT, "её", "E_OLGA")),
    )
    second = AssertionCandidate(
        "A1",
        predicate,
        (_act(ActantRole.SUBJECT, "Анна", "E_ANNA"), _act(ActantRole.OBJECT, "её", "E_MARIA")),
    )
    candidate = AssertionCandidate(
        "A1", predicate, first.actants, alternatives=(first, second)
    )
    service = _service("A1")
    result = service._resolve_correlated_alternatives(
        "Анна видит её.", PerceptionResult("Анна видит её.", assertions=(candidate,))
    )
    assert result.assertions[0].alternatives == (first, second)
    assert service.backend.calls == []
