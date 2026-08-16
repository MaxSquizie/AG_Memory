from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PROJECT / "src/ah/gui/main_window.py"


class AcceptanceCanvasRenderTests(unittest.TestCase):
    def _method_calls(self, name: str) -> set[str]:
        tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        )
        calls: set[str] = set()
        for node in ast.walk(method):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                calls.add(func.attr)
            elif isinstance(func, ast.Name):
                calls.add(func.id)
        return calls

    def test_acceptance_does_not_disable_live_canvas_updates(self) -> None:
        suspend_calls = self._method_calls("_suspend_acceptance_status_polling")
        resume_calls = self._method_calls("_resume_acceptance_status_polling")
        self.assertNotIn("set_live_updates_enabled", suspend_calls)
        self.assertNotIn("set_live_updates_enabled", resume_calls)
        self.assertIn("stop", suspend_calls)
        self.assertIn("refresh", resume_calls)
        self.assertIn("start", resume_calls)


if __name__ == "__main__":
    unittest.main()
