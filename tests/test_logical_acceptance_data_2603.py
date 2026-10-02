from collections import Counter
from pathlib import Path

from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import load_semantic_oracle, validate_oracle_alignment


ROOT = Path(__file__).resolve().parents[1]


def _ops(expr):
    if isinstance(expr, str):
        return set()
    if not isinstance(expr, dict):
        return set()
    result = {str(expr.get("op", expr.get("operator", ""))).upper()}
    for item in expr.get("args", expr.get("members", [])) or []:
        result.update(_ops(item))
    result.discard("")
    return result


def test_logical_formalization_corpus_is_exact_aligned_and_operator_complete() -> None:
    cases = load_acceptance_cases(
        ROOT / "data" / "acceptance_logic" / "cases.txt"
    )
    oracle = load_semantic_oracle(
        ROOT / "data" / "acceptance_logic" / "oracle.json"
    )
    validate_oracle_alignment(cases, oracle)

    assert len(cases) == len(oracle) == 33
    assert all(item.grade == "EXACT" for item in oracle)
    assert Counter(item.family for item in oracle) == {
        "and": 4,
        "or": 4,
        "xor": 6,
        "local_not": 6,
        "whole_not": 1,
        "implies": 8,
        "mixed_scope": 4,
    }

    operators = set()
    for item in oracle:
        roots = item.expectation["perception"].get("proposition_roots", [])
        assert len(roots) == 1
        operators.update(_ops(roots[0]["expr"]))
    assert {"AND", "OR", "XOR", "NOT", "IMPLIES"} <= operators


def test_logical_formula_cases_grade_both_perception_ast_and_canonical_shape() -> None:
    oracle = load_semantic_oracle(
        ROOT / "data" / "acceptance_logic" / "oracle.json"
    )
    ordinary = [
        item for item in oracle
        if item.family != "implies"
    ]
    assert ordinary
    for item in ordinary:
        expected = item.expectation
        roots = expected["perception"]["proposition_roots"]
        formulas = expected["integration"].get("formulas")
        assert formulas == [{"expr": roots[0]["expr"]}]
