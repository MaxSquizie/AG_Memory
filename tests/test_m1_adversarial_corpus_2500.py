from __future__ import annotations

from collections import Counter
from pathlib import Path

from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import load_semantic_oracle, validate_oracle_alignment


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_cases_m1_adversarial.txt"
ORACLE = ROOT / "data" / "acceptance_oracle_m1_adversarial.json"


def test_m1_adversarial_corpus_is_aligned_and_exact() -> None:
    cases = load_acceptance_cases(CASES)
    oracle = load_semantic_oracle(ORACLE)
    validate_oracle_alignment(cases, oracle)
    assert len(cases) == 36
    assert len(oracle) == 36
    assert all(item.grade == "EXACT" for item in oracle)


def test_m1_adversarial_corpus_covers_hidden_noise_classes_and_roles() -> None:
    oracle = load_semantic_oracle(ORACLE)
    families = Counter(item.family for item in oracle)
    assert families == {
        "m1_typo_noise": 10,
        "m1_inversion": 10,
        "m1_ellipsis": 10,
        "m1_mixed_noise": 6,
    }
    tags = {tag for item in oracle for tag in item.tags}
    assert {"typo", "inversion", "ellipsis"}.issubset(tags)

    roles = {
        role
        for item in oracle
        for assertion in item.expectation["perception"]["assertions"]
        for role in assertion["roles"]
    }
    # Mandatory hackathon M1 roles plus additional valency pressure.
    assert {"SUBJECT", "OBJECT", "LOCATION"}.issubset(roles)
    assert {"RECIPIENT", "TOOL", "MATERIAL", "TIME", "DURATION", "SOURCE"}.issubset(roles)


def test_ellipsis_family_reconstructs_more_assertions_than_source_predicates() -> None:
    oracle = load_semantic_oracle(ORACLE)
    ellipsis = [item for item in oracle if item.family == "m1_ellipsis"]
    assert ellipsis
    assert all(len(item.expectation["perception"]["assertions"]) == 2 for item in ellipsis)
    assert all("ellipsis" in item.tags for item in ellipsis)
