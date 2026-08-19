from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.diagnostics import ProofSnapshotBuilder, run_m2_attention_acceptance
from ah.inference import GoalSpec, InferenceEngine, InferenceQuery, RelationGoal
from ah.model import Domain, Property


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"
EXPLORER = PROJECT / "src/ah/gui/inference_explorer.py"
CANVAS = PROJECT / "src/ah/gui/graph_canvas.py"


class InferenceProofExplorerV060Tests(unittest.TestCase):
    def test_transitive_proof_has_human_semantic_steps(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        dog = core.add_entity(Domain.C, {"name": Property("name", "Собака", "str")})
        mammal = core.add_entity(Domain.C, {"name": Property("name", "Млекопитающее", "str")})
        animal = core.add_entity(Domain.C, {"name": Property("name", "Животное", "str")})
        first = core.add_link("IS-A", core.ref(dog.uid), core.ref(mammal.uid), 0.4)
        second = core.add_link("IS-A", core.ref(mammal.uid), core.ref(animal.uid), 0.4)
        outcome = InferenceEngine(
            core, InferenceSettings(max_depth=6, max_expanded_states=100)
        ).solve(
            InferenceQuery(
                GoalSpec(RelationGoal("IS-A", core.ref(dog.uid), core.ref(animal.uid)))
            )
        )

        proof = ProofSnapshotBuilder(core).build(
            outcome, chain_id="test", source="LIVE", title="taxonomy"
        )
        self.assertEqual(proof.logical_depth, 2)
        self.assertEqual([edge.uid for edge in proof.edges], [first.uid, second.uid])
        self.assertEqual([step.rule for step in proof.steps], ["IS-A / DIRECT", "IS-A / TRANSITIVITY"])
        rendered = proof.semantic_text()
        self.assertIn("Собака IS-A Животное", rendered)
        self.assertIn("по транзитивности", rendered)
        self.assertIn("Заключение", rendered)

    def test_m2_cases_carry_semantic_proof_and_explicit_checks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = run_m2_attention_acceptance(
                data_dir=Path(td), minimum_ah_uids=2_000
            )
            self.assertEqual(result.failed, 0)
            self.assertEqual(result.total, 40)
            for case in result.cases:
                self.assertIsNotNone(case.proof)
                proof = case.proof
                assert proof is not None
                self.assertEqual(len(proof.steps), case.goal_depth)
                self.assertTrue(proof.goal_text)
                self.assertTrue(proof.conclusion_text)
                names = {check.name for check in proof.checks}
                self.assertIn("exact UID trace", names)
                self.assertIn("trace stops at Goal", names)
                self.assertTrue(all(check.passed for check in proof.checks), case.scenario)

            report = (result.output_dir / "report.txt").read_text(encoding="utf-8")
            self.assertIn("step 1", report)
            self.assertIn("checks:", report)
            self.assertIn("goal:", report)

    def test_gui_has_modeless_proof_explorer_and_live_canvas_overlay(self) -> None:
        main = MAIN.read_text(encoding="utf-8")
        explorer = EXPLORER.read_text(encoding="utf-8")
        canvas = CANVAS.read_text(encoding="utf-8")
        self.assertIn('QAction("Логический вывод"', main)
        self.assertIn("ProofSnapshotBuilder(self.services.core)", main)
        self.assertIn("case.proof", main)
        self.assertIn("class InferenceExplorerWidget", explorer)
        self.assertIn("Цель / остановка", explorer)
        self.assertIn("Семантика / логика", explorer)
        self.assertIn("Проверки M2", explorer)
        self.assertIn("UID trace", explorer)
        self.assertIn("class ProofCanvasView", explorer)
        self.assertIn("def set_proof_highlight", canvas)
        self.assertIn("def clear_proof_highlight", canvas)
        self.assertIn('QDockWidget("Логический вывод"', main)
        self.assertIn("CanvasBrowserWidget", main)


if __name__ == "__main__":
    unittest.main()
