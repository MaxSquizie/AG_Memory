from __future__ import annotations

from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"


class GUIScreenFitV063Tests(unittest.TestCase):
    def test_initial_window_is_capped_to_available_screen(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn("def _fit_initial_window_to_screen", source)
        self.assertIn("QGuiApplication.primaryScreen()", source)
        self.assertIn("screen.availableGeometry()", source)
        self.assertIn("min(1580", source)
        self.assertIn("min(980", source)
        self.assertNotIn('self.resize(1580, 980)\n\n        self.canvas', source)

    def test_chat_dock_has_layout_scroll_and_flexible_input_height(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn("self.chat_scroll = QScrollArea()", source)
        self.assertIn("ScrollBarAsNeeded", source)
        self.assertIn("self.chat_scroll.setWidget(body)", source)
        self.assertIn("self.chat_input.setMinimumHeight(48)", source)
        self.assertIn("self.chat_input.setMaximumHeight(90)", source)
        self.assertNotIn("self.chat_input.setFixedHeight(90)", source)


if __name__ == "__main__":
    unittest.main()
