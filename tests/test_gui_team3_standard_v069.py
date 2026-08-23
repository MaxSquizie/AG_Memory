from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "ah" / "gui"


def _text(name: str) -> str:
    return (GUI / name).read_text(encoding="utf-8")


def test_team3_gui_modules_are_present_and_syntax_valid() -> None:
    for name in ("theme.py", "node_inspector.py", "diagnostics_panel.py"):
        text = _text(name)
        ast.parse(text)
        assert text.strip()


def test_gui_entrypoint_applies_team3_theme() -> None:
    text = _text("app.py")
    assert "from ah.gui.theme import apply_theme" in text
    assert "apply_theme(app)" in text


def test_main_window_uses_team3_inspector_diagnostics_and_workspace_modes() -> None:
    text = _text("main_window.py")
    assert "NodeInspectorWidget" in text
    assert "DiagnosticsPanel" in text
    assert "_build_workspace_mode_menu" in text
    assert 'tabs.addTab(runtime_body, "Runtime")' in text
    assert 'tabs.addTab(self.diagnostics_panel, "Diagnostics")' in text
    for mode in ("graph", "monitor", "edit"):
        assert f'"{mode}",' in text
    assert '"inspect", "INSPECT"' not in text
    assert '"runtime", "RUNTIME"' not in text


def test_link_manager_supports_sequential_canvas_endpoint_picking() -> None:
    text = _text("link_manager.py")
    assert "self.canvas_pick" in text
    assert "def on_canvas_selection" in text
    assert "кликните источник, затем цель" in text


def test_current_provenance_contract_is_preserved_in_audited_gui() -> None:
    text = _text("main_window.py")
    # The audited GUI originally dropped unresolved epistemic goals from the
    # explorer. Our project must keep them visible instead of showing 0 chains.
    assert "build_unresolved(" in text
    assert '"status": "UNRESOLVED"' in text
    assert '"stop_reason": "GOAL_NOT_COMPILED"' in text
    assert "self.inference_explorer.add_chain(proof, select=False)" in text


def test_screen_safe_dialog_contract_remains_present() -> None:
    text = _text("main_window.py")
    assert "availableGeometry()" in text
    assert "QScrollArea" in text
    assert "self.chat_scroll" in text
    assert "setMinimumHeight(48)" in text
    assert "setMaximumHeight(90)" in text


def test_workspace_mode_docks_are_bound_before_mode_application() -> None:
    text = _text("main_window.py")
    # Workspace modes manipulate these QDockWidgets by attribute. The audited
    # GUI originally created three of them only as local variables, so startup
    # crashed as soon as GRAPH mode was applied. Keep every referenced dock
    # strongly bound on MainWindow before _build_workspace_mode_menu().
    for attr in ("config_dock", "node_dock", "link_dock"):
        assert f"self.{attr} = dock" in text

    init_start = text.index("def __init__")
    init_end = text.index("def _fit_initial_window_to_screen", init_start)
    init = text[init_start:init_end]
    menu_pos = init.index("self._build_workspace_mode_menu()")
    for builder in (
        "self._build_config_dock()",
        "self._build_node_manager_dock()",
        "self._build_link_manager_dock()",
        "self._build_runtime_dock()",
    ):
        assert init.index(builder) < menu_pos
