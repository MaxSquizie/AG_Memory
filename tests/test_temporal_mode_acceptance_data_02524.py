from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ah.cli import build_parser
from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import (
    load_semantic_oracle,
    validate_oracle_alignment,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_temporal_modes" / "cases.txt"
ORACLE = ROOT / "data" / "acceptance_temporal_modes" / "oracle.json"


def test_temporal_mode_acceptance_is_exact_aligned_and_balanced() -> None:
    cases = load_acceptance_cases(CASES)
    oracle = load_semantic_oracle(ORACLE)
    validate_oracle_alignment(cases, oracle)
    assert len(cases) == 46
    assert all(item.grade == "EXACT" for item in oracle)

    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert payload["case_count"] == 46
    families = Counter(item["family"] for item in payload["cases"])
    assert families == {
        "state": 12,
        "process": 12,
        "event": 12,
        "transition": 5,
        "mode_none": 4,
        "ambiguous": 1,
    }

    modes = Counter()
    operators = set()
    temporal_roles = set()
    for item in payload["cases"]:
        perception = item["expect"]["perception"]
        if not perception.get("must_parse", True):
            assert item["expect"]["integration"]["must_succeed"] is False
            continue
        assertion = perception["assertions"][0]
        modes[assertion.get("temporal_mode")] += 1
        operator = assertion.get("transition_operator")
        if operator:
            operators.add(operator)
        temporal_roles.update(
            role
            for role in assertion["roles"]
            if role in {"TIME", "DURATION"}
        )
    assert modes == {"STATE": 12, "PROCESS": 12, "EVENT": 12, "TRANSITION": 5, None: 4}
    assert operators == {"START", "STOP", "CONTINUE", "AGAIN", "NO_LONGER"}
    assert temporal_roles == {"TIME", "DURATION"}


def test_acceptance_sentences_are_not_a_production_temporal_dictionary() -> None:
    algorithm = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (
            ROOT / "src" / "ah" / "perception",
            ROOT / "src" / "ah" / "temporal",
            ROOT / "src" / "ah" / "integration",
        )
        for path in base.rglob("*.py")
    ).casefold()
    assert "acceptance_temporal_modes" not in algorithm
    for case in load_acceptance_cases(CASES):
        assert case.text.casefold() not in algorithm


def test_temporal_mode_acceptance_is_bound_to_cli_gui_and_metrics_history() -> None:
    args = build_parser().parse_args(["temporal-mode-acceptance"])
    assert args.command == "temporal-mode-acceptance"

    window_source = (ROOT / "src" / "ah" / "gui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert 'cases_filename="acceptance_temporal_modes/cases.txt"' in window_source
    assert 'oracle_filename="acceptance_temporal_modes/oracle.json"' in window_source
    assert 'runs_dirname="acceptance_runs_m1_temporal_modes"' in window_source
    assert "_run_m1_temporal_mode_acceptance" in window_source

    metrics_source = (ROOT / "src" / "ah" / "gui" / "metrics_panel.py").read_text(
        encoding="utf-8"
    )
    assert '"Temporal modes": "acceptance_runs_m1_temporal_modes"' in metrics_source
