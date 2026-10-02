from __future__ import annotations

import pytest

from ah.model import ActantRole
from ah.perception.association_goal_semantics import AssociationGoalSemanticService
from ah.perception.association_semantics import (
    AssociationProbeAttempt,
    AssociationProbeError,
)
from ah.perception.contracts import (
    ActantCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
)
from ah.perception.llm_parser import PerceptionParseError


class _UnknownAssociationClassifier:
    def classify_association_query(self, source_text: str, act: QueryCandidate):
        del source_text, act
        cause = AssociationProbeError(
            "association query intent/endpoints are semantically unresolved",
            (
                AssociationProbeAttempt(
                    raw_text="UNKNOWN",
                    normalized_answer="UNKNOWN",
                    error=None,
                    retry_index=0,
                ),
            ),
        )
        raise PerceptionParseError(str(cause)) from cause


class _BrokenAssociationClassifier:
    def classify_association_query(self, source_text: str, act: QueryCandidate):
        del source_text, act
        cause = AssociationProbeError(
            "association semantic probe backend failed",
            (
                AssociationProbeAttempt(
                    raw_text="",
                    normalized_answer=None,
                    error="backend:RuntimeError:offline",
                    retry_index=0,
                ),
            ),
        )
        raise PerceptionParseError(str(cause)) from cause


def _ordinary_fill_role_query() -> PerceptionResult:
    query = QueryCandidate(
        PredicateCandidate("подарить", normalized_hint="подарить"),
        (
            ActantCandidate(
                ActantRole.RECIPIENT,
                mention="Марии",
                normalized_hint="Мария",
            ),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="книгу",
                normalized_hint="книга",
            ),
        ),
        requested_role=ActantRole.SUBJECT,
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q1",
    )
    return PerceptionResult("Кто подарил Марии книгу?", queries=(query,))


def test_unknown_association_overlay_does_not_destroy_ordinary_fill_role_query() -> None:
    source = _ordinary_fill_role_query()

    completed = AssociationGoalSemanticService(
        _UnknownAssociationClassifier()
    ).complete(source)

    assert completed.queries == source.queries
    assert completed.act_relations == ()


def test_nonsemantic_association_probe_failure_still_propagates() -> None:
    source = _ordinary_fill_role_query()

    with pytest.raises(PerceptionParseError, match="backend failed"):
        AssociationGoalSemanticService(_BrokenAssociationClassifier()).complete(source)
