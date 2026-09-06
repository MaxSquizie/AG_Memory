from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"


class GUIM1AdversarialAcceptanceV0251Tests(unittest.TestCase):
    def test_dedicated_button_is_bound_to_m1_adversarial_pair(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn('QPushButton("M1: adversarial acceptance")', source)
        self.assertIn(
            "self.m1_adversarial_button.clicked.connect(self._run_m1_adversarial_acceptance)",
            source,
        )
        self.assertIn('cases_filename="acceptance_cases_m1_adversarial.txt"', source)
        self.assertIn('oracle_filename="acceptance_oracle_m1_adversarial.json"', source)
        self.assertIn('runs_dirname="acceptance_runs_m1_adversarial"', source)

    def test_standard_and_adversarial_buttons_share_the_real_acceptance_runner(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        tree = ast.parse(source)
        main = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
        )
        names = {node.name for node in main.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertIn("_run_acceptance_pair", names)
        self.assertIn("_run_acceptance_cases", names)
        self.assertIn("_run_m1_adversarial_acceptance", names)
        self.assertIn("return run_acceptance_suite(", source)
        self.assertIn("runs_dirname=runs_dirname", source)

    def test_tooltip_follows_configured_data_dir(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertGreaterEqual(
            source.count('new_config.paths.data_dir / "acceptance_cases_m1_adversarial.txt"'),
            1,
        )
        self.assertGreaterEqual(
            source.count('new_config.paths.data_dir / "acceptance_oracle_m1_adversarial.json"'),
            1,
        )


if __name__ == "__main__":
    unittest.main()
