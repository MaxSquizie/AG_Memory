from __future__ import annotations

from types import SimpleNamespace

import pytest

from ah.model import ActantRole
from ah.perception import LLMPerceptionService
from ah.perception.adaptive_parser import AdaptiveParseError
from ah.perception.contracts import ActantCandidate, AssertionCandidate, PredicateCandidate
from ah.perception.higher_order_queries import (
    HigherOrderQueryAdaptiveParser,
    HigherOrderQueryLLMPerceptionService,
)
from ah.perception.semantic_predicates import SemanticPredicateAdaptiveParser


def _unresolved(*args, **kwargs):
    raise AdaptiveParseError("requested role unresolved: что")


def _parser(monkeypatch, decision: str):
    parser = object.__new__(HigherOrderQueryAdaptiveParser)
    parser._traces = []
    monkeypatch.setattr(
        SemanticPredicateAdaptiveParser,
        "_requested_query_roles",
        _unresolved,
    )
    monkeypatch.setattr(
        HigherOrderQueryAdaptiveParser,
        "_requested_query_spans",
        lambda self, text, tokens, predicate_span=None: (SimpleNamespace(text="что"),),
    )
    monkeypatch.setattr(
        HigherOrderQueryAdaptiveParser,
        "_deep_semantic_choice_probe",
        lambda self, stage, prompt, choices: (decision, ()),
    )
    monkeypatch.setattr(
        HigherOrderQueryAdaptiveParser,
        "_deterministic_trace",
        lambda self, stage, prompt, answer: None,
    )
    return parser


def _binary_assertion() -> AssertionCandidate:
    return AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate("есть", normalized_hint="быть"),
        actants=(
            # Deliberately plausible local roles that are wrong for possession.
            ActantCandidate(ActantRole.SOURCE, mention="ворона"),
            ActantCandidate(ActantRole.STATE, mention="лапки"),
        ),
    )


def test_production_perception_uses_higher_order_query_layer() -> None:
    assert LLMPerceptionService is HigherOrderQueryLLMPerceptionService


def test_binary_frame_can_correct_provisional_roles_top_down(monkeypatch) -> None:
    parser = object.__new__(HigherOrderQueryAdaptiveParser)
    parser._traces = []
    monkeypatch.setattr(
        HigherOrderQueryAdaptiveParser,
        "_deep_semantic_choice_probe",
        lambda self, stage, prompt, choices: ("E1_HAS_E2", ()),
    )

    rewritten, changed = parser._normalize_predicate_semantics(
        "У вороны есть лапки",
        _binary_assertion(),
    )

    assert changed
    assert rewritten.predicate.normalized_hint == "иметь"
    assert rewritten.predicate.sense_hint == "POSSESSION"
    assert tuple(item.role for item in rewritten.actants) == (
        ActantRole.SUBJECT,
        ActantRole.OBJECT,
    )
    assert tuple(item.mention for item in rewritten.actants) == ("ворона", "лапки")


def test_binary_frame_orientation_is_semantic_not_source_order(monkeypatch) -> None:
    parser = object.__new__(HigherOrderQueryAdaptiveParser)
    parser._traces = []
    monkeypatch.setattr(
        HigherOrderQueryAdaptiveParser,
        "_deep_semantic_choice_probe",
        lambda self, stage, prompt, choices: ("E2_HAS_E1", ()),
    )

    rewritten, changed = parser._normalize_predicate_semantics(
        "Лапки есть у вороны",
        _binary_assertion(),
    )

    assert changed
    assert tuple(item.role for item in rewritten.actants) == (
        ActantRole.OBJECT,
        ActantRole.SUBJECT,
    )


def test_unresolved_wh_can_commit_late_to_relation_description(monkeypatch) -> None:
    parser = _parser(monkeypatch, "RELATION_DESCRIPTION")

    roles, spans = parser._requested_query_roles(
        "Что общего между вороной и столом?",
        (),
        SimpleNamespace(surface="быть"),
        None,
        used_roles={ActantRole.SUBJECT, ActantRole.OBJECT},
    )

    assert roles == (ActantRole.STATE,)
    assert tuple(item.text for item in spans) == ("что",)


def test_late_commitment_does_not_rewrite_ordinary_argument_gap(monkeypatch) -> None:
    parser = _parser(monkeypatch, "ARGUMENT_GAP")

    with pytest.raises(AdaptiveParseError, match="requested role unresolved"):
        parser._requested_query_roles(
            "Что связывает первый объект со вторым?",
            (),
            SimpleNamespace(surface="связывает"),
            None,
            used_roles={ActantRole.SUBJECT, ActantRole.OBJECT},
        )


def test_late_commitment_requires_two_already_filled_participants(monkeypatch) -> None:
    parser = _parser(monkeypatch, "RELATION_DESCRIPTION")

    with pytest.raises(AdaptiveParseError, match="requested role unresolved"):
        parser._requested_query_roles(
            "Что увидел наблюдатель?",
            (),
            SimpleNamespace(surface="увидел"),
            None,
            used_roles={ActantRole.SUBJECT},
        )
