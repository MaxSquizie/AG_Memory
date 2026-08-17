from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"
TUNING = PROJECT / "src/ah/gui/ignition_tuning.py"


class GUIRuntimeControlsV029Tests(unittest.TestCase):
    def test_full_canvas_mode_hides_and_restores_docks(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn('QAction("Полный canvas"', source)
        self.assertIn('setShortcut("F11")', source)
        self.assertIn("def _toggle_full_canvas", source)
        self.assertIn("dock.hide()", source)
        self.assertIn("dock.show()", source)

    def test_selected_node_manual_seed_is_exposed(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn("def _seed_selected_node", source)
        self.assertIn("self.services.ignition.seed(ref, amount)", source)
        self.assertIn("self.services.config.ignition.seeds.reactivated_fact", source)
        self.assertIn("self.services.ignition.tick()", source)

    def test_reactivation_threshold_is_a_third_hot_slider(self) -> None:
        source = TUNING.read_text(encoding="utf-8")
        self.assertIn("Порог сильной реактивации", source)
        self.assertIn("self.reactivation_slider.setRange(0, 1000)", source)
        self.assertIn("decay.reactivation_min_input", source)
        self.assertIn("Сильный импульс S", source)
        self.assertIn("self.symbol_slider.setRange(0, 1000)", source)
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IgnitionTuningWidget")
        assigns = [n for n in cls.body if isinstance(n, ast.Assign)]
        signal_calls = {
            target.id: node.value
            for node in assigns
            for target in node.targets
            if isinstance(target, ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "Signal"
        }
        self.assertEqual(len(signal_calls["tuning_changed"].args), 4)
        self.assertEqual(len(signal_calls["tuning_committed"].args), 4)


if __name__ == "__main__":
    unittest.main()
