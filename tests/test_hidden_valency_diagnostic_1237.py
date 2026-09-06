from __future__ import annotations

from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import re
import tempfile
import unittest

from ah.config import LLMRoleSettings
from ah.core import AHCore
from ah.diagnostics.hidden_valency_diagnostic import run_hidden_valency_diagnostic
from ah.llm.process_backend import LLMResponse


_CHOICES_RE = re.compile(r"CHOICES:\n([A-Z_]+)\n([A-Z_]+)")


class _FirstChoiceBackend:
    is_running = True

    def generate(self, prompt: str, **_kwargs) -> LLMResponse:
        match = _CHOICES_RE.search(prompt)
        if match is None:
            raise AssertionError("diagnostic prompt must contain exactly two protocol choices")
        # Reproduce the observed Qwen transport artifact while always choosing
        # position 1, so the diagnostic must identify order bias rather than fail
        # before the semantic comparison.
        return LLMResponse(match.group(1) + "</think>", {})


class _SemanticBackend:
    is_running = True

    def generate(self, prompt: str, **_kwargs) -> LLMResponse:
        if "receiver/addressee/destination" in prompt:
            if "Verb:\nподарить" in prompt:
                answer = "HAS_RECIPIENT_SLOT"
            else:
                answer = "NO_RECIPIENT_SLOT"
        elif "source/origin slot" in prompt:
            if "Verb:\nполучить" in prompt:
                answer = "HAS_SOURCE_SLOT"
            else:
                answer = "NO_SOURCE_SLOT"
        else:
            raise AssertionError("unexpected diagnostic question")
        return LLMResponse(answer, {})


class _Services:
    def __init__(self, data_dir: Path, backend) -> None:
        prompt_dir = Path(__file__).resolve().parents[1] / "prompts" / "perception"
        self.config = SimpleNamespace(paths=SimpleNamespace(data_dir=data_dir))
        self.operation_lock = RLock()
        self.core = AHCore()
        self.llm = backend
        self.perception = SimpleNamespace(
            settings=SimpleNamespace(
                protocol="adaptive_v3",
                probe_prompt_dir=prompt_dir,
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                max_actants_per_act=8,
                predicate_symbol_language="en",
                morphology_backend="none",
            )
        )


class HiddenValencyDiagnostic1237Tests(unittest.TestCase):
    def test_first_choice_copying_is_detected_even_with_orphan_think_close(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            services = _Services(Path(td), _FirstChoiceBackend())
            result = run_hidden_valency_diagnostic(services)

            self.assertEqual(result.cases, 6)
            self.assertEqual(result.calls, 12)
            self.assertEqual(result.order_bias, 6)
            self.assertEqual(result.semantic_ok, 0)
            self.assertEqual(result.malformed, 0)
            self.assertEqual(result.exact_protocol_calls, 0)
            self.assertEqual(result.wrapper_recovered_calls, 12)
            self.assertEqual(result.first_choice_calls, 12)
            self.assertTrue(result.ah_unchanged)
            self.assertTrue(result.archive_path.is_file())
            summary = (result.output_dir / "summary.txt").read_text(encoding="utf-8")
            self.assertIn("ORDER_BIAS=6", summary)
            self.assertIn("First-choice selections: 12/12", summary)

    def test_semantic_order_invariant_backend_passes_all_six_cases(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            services = _Services(Path(td), _SemanticBackend())
            result = run_hidden_valency_diagnostic(services)

            self.assertEqual(result.semantic_ok, 6)
            self.assertEqual(result.order_bias, 0)
            self.assertEqual(result.semantic_wrong, 0)
            self.assertEqual(result.inconsistent, 0)
            self.assertEqual(result.malformed, 0)
            self.assertEqual(result.exact_protocol_calls, 12)
            # With reversed order, a real semantic decision lands in position 2
            # exactly once per case instead of following position 1.
            self.assertEqual(result.first_choice_calls, 6)
            self.assertTrue(result.ah_unchanged)


if __name__ == "__main__":
    unittest.main()
