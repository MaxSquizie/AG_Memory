from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import ContextSettings, IgnitionSettings, LifecycleSettings, WorkspaceSettings
from ah.core import AHCore
from ah.ignition import IgnitionEngine
from ah.model import Domain, Property
from ah.projection import ContextProjector


PROJECT = Path(__file__).resolve().parents[1]
LLM_PANEL = PROJECT / "src/ah/gui/llm_panel.py"
BACKEND = PROJECT / "src/ah/llm/process_backend.py"


class AgentInputVisibilityV035Tests(unittest.TestCase):
    def test_projection_diagnostic_explains_workspace_without_leaking_into_model_context(self) -> None:
        core = AHCore()
        entity = core.add_entity(
            Domain.P,
            {"name": Property("name", "Миша", "str")},
        )
        engine = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(gc_enabled=False),
        )
        engine.seed(core.ref(entity.uid), 0.8)
        engine.tick()
        workspace = engine.workspace_refs()
        projector = ContextProjector(core, ContextSettings())
        context = projector.project("Как зовут моего друга?", workspace, ())
        diagnostic = projector.diagnose(
            context,
            tick_index=engine.tick_index,
            workspace_threshold=engine.workspace_settings.threshold,
        )

        self.assertIn("# ACTIVE MEMORY", context.rendered)
        self.assertIn("Миша", context.rendered)
        self.assertNotIn("0.800000", context.rendered)
        self.assertNotIn("Workspace rule", context.rendered)
        self.assertEqual(diagnostic.tick_index, engine.tick_index)
        self.assertEqual(diagnostic.workspace_threshold, 0.35)
        self.assertEqual(len(diagnostic.workspace), 1)
        row = diagnostic.workspace[0]
        self.assertEqual(row.root.uid, entity.uid)
        self.assertGreater(row.excitation, 0.35)
        self.assertIn("Миша", row.semantic)
        self.assertNotEqual(row.semantic, context.workspace_blocks[0].semantic)
        self.assertIn("Связанная сущность: Миша", context.workspace_blocks[0].semantic)

    def test_gui_exposes_model_visible_context_memory_and_final_prompt_as_separate_tabs(self) -> None:
        source = LLM_PANEL.read_text(encoding="utf-8")
        self.assertIn('"Agent CONTEXT"', source)
        self.assertIn('"Memory INPUT"', source)
        self.assertIn('"Agent FINAL prompt"', source)
        self.assertIn("MODEL-VISIBLE MEMORY PAYLOAD", source)
        self.assertIn("DEBUG EXPLANATION (NOT sent to Agent LLM)", source)
        self.assertIn("active_request_diagnostic", source)

    def test_backend_keeps_in_flight_request_payload_for_live_gui_inspection(self) -> None:
        source = BACKEND.read_text(encoding="utf-8")
        self.assertIn("class LLMActiveRequestDiagnostic", source)
        self.assertIn("def active_request_diagnostic", source)
        self.assertIn("self._active_request = LLMActiveRequestDiagnostic", source)


if __name__ == "__main__":
    unittest.main()
