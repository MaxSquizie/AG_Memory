from __future__ import annotations

import json
from pathlib import Path

from ah.integration import namespace_perception_result
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
    apply_speech_act_scoping,
)
from ah.model import ActantRole


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "data" / "acceptance_counterfactual_goal" / "oracle.json"


def _typed_direct_counterfactual() -> PerceptionResult:
    assumption = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "работать",
            "работать",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention="сервер"),),
        status=AssertionStatus.HYPOTHETICAL,
    )
    query = QueryCandidate(
        PredicateCandidate(
            "отвечать",
            "отвечать",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention="сервис"),),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    return PerceptionResult(
        "Если бы сервер работал, сервис отвечал бы?",
        assertions=(assumption,),
        queries=(query,),
        act_dependencies=(
            ActDependencyCandidate(
                "Q1", "A1", ActDependencyKind.SUBORDINATE
            ),
        ),
    )


def test_counterfactual_goal_oracle_is_exact_and_complete() -> None:
    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["input_boundary"] == (
        "typed HYPOTHETICAL scope + QUERY dependencies"
    )
    assert payload["case_count"] == len(payload["cases"]) == 12
    assert payload["policy"]["grade"] == "EXACT"
    ids = [item["id"] for item in payload["cases"]]
    assert len(ids) == len(set(ids))
    assert {
        "direct_positive_mp",
        "multiple_simultaneous_assumptions",
        "missing_required_assumption",
        "negative_assumption_override",
        "positive_assumption_override",
        "incompatible_assumptions",
        "explicit_embedded_target",
        "nested_hypothetical_content",
        "open_ended_fill_role",
        "structural_relation_target",
        "quoted_hypothesis_edge",
        "ordinary_query_regression",
    } == set(ids)


def test_counterfactual_shadow_survives_real_document_namespace_idempotently() -> None:
    scoped = apply_speech_act_scoping(_typed_direct_counterfactual())
    assert any(
        item.local_id == "Q1:__CF_TARGET__"
        for item in scoped.assertions
    )

    namespaced = namespace_perception_result(scoped, 0)
    assert namespaced.queries[0].local_id == "B0:Q1"
    assert any(
        item.local_id == "B0:Q1:__CF_TARGET__"
        for item in namespaced.assertions
    )

    rescoped = apply_speech_act_scoping(namespaced)
    target_ids = [
        item.local_id
        for item in rescoped.assertions
        if item.local_id.endswith(":__CF_TARGET__")
    ]
    assert target_ids == ["B0:Q1:__CF_TARGET__"]


def test_counterfactual_scoping_uses_typed_status_not_surface_words() -> None:
    typed = _typed_direct_counterfactual()
    # Surface contains no counterfactual lexical marker at all; typed status and
    # dependency topology are sufficient and therefore the result must be identical
    # at the goal-scoping boundary.
    marker_free = PerceptionResult(
        "opaque semantic turn",
        assertions=typed.assertions,
        queries=typed.queries,
        act_dependencies=typed.act_dependencies,
    )
    scoped = apply_speech_act_scoping(marker_free)
    assert any(
        item.local_id == "Q1:__CF_TARGET__"
        for item in scoped.assertions
    )

    # Conversely, marker-looking text without HYPOTHETICAL status is not authority
    # to invent a counterfactual world.
    ordinary_assumption = AssertionCandidate(
        "A1",
        typed.assertions[0].predicate,
        typed.assertions[0].actants,
        status=AssertionStatus.ASSERTED,
    )
    lexical_only = PerceptionResult(
        "если бы сервер работал",
        assertions=(ordinary_assumption,),
        queries=typed.queries,
        act_dependencies=typed.act_dependencies,
    )
    lexical_scoped = apply_speech_act_scoping(lexical_only)
    assert all(
        item.local_id != "Q1:__CF_TARGET__"
        for item in lexical_scoped.assertions
    )
