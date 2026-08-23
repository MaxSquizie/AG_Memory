from __future__ import annotations

from pathlib import Path

from ah.diagnostics.document_acceptance import (
    _compiled_bundle,
    evaluate_document_graph,
    load_document_specs,
)
from ah.diagnostics.semantic_oracle import load_semantic_oracle
from ah.diagnostics.acceptance_runner import load_acceptance_cases


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_manual_document_suite_has_three_strict_documents_and_three_literary_monoliths(tmp_path: Path) -> None:
    specs = load_document_specs(DATA)
    assert [item.document_id for item in specs] == [
        "cooling_station",
        "greenhouse_control",
        "archive_leak",
        "house_by_pier_monolith",
        "belyaev_amphibian_mutiny",
        "old_observatory_monolith",
    ]
    assert [item.ingest_mode for item in specs] == [
        "paragraphs", "paragraphs", "paragraphs", "monolith", "monolith", "monolith"
    ]
    assert sum(len(item.paragraphs) for item in specs[:3]) == 21
    assert len(specs[3].paragraphs) == 15
    assert len(specs[4].paragraphs) == 45
    assert len(specs[5].paragraphs) == 17
    assert all("\n\n" not in item.source_text.strip() for item in specs[3:])
    assert sum(len(item.m2_questions) for item in specs) == 14
    # The public-domain literary excerpt is intentionally not rewritten into
    # explicit causal training prose. Its oracle therefore tests narrative
    # causality without relying on the connective used by the synthetic docs.
    assert "потому что" not in specs[4].source_text.casefold()


def test_compiled_document_bundle_reuses_existing_semantic_oracle_contract(tmp_path: Path) -> None:
    specs = load_document_specs(DATA)
    cases_file, oracle_file = _compiled_bundle(specs, tmp_path)
    cases = load_acceptance_cases(cases_file)
    oracle = load_semantic_oracle(oracle_file)
    assert len(cases) == 98
    assert len(oracle) == 98
    assert [item.text for item in cases] == [item.text for item in oracle]
    assert {item.scenario_id for item in oracle} == {
        "cooling_station",
        "greenhouse_control",
        "archive_leak",
        "house_by_pier_monolith",
        "belyaev_amphibian_mutiny",
        "old_observatory_monolith",
    }


def _fixture_snapshot() -> dict[str, dict]:
    return {
        "S_LOW": {"uid": "S_LOW", "kind": "S", "domain": None, "forms": ["опуститься"]},
        "S_FREEZE": {"uid": "S_FREEZE", "kind": "S", "domain": None, "forms": ["замёрзнуть"]},
        "T_LOW": {"uid": "T_LOW", "kind": "T", "domain": "C", "predicate": {"kind": "S", "uid": "S_LOW"}, "roles": ["SUBJECT"]},
        "T_FREEZE": {"uid": "T_FREEZE", "kind": "T", "domain": "C", "predicate": {"kind": "S", "uid": "S_FREEZE"}, "roles": ["SUBJECT"]},
        "M_TEMP": {"uid": "M_TEMP", "kind": "M", "domain": "C", "properties": {"name": {"value": "температура"}}, "meta": {}},
        "M_WATER": {"uid": "M_WATER", "kind": "M", "domain": "C", "properties": {"name": {"value": "вода"}}, "meta": {}},
        "N_LOW": {"uid": "N_LOW", "kind": "N", "domain": "C", "template": {"kind": "T", "uid": "T_LOW"}, "actants": {"SUBJECT": {"kind": "M", "uid": "M_TEMP"}}},
        "N_FREEZE": {"uid": "N_FREEZE", "kind": "N", "domain": "C", "template": {"kind": "T", "uid": "T_FREEZE"}, "actants": {"SUBJECT": {"kind": "M", "uid": "M_WATER"}}},
        "L_CAUSE": {"uid": "L_CAUSE", "kind": "L", "domain": None, "relation_id": "CAUSE", "source": {"kind": "N", "uid": "N_LOW"}, "target": {"kind": "N", "uid": "N_FREEZE"}},
    }


def test_document_graph_oracle_matches_fact_identity_and_causal_edge() -> None:
    expectation = {
        "facts": [
            {"id": "low", "predicate": "опуститься", "roles": {"SUBJECT": "температура"}},
            {"id": "freeze", "predicate": "замёрзнуть", "roles": {"SUBJECT": "вода"}},
        ],
        "links": [{"relation": "CAUSE", "source": "low", "target": "freeze"}],
        "forbidden_links": [{"relation": "CAUSE", "source": "freeze", "target": "low"}],
        "min_cause_depth": 1,
    }
    checks, matched = evaluate_document_graph(_fixture_snapshot(), expectation)
    assert matched == {"low": "N_LOW", "freeze": "N_FREEZE"}
    assert checks
    assert all(item["ok"] for item in checks)


def test_document_graph_oracle_fails_when_causal_direction_is_wrong() -> None:
    snapshot = _fixture_snapshot()
    snapshot["L_CAUSE"] = {
        **snapshot["L_CAUSE"],
        "source": {"kind": "N", "uid": "N_FREEZE"},
        "target": {"kind": "N", "uid": "N_LOW"},
    }
    expectation = {
        "facts": [
            {"id": "low", "predicate": "опуститься", "roles": {"SUBJECT": "температура"}},
            {"id": "freeze", "predicate": "замёрзнуть", "roles": {"SUBJECT": "вода"}},
        ],
        "links": [{"relation": "CAUSE", "source": "low", "target": "freeze"}],
        "min_cause_depth": 1,
    }
    checks, _ = evaluate_document_graph(snapshot, expectation)
    failed = {item["name"] for item in checks if not item["ok"]}
    assert "link.CAUSE.low->freeze" in failed
    assert "cause_chain.minimum_depth" in failed


def test_future_m2_paths_are_explicit_and_relation_typed() -> None:
    specs = load_document_specs(DATA)
    for spec in specs:
        fact_ids = {str(item["id"]) for item in spec.final_expectation.get("facts", [])}
        for question in spec.m2_questions:
            path = [str(item) for item in question["path"]]
            relations = [str(item).upper() for item in question["relations"]]
            assert len(path) >= 2
            assert len(relations) == len(path) - 1
            assert set(path).issubset(fact_ids)
            assert set(relations).issubset({"CAUSE", "FOLLOW", "IS-A"})


def test_literary_monolith_is_split_only_into_bounded_sentence_windows() -> None:
    specs = load_document_specs(DATA)
    spec = next(item for item in specs if item.document_id == "house_by_pier_monolith")
    assert spec.ingest_mode == "monolith"
    assert len(spec.paragraphs) == 15
    assert all(unit.text.count(".") == 2 for unit in spec.paragraphs)
    reconstructed = " ".join(unit.text for unit in spec.paragraphs)
    normalized_source = " ".join(spec.source_text.split())
    assert reconstructed == normalized_source
    assert all(unit.expectation["perception"].get("unchecked") is True for unit in spec.paragraphs)
    assert spec.final_expectation.get("min_cause_depth") == 6


def test_literary_monolith_has_handwritten_typed_m2_path_depth_six() -> None:
    specs = load_document_specs(DATA)
    spec = next(item for item in specs if item.document_id == "house_by_pier_monolith")
    deep = max(spec.m2_questions, key=lambda item: len(item["relations"]))
    assert deep["path"] == [
        "branch_touch",
        "gutter_shift",
        "water_go",
        "beam_wet",
        "beam_swell",
        "frame_warp",
        "window_jam",
    ]
    assert deep["relations"] == ["CAUSE"] * 6


def test_public_domain_belyaev_monolith_keeps_real_prose_and_manual_oracle() -> None:
    specs = load_document_specs(DATA)
    spec = next(item for item in specs if item.document_id == "belyaev_amphibian_mutiny")
    assert spec.ingest_mode == "monolith"
    assert len(spec.paragraphs) == 45
    assert all(unit.expectation["perception"].get("unchecked") is True for unit in spec.paragraphs)
    assert "потому что" not in spec.source_text.casefold()
    assert "Зурита" in spec.source_text and "Ихтиандр" in spec.source_text
    assert spec.final_expectation.get("min_cause_depth") == 2
    deep = max(spec.m2_questions, key=lambda item: len(item["relations"]))
    assert deep["path"] == ["sailor_grab", "zurita_hit", "grabber_fall"]
    assert deep["relations"] == ["CAUSE", "CAUSE"]


def test_monolith_sentence_splitter_handles_new_dialogue_turn_after_terminal_punctuation() -> None:
    from ah.diagnostics.document_acceptance import _split_monolith_sentences

    parts = _split_monolith_sentences(
        "Он спросил: — Ты идёшь? — Да, — ответила она. — Тогда идём!"
    )
    assert parts == (
        "Он спросил: — Ты идёшь?",
        "— Да, — ответила она.",
        "— Тогда идём!",
    )


def test_second_handwritten_literary_monolith_targets_event_normalization_and_subjective_scope() -> None:
    specs = load_document_specs(DATA)
    spec = next(item for item in specs if item.document_id == "old_observatory_monolith")
    assert spec.ingest_mode == "monolith"
    assert len(spec.paragraphs) == 17
    assert "потому что" not in spec.source_text.casefold()
    assert "Отперев" in spec.source_text
    assert "Зажёгши" in spec.source_text
    assert "Увидев дым" in spec.source_text
    assert "Ей показалось" in spec.source_text
    assert all(unit.expectation["perception"].get("unchecked") is True for unit in spec.paragraphs)
    forbidden = spec.final_expectation.get("forbidden_facts") or []
    assert {item["id"] for item in forbidden} == {
        "imagined_walk_as_world", "imagined_stop_as_world"
    }
    assert all(item.get("semantic_scope") == "ASSERTED" for item in forbidden)


def test_document_graph_oracle_can_forbid_an_asserted_world_fact_while_allowing_embedded_content() -> None:
    snapshot = _fixture_snapshot()
    # Extend the fixture with an embedded proposition. It is canonical content but
    # must not satisfy a forbidden ASSERTED-world-fact specification.
    snapshot.update({
        "S_WALK": {"uid": "S_WALK", "kind": "S", "domain": None, "forms": ["пройти"]},
        "T_WALK": {"uid": "T_WALK", "kind": "T", "domain": "C", "predicate": {"kind": "S", "uid": "S_WALK"}, "roles": ["SUBJECT"]},
        "M_SOMEONE": {"uid": "M_SOMEONE", "kind": "M", "domain": "C", "properties": {"name": {"value": "кто-то"}}, "meta": {}},
        "N_WALK": {"uid": "N_WALK", "kind": "N", "domain": "C", "template": {"kind": "T", "uid": "T_WALK"}, "actants": {"SUBJECT": {"kind": "M", "uid": "M_SOMEONE"}}, "meta": {"semantic_scope": "EMBEDDED"}},
    })
    expectation = {
        "facts": [],
        "forbidden_facts": [
            {"id": "walk_world", "predicate": "пройти", "domain": "C", "semantic_scope": "ASSERTED", "exact_roles": False, "roles": {"SUBJECT": "кто-то"}}
        ],
    }
    checks, _ = evaluate_document_graph(snapshot, expectation)
    assert checks == ({
        "name": "forbidden_fact.walk_world",
        "ok": True,
        "expected": False,
        "actual": {"matched_uid": None, "candidates": []},
    },)
