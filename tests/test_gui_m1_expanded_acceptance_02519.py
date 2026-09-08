from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "ah" / "gui" / "main_window.py"


def test_inversion_and_typo_buttons_use_dedicated_acceptance_pairs() -> None:
    source = MAIN.read_text(encoding="utf-8")
    expected = (
        ('QPushButton("M1: inversion acceptance")', "_run_m1_inversion_acceptance"),
        ('QPushButton("M1: typo/noise acceptance")', "_run_m1_typo_acceptance"),
    )
    for label, handler in expected:
        assert label in source
        assert f"clicked.connect(self.{handler})" in source
    assert 'cases_filename="acceptance_inversion/cases.txt"' in source
    assert 'oracle_filename="acceptance_inversion/oracle.json"' in source
    assert 'runs_dirname="acceptance_runs_m1_inversion"' in source
    assert 'cases_filename="acceptance_typo/cases.txt"' in source
    assert 'oracle_filename="acceptance_typo/oracle.json"' in source
    assert 'runs_dirname="acceptance_runs_m1_typo"' in source


def test_all_m1_buttons_share_busy_state_and_follow_configured_data_dir() -> None:
    source = MAIN.read_text(encoding="utf-8")
    for name in ("adversarial", "inversion", "ellipsis", "typo"):
        assert source.count(f"self.m1_{name}_button.setEnabled(False)") == 4
        assert source.count(f"self.m1_{name}_button.setEnabled(True)") == 4
    for folder in ("acceptance_inversion", "acceptance_ellipsis", "acceptance_typo"):
        assert f'new_config.paths.data_dir / "{folder}" / "cases.txt"' in source
        assert f'new_config.paths.data_dir / "{folder}" / "oracle.json"' in source

