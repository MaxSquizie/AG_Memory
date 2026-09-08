from collections import Counter
from pathlib import Path

from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import load_semantic_oracle, validate_oracle_alignment


ROOT = Path(__file__).resolve().parents[1]


def test_dedicated_inversion_corpus_is_aligned_and_role_rich() -> None:
    cases = load_acceptance_cases(ROOT / "data" / "acceptance_inversion" / "cases.txt")
    oracle = load_semantic_oracle(ROOT / "data" / "acceptance_inversion" / "oracle.json")
    validate_oracle_alignment(cases, oracle)
    assert len(cases) == len(oracle) == 100
    assert all(item.grade == "EXACT" for item in oracle)
    assert Counter(item.family for item in oracle) == {
        "object_fronting": 15,
        "recipient_scrambling": 15,
        "location_scrambling": 15,
        "tool_material_source": 15,
        "time_duration_scrambling": 15,
        "predicate_initial": 10,
        "multi_actant_permutation": 10,
        "coordination_inversion": 5,
    }
    roles = {
        role
        for item in oracle
        for assertion in item.expectation["perception"]["assertions"]
        for role in assertion["roles"]
    }
    assert {
        "SUBJECT", "OBJECT", "RECIPIENT", "LOCATION", "TOOL", "MATERIAL",
        "SOURCE", "TIME", "DURATION",
    } <= roles


def test_imported_expansion_keeps_all_old_ellipsis_cases_and_adds_frontiers() -> None:
    oracle = load_semantic_oracle(ROOT / "data" / "acceptance_ellipsis" / "oracle.json")
    assert len(oracle) == 166
    families = Counter(item.family for item in oracle)
    assert families["inversion_ellipsis"] == 12
    assert families["punctuation_noise_ellipsis"] == 12
    assert families["scope_control_ellipsis"] == 12
    assert families["ellipsis_boundary_guard"] == 6
