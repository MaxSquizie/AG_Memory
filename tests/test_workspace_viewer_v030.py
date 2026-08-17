from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import IgnitionSettings, LifecycleSettings, WorkspaceSettings
from ah.core import AHCore
from ah.diagnostics import GraphInspector
from ah.ignition import IgnitionEngine
from ah.model import ActantRole, Domain, Property


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"
VIEWER = PROJECT / "src/ah/gui/workspace_viewer.py"


class WorkspaceViewerV030Tests(unittest.TestCase):
    def test_workspace_snapshot_contains_active_human_semantics(self) -> None:
        core = AHCore()
        pred = core.add_abstract_symbol({"высказать"})
        user = core.add_entity(
            Domain.P,
            {"name": Property("name", "Пользователь", "str")},
            meta={"identity_role": "USER"},
        )
        template = core.add_template(Domain.H, core.ref(pred.uid), (ActantRole.SUBJECT,))
        event, _ = core.add_hypernode(
            Domain.H,
            core.ref(template.uid),
            {ActantRole.SUBJECT: core.ref(user.uid)},
            0.3,
            properties={"text": Property("text", "Мне нужен интерфейс", "str")},
            meta={"event_instance": True},
        )
        engine = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.2),
            LifecycleSettings(gc_enabled=False),
        )
        engine.seed(core.ref(event.uid), 0.8)
        engine.tick()

        snap = GraphInspector(core, engine).snapshot()

        self.assertIn(event.uid, snap.workspace_uids)
        rendered = snap.workspace_semantics[event.uid]
        self.assertTrue(rendered.startswith("реплика пользователя:"))
        self.assertIn("Мне нужен интерфейс", rendered)
        self.assertNotIn("высказать", rendered)
        self.assertNotIn(event.uid, rendered)

    def test_workspace_is_a_separate_live_dock(self) -> None:
        main_source = MAIN.read_text(encoding="utf-8")
        viewer_source = VIEWER.read_text(encoding="utf-8")
        self.assertIn('QDockWidget("Workspace"', main_source)
        self.assertIn("self.workspace_view.refresh(snap", main_source)
        self.assertIn('"Смысл"', viewer_source)
        self.assertIn('"x"', viewer_source)
        self.assertIn("workspace_semantics", viewer_source)
        self.assertIn("node_selected = Signal(str)", viewer_source)


if __name__ == "__main__":
    unittest.main()
