from __future__ import annotations

from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"
LLM = PROJECT / "src/ah/gui/llm_panel.py"
ALL_NODES = PROJECT / "src/ah/gui/all_nodes_viewer.py"
WORKSPACE = PROJECT / "src/ah/gui/workspace_viewer.py"
ARCH = PROJECT / "docs/reference/Архитектура_v3.md"


class GUIDiagnosticPerformanceV036Tests(unittest.TestCase):
    def test_text_diagnostics_poll_at_one_hz_and_hidden_docks_are_lazy(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("start(1000)"), 2)
        self.assertIn("self.workspace_dock.isVisible()", source)
        self.assertIn("self.all_nodes_dock.isVisible()", source)
        self.assertIn("self.llm_dock.isVisible()", source)
        self.assertIn("self.canvas.current_snapshot", source)

    def test_large_text_views_do_not_copy_their_document_on_every_poll(self) -> None:
        source = LLM.read_text(encoding="utf-8")
        self.assertIn('view.property("ah_last_plain_text")', source)
        self.assertNotIn("text == view.toPlainText()", source)
        self.assertIn("self.tabs.currentWidget()", source)
        self.assertIn("current is self.requests_view", source)
        self.assertIn("truncated in Requests tab; exact Agent prompt has its own tabs", source)

    def test_all_nodes_reuses_semantics_and_existing_table_items(self) -> None:
        source = ALL_NODES.read_text(encoding="utf-8")
        self.assertIn("def missing_semantic_uids", source)
        self.assertIn("self._semantic_cache", source)
        self.assertIn("same_membership", source)
        self.assertIn("Fast path", source)
        self.assertNotIn("ResizeMode.ResizeToContents", source)

    def test_live_tables_avoid_resize_to_contents(self) -> None:
        self.assertNotIn("ResizeMode.ResizeToContents", WORKSPACE.read_text(encoding="utf-8"))

    def test_architecture_reference_is_the_user_v04_specification(self) -> None:
        source = ARCH.read_text(encoding="utf-8")
        self.assertIn("спецификация v0.4", source)
        self.assertIn("Diagnostics / UID Trace", source)
        self.assertNotIn("спецификация v0.40", source)


if __name__ == "__main__":
    unittest.main()
