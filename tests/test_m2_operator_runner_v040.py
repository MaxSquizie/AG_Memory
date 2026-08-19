from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ah.cli import build_parser
from ah.config import IgnitionSettings, LifecycleSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import IgnitionInferenceAttention
from ah.model import Domain, Property
from ah.diagnostics import run_m2_attention_acceptance


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"
ARCH = PROJECT / "docs/reference/Архитектура_v3.md"


class M2OperatorRunnerV041Tests(unittest.TestCase):
    def test_operator_runner_uses_dirty_150k_ah_real_attention_and_persists_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = run_m2_attention_acceptance(data_dir=Path(td))

            self.assertEqual(result.total, 40)
            self.assertEqual(result.passed, 40)
            self.assertEqual(result.failed, 0)
            self.assertGreaterEqual(result.ah_uids, 150_000)
            self.assertEqual(result.initial_workspace_count, 0)
            self.assertGreater(result.final_workspace_count, 0)
            self.assertTrue((result.output_dir / "result.json").is_file())
            self.assertTrue((result.output_dir / "report.txt").is_file())

            relations = {case.relation for case in result.cases}
            self.assertTrue({"CAUSE", "FOLLOW", "IS-A"}.issubset(relations))
            self.assertTrue(any("→" in relation for relation in relations))
            self.assertTrue(any(
                case.relation == "CAUSE→FOLLOW→IS-A" and case.goal_depth == 6
                for case in result.cases
            ))
            depths = {case.goal_depth for case in result.cases if case.scenario == "cause_alpha"}
            self.assertEqual(depths, {1, 2, 3, 4, 5, 6})

            for case in result.cases:
                self.assertTrue(case.passed, case.diagnostics)
                self.assertTrue(case.path_cold_before)
                self.assertTrue(case.excitation_changed)
                self.assertTrue(case.path_excited_after)
                if "→" not in case.relation:
                    self.assertTrue(case.tail_inactive_after)
                self.assertTrue(case.tail_absent_from_trace)
                self.assertTrue(case.foreign_absent_from_trace)
                self.assertTrue(case.foreign_absent_from_attention)
                self.assertEqual(case.logical_depth, case.goal_depth)
                self.assertEqual(case.trace_uids, case.expected_trace_uids)
                self.assertEqual(
                    case.attention_focus_uids,
                    case.expected_attention_focus_uids,
                )


    def test_live_warm_snapshot_is_used_without_mutating_live_ah(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        warm = core.add_entity(
            Domain.P,
            properties={"name": Property("name", "already-active", "str")},
        )
        ignition = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(gc_enabled=False, orphan_cleanup=False),
        )
        attention = IgnitionInferenceAttention(ignition)
        attention.focus(core.ref(warm.uid), logical_depth=0)

        uids_before = core.store.all_uids()
        x_before = {uid: core.store.runtime_state(uid).excitation for uid in uids_before}
        workspace_before = ignition.workspace_refs()

        with tempfile.TemporaryDirectory() as td:
            result = run_m2_attention_acceptance(
                data_dir=Path(td),
                base_core=core,
                base_ignition=ignition,
                minimum_ah_uids=5_000,
            )

        self.assertEqual(result.base_mode, "live-AH-snapshot")
        self.assertGreater(result.initial_workspace_count, 0)
        self.assertEqual(result.failed, 0)
        self.assertEqual(core.store.all_uids(), uids_before)
        self.assertEqual(
            {uid: core.store.runtime_state(uid).excitation for uid in uids_before},
            x_before,
        )
        self.assertEqual(ignition.workspace_refs(), workspace_before)

    def test_gui_exposes_attention_m2_launcher_using_current_ah_snapshot(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn('QPushButton("M2: inference attention")', source)
        self.assertIn("def _run_m2_acceptance", source)
        self.assertIn("run_m2_attention_acceptance", source)
        self.assertIn("base_core=self.services.core", source)
        self.assertIn("base_ignition=self.services.ignition", source)
        self.assertIn("LLM не использовалась", source)
        self.assertIn("CanvasBrowserWidget", source)
        self.assertIn("set_sandbox_snapshot", source)
        self.assertIn('QDockWidget("Логический вывод"', source)

    def test_cli_exposes_same_m2_runner(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["m2-acceptance"])
        self.assertEqual(args.command, "m2-acceptance")

    def test_reference_architecture_is_user_v04_not_obsolete_v040_isolation_patch(self) -> None:
        source = ARCH.read_text(encoding="utf-8")
        self.assertIn("спецификация v0.4", source)
        self.assertIn("Reasoner может переходить к неактивным элементам", source)
        self.assertNotIn("fresh isolated AH", source)
        self.assertNotIn("спецификация v0.40", source)


if __name__ == "__main__":
    unittest.main()
