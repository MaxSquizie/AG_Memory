from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "ah" / "gui" / "main_window.py"
TUNING = ROOT / "src" / "ah" / "gui" / "ignition_tuning.py"


def _source(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    ast.parse(text)
    return text


def test_inspect_and_runtime_are_replaced_by_one_monitor_mode() -> None:
    text = _source(MAIN)
    assert '"monitor",' in text and '"MONITOR",' in text
    assert '("inspect", "INSPECT"' not in text
    assert '("runtime", "RUNTIME"' not in text
    assert '"monitor": "Режим MONITOR: Inspector и Runtime видны одновременно"' in text


def test_monitor_keeps_live_inspector_and_runtime_surfaces_visible_together() -> None:
    text = _source(MAIN)
    body = text[text.index("def _arrange_monitor_workspace"):text.index("def resizeEvent")]
    for dock in (
        "self.inspector_dock",
        "self.workspace_dock",
        "self.runtime_dock",
        "self.llm_dock",
        "self.chat_dock",
    ):
        assert dock in body
    assert "self.splitDockWidget(self.inspector_dock, self.workspace_dock" in body
    assert "self.splitDockWidget(self.runtime_dock, self.llm_dock" in body


def test_monitor_has_responsive_breakpoints_and_only_reflows_on_class_change() -> None:
    text = _source(MAIN)
    assert 'return "wide"' in text
    assert 'return "normal"' in text
    assert 'return "compact"' in text
    assert "width >= 2300" in text
    assert "width >= 1600" in text
    assert "layout_class == self._monitor_layout_class" in text
    assert "def resizeEvent" in text
    assert 'if self._workspace_mode == "monitor"' in text


def test_auxiliary_browse_and_config_are_tabbed_on_nonwide_displays() -> None:
    text = _source(MAIN)
    body = text[text.index("def _arrange_monitor_workspace"):text.index("def resizeEvent")]
    assert "self.tabifyDockWidget(self.workspace_dock, self.all_nodes_dock)" in body
    assert "self.tabifyDockWidget(self.llm_dock, self.config_dock)" in body
    assert 'if layout_class == "wide"' in body


def test_runtime_tuning_and_import_do_not_consume_height_simultaneously() -> None:
    text = _source(TUNING)
    assert "self.sections = QTabWidget()" in text
    assert 'self.sections.addTab(parameters_page, "Параметры")' in text
    assert 'self.sections.addTab(import_box, "Импорт")' in text


def test_llm_panel_collapses_secondary_metadata_in_monitor_mode() -> None:
    main = _source(MAIN)
    llm = _source(ROOT / "src" / "ah" / "gui" / "llm_panel.py")
    assert 'self.llm_panel.set_monitor_compact(mode == "monitor")' in main
    assert "def set_monitor_compact" in llm
    for field in (
        "self.role_label", "self.loader_label", "self.device_policy_label",
        "self.history_label", "self.perception_cfg_label", "self.agent_cfg_label",
    ):
        assert field in llm
    assert "self.info_layout.labelForField(field)" in llm
