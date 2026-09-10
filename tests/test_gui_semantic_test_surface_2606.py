from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "ah" / "gui"


def test_production_gui_uses_semantic_test_window() -> None:
    app = (GUI / "app.py").read_text(encoding="utf-8")
    assert "from ah.gui.semantic_test_window import MainWindow" in app
    assert "from ah.gui.main_window import MainWindow" not in app


def test_semantic_test_surface_has_current_semantic_suites_only() -> None:
    source = (GUI / "semantic_test_window.py").read_text(encoding="utf-8")

    # Text -> semantic oracle suites.
    for token in (
        "acceptance_cases.txt",
        "acceptance_cases_m1_adversarial.txt",
        "acceptance_inversion/cases.txt",
        "acceptance_ellipsis/cases.txt",
        "acceptance_typo/cases.txt",
        "acceptance_logic/cases.txt",
        "acceptance_modal/cases.txt",
    ):
        assert token in source

    # Typed semantic GoalCompiler suites that require canonical-memory fixtures.
    for token in (
        "test_quantified_goal_compiler_2605.py",
        "test_counterfactual_goal_compiler_2605.py",
        "test_association_goal_compiler_2606.py",
    ):
        assert token in source

    # These are deliberately not runnable choices in the semantic selector.
    assert '"document_acceptance",' not in source
    assert '"m2_acceptance",' not in source
    assert '"m3_gc",' not in source


def test_obsolete_chat_and_metric_test_launchers_are_hidden() -> None:
    source = (GUI / "semantic_test_window.py").read_text(encoding="utf-8")
    for attribute in (
        "document_acceptance_button",
        "m2_acceptance_button",
    ):
        assert f'"{attribute}"' in source
    for label in (
        "Запустить M2 acceptance",
        "Запустить M3 GC acceptance",
    ):
        assert label in source


def test_goalcompiler_targets_exist() -> None:
    targets = (
        "tests/test_quantified_goal_acceptance_2605.py",
        "tests/test_quantified_goal_compiler_2605.py",
        "tests/test_counterfactual_goal_acceptance_2605.py",
        "tests/test_counterfactual_goal_compiler_2605.py",
        "tests/test_association_goal_acceptance_2606.py",
        "tests/test_association_goal_compiler_2606.py",
        "tests/test_association_goal_guards_2606.py",
    )
    for target in targets:
        assert (ROOT / target).is_file(), target
