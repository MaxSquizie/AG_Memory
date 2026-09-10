from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "data" / "acceptance_association_goal"
ORACLE = SUITE / "oracle.json"
CASES = SUITE / "cases.txt"


def test_association_goal_oracle_is_exact_and_complete() -> None:
    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["case_count"] == len(payload["cases"]) == 24
    assert payload["policy"]["grade"] == "EXACT"
    ids = [item["id"] for item in payload["cases"]]
    assert len(ids) == len(set(ids))
    assert {
        "direct_question",
        "association_noun_paraphrase",
        "semantic_bridge_command",
        "memory_connection_paraphrase",
        "convergence_paraphrase",
        "polar_surface_association",
        "common_representation_paraphrase",
        "path_paraphrase",
        "intersection_without_association_word",
        "expanded_representation_paraphrase",
        "proposition_endpoints",
        "local_candidate_refs",
        "three_way_request_not_binary",
        "named_relation_query_is_ordinary",
        "ordinary_role_query",
        "comparison_command",
        "ordinary_event_query",
        "negated_association_command",
        "quoted_association_command",
        "quantified_association_not_composed",
        "identical_canonical_origins",
        "unknown_endpoint_no_creation",
        "lexical_symbol_fallback",
        "composition_member_selectors_and_projection",
    } == set(ids)


def test_association_language_corpus_matches_oracle_texts() -> None:
    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    corpus = tuple(
        line.strip()
        for line in CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    assert len(corpus) == 24
    assert corpus == tuple(item["text"] for item in payload["cases"])


def test_association_oracle_keeps_search_separate_from_proof() -> None:
    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    invariants = "\n".join(payload["policy"]["invariants"])
    assert "AssociationCoordinator" in invariants
    assert "InferenceEngine" in invariants
    assert "AgentContext.association_blocks" in invariants
    assert "never through inference_blocks" in invariants
    assert "not entailment" in invariants


def test_association_oracle_covers_fail_closed_and_non_entity_origins() -> None:
    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    edge = {item["id"]: item for item in payload["synthetic_edge_checks"]}
    assert {
        "ambiguous_entity",
        "homographic_symbol",
        "noncanonical_formula",
        "generic_marker_rejected",
        "mixed_relation_marker_rejected",
        "common_node_kinds",
    } == set(edge)
    assert set(edge["common_node_kinds"]["allowed_common_kinds"]) == {
        "S", "M", "T", "N", "G", "K"
    }
