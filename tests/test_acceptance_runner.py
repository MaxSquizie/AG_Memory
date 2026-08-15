from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import json
import tempfile
import unittest

from ah.core import AHCore
from ah.diagnostics import GraphInspector
from ah.diagnostics.acceptance_runner import (
    canonical_ah_snapshot,
    diff_canonical_ah,
    load_acceptance_cases,
    run_acceptance_suite,
    _runtime_summary,
)
from ah.model import ActantRole, Domain, Property
from ah.perception import PerceptionResult


@dataclass(frozen=True, slots=True)
class _FakeTurn:
    perception: PerceptionResult
    integration: dict
    queries: tuple
    agent_context: dict
    response_text: str
    response_perception: PerceptionResult | None
    response_integration: dict | None


class _FakeOrchestrator:
    def __init__(self, services) -> None:
        self.services = services

    def handle_user_text(self, text: str, *, generate_response: bool = True) -> _FakeTurn:
        if generate_response:
            raise AssertionError("acceptance runner must stop before LLM agent generation")
        # A tiny deterministic mutation makes the exported AH diff observable.
        self.services.core.ensure_abstract_symbol(text)
        return _FakeTurn(
            perception=PerceptionResult(source_text=text),
            integration={"status": "ok"},
            queries=(),
            agent_context={"current_input": text},
            response_text="ok",
            response_perception=None,
            response_integration=None,
        )




class _FakeIgnition:
    def workspace_refs(self):
        return ()

    def export_snapshot(self, *, include_pending: bool = False):
        return SimpleNamespace(
            tick_index=0,
            incoming={},
            pending_refutations=(),
        )


class _FakeServices:
    def __init__(self, data_dir: Path) -> None:
        self.config = SimpleNamespace(
            paths=SimpleNamespace(data_dir=data_dir),
            llm=SimpleNamespace(perception_morphology_backend="none"),
        )
        self.operation_lock = RLock()
        self.core = AHCore()
        self.ignition = _FakeIgnition()
        self.graph_inspector = GraphInspector(self.core)
        self.context = SimpleNamespace(pronoun_refs={})
        self.perception = None
        self.llm = None

    def create_orchestrator(self):
        return _FakeOrchestrator(self)


class AcceptanceRunnerTests(unittest.TestCase):
    def test_cases_file_is_plain_replaceable_one_request_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "acceptance_cases.txt"
            path.write_text("# group\n\nПервый запрос.\n  Второй запрос?  \n", encoding="utf-8")
            cases = load_acceptance_cases(path)
        self.assertEqual([case.text for case in cases], ["Первый запрос.", "Второй запрос?"])
        self.assertEqual([case.index for case in cases], [1, 2])

    def test_canonical_snapshot_and_diff_preserve_template_roles_and_n_filling(self) -> None:
        services = _FakeServices(Path("."))
        before = canonical_ah_snapshot(services)
        predicate = services.core.add_abstract_symbol({"read"}, uid="S_READ")
        person = services.core.add_entity(
            Domain.C, {"name": Property("name", "Иван", "str")}, uid="M_IVAN"
        )
        template = services.core.add_template(
            Domain.C,
            services.core.ref(predicate.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
            uid="T_READ",
        )
        node, _ = services.core.add_hypernode(
            Domain.C,
            services.core.ref(template.uid),
            {ActantRole.SUBJECT: services.core.ref(person.uid)},
            0.4,
            uid="N_READ",
        )
        after = canonical_ah_snapshot(services)
        diff = diff_canonical_ah(before, after)
        self.assertEqual(after[template.uid]["roles"], ["SUBJECT", "OBJECT"])
        self.assertEqual(set(after[node.uid]["actants"]), {"SUBJECT"})
        self.assertIn("T_READ", diff["added"])
        self.assertIn("N_READ", diff["added"])

    def test_runtime_summary_does_not_build_full_graph_snapshot(self) -> None:
        services = _FakeServices(Path("."))

        def forbidden_snapshot():
            raise AssertionError("runtime summary must not build a full GraphInspector snapshot")

        services.graph_inspector.snapshot = forbidden_snapshot  # type: ignore[method-assign]
        summary = _runtime_summary(services)
        self.assertEqual(summary["workspace_uids"], [])
        self.assertEqual(summary["tick"], 0)

    def test_suite_writes_per_turn_diagnostics_and_final_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            cases_file = data_dir / "acceptance_cases.txt"
            cases_file.write_text("Кошка спит.\nИван читает.\n", encoding="utf-8")
            services = _FakeServices(data_dir)

            result = run_acceptance_suite(services, cases_file=cases_file)

            self.assertEqual(result.total, 2)
            self.assertEqual(result.succeeded, 2)
            self.assertEqual(result.failed, 0)
            self.assertTrue((result.output_dir / "cases_used.txt").is_file())
            self.assertTrue((result.output_dir / "config.json").is_file())
            self.assertTrue((result.output_dir / "initial_context.json").is_file())
            self.assertTrue((result.output_dir / "initial_ah.json").is_file())
            self.assertTrue((result.output_dir / "final_context.json").is_file())
            self.assertTrue((result.output_dir / "final_ah.json").is_file())
            self.assertTrue((result.output_dir / "final_graph.json").is_file())
            self.assertTrue((result.output_dir / "manifest.json").is_file())
            self.assertTrue((result.output_dir / "summary.txt").is_file())

            turn = json.loads((result.output_dir / "turn_001.json").read_text(encoding="utf-8"))
            self.assertEqual(turn["input"], "Кошка спит.")
            self.assertEqual(turn["status"], "OK")
            self.assertIn("linguistic_candidate_graph", turn)
            self.assertIn("perception_result", turn)
            self.assertIn("ah_diff", turn)
            self.assertTrue(turn["agent_generation_skipped"])
            self.assertIsNone(turn["agent_response"])
            self.assertIn("interaction_context_after", turn)
            self.assertTrue(turn["ah_diff"]["added"])
            self.assertEqual(
                (data_dir / "acceptance_runs" / "latest.txt").read_text(encoding="utf-8").strip(),
                str(result.output_dir.resolve()),
            )


if __name__ == "__main__":
    unittest.main()
