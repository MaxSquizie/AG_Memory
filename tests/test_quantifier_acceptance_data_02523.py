from __future__ import annotations

import json
from pathlib import Path

from ah.cli import build_parser
from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import (
    load_semantic_oracle,
    validate_oracle_alignment,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_quantifiers" / "cases.txt"
ORACLE = ROOT / "data" / "acceptance_quantifiers" / "oracle.json"


def test_quantifier_acceptance_is_aligned_and_covers_semantic_frontier() -> None:
    cases = load_acceptance_cases(CASES)
    oracle = load_semantic_oracle(ORACLE)
    validate_oracle_alignment(cases, oracle)
    assert len(cases) == 78
    assert all(item.grade == "EXACT" for item in oracle)

    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert payload["case_count"] == len(cases)
    kinds: set[str] = set()
    roles: set[str] = set()
    families: set[str] = set()
    fail_closed = 0
    for item in payload["cases"]:
        families.add(item["family"])
        perception = item["expect"]["perception"]
        if not perception.get("must_parse", True):
            fail_closed += 1
            assert item["expect"]["integration"]["must_succeed"] is False
            continue
        assertion = perception["assertions"][0]
        quantified = [
            (role, target["quantifier"])
            for role, target in assertion["roles"].items()
            if isinstance(target, dict) and "quantifier" in target
        ]
        assert len(quantified) == 1
        role, quantifier = quantified[0]
        roles.add(role)
        kinds.add(quantifier["kind"])
        integrated = item["expect"]["integration"]["quantifiers"]
        assert len(integrated) == 1
        assert integrated[0]["kind"] == quantifier["kind"]
        assert integrated[0]["members"] == ["a1"]

    assert kinds == {"EXISTS", "NOT_EXISTS", "FORALL", "NOT_FORALL"}
    assert {
        "SUBJECT",
        "OBJECT",
        "RECIPIENT",
        "LOCATION",
        "TIME",
        "TOOL",
        "SOURCE",
        "MATERIAL",
        "AUXILLIARY",
    }.issubset(roles)
    assert {"inversion_scope", "body_negation", "ambiguous_scope"}.issubset(
        families
    )
    assert fail_closed == 1


def test_acceptance_sentences_are_not_a_production_quantifier_dictionary() -> None:
    algorithm = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (
            ROOT / "src" / "ah" / "perception",
            ROOT / "src" / "ah" / "integration",
        )
        for path in base.rglob("*.py")
    ).casefold()
    assert "acceptance_quantifiers" not in algorithm
    for sentence in (item.text for item in load_acceptance_cases(CASES)):
        assert sentence.casefold() not in algorithm


def test_quantifier_acceptance_is_bound_to_cli_gui_and_metrics_history() -> None:
    args = build_parser().parse_args(["quantifier-acceptance"])
    assert args.command == "quantifier-acceptance"

    window_source = (ROOT / "src" / "ah" / "gui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert 'cases_filename="acceptance_quantifiers/cases.txt"' in window_source
    assert 'oracle_filename="acceptance_quantifiers/oracle.json"' in window_source
    assert 'runs_dirname="acceptance_runs_m1_quantifiers"' in window_source
    assert "_run_m1_quantifier_acceptance" in window_source

    metrics_source = (ROOT / "src" / "ah" / "gui" / "metrics_panel.py").read_text(
        encoding="utf-8"
    )
    assert '"Quantifiers": "acceptance_runs_m1_quantifiers"' in metrics_source
