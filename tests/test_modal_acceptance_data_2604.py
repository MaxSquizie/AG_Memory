from collections import Counter
from pathlib import Path

from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import (
    load_semantic_oracle,
    validate_oracle_alignment,
)


ROOT = Path(__file__).resolve().parents[1]


def _ops(expr):
    if isinstance(expr, str):
        return set()
    if not isinstance(expr, dict):
        return set()
    result = {str(expr.get("op", expr.get("operator", ""))).upper()}
    for child in expr.get("args", expr.get("members", [])) or []:
        result.update(_ops(child))
    result.discard("")
    return result


def test_modal_acceptance_is_exact_aligned_and_has_negative_controls() -> None:
    cases = load_acceptance_cases(
        ROOT / "data" / "acceptance_modal" / "cases.txt"
    )
    oracle = load_semantic_oracle(
        ROOT / "data" / "acceptance_modal" / "oracle.json"
    )
    validate_oracle_alignment(cases, oracle)

    assert len(cases) == len(oracle) == 18
    assert all(item.grade == "EXACT" for item in oracle)
    assert Counter(item.family for item in oracle) == {
        "modal_possible": 3,
        "modal_scope": 3,
        "impersonal_modal": 3,
        "nonmodal_negative": 3,
        "reported_attitude": 4,
        "factivity": 2,
    }

    roots = [
        root
        for item in oracle
        for root in item.expectation["perception"].get(
            "proposition_roots", []
        )
    ]
    operators = set()
    for root in roots:
        operators.update(_ops(root["expr"]))
    assert {"POSSIBLE", "REQUIRED", "PERMITTED", "NOT", "AND", "OR"} <= operators

    negatives = [
        item for item in oracle if item.family == "nonmodal_negative"
    ]
    assert all(
        not item.expectation["perception"].get("proposition_roots")
        for item in negatives
    )


def test_every_modal_formula_is_graded_against_canonical_g_shape() -> None:
    oracle = load_semantic_oracle(
        ROOT / "data" / "acceptance_modal" / "oracle.json"
    )
    modal_families = {"modal_possible", "modal_scope", "impersonal_modal"}
    for item in oracle:
        if item.family not in modal_families:
            continue
        roots = item.expectation["perception"]["proposition_roots"]
        assert len(roots) == 1
        assert item.expectation["integration"]["formulas"] == [
            {"expr": roots[0]["expr"]}
        ]
