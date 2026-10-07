# -*- coding: utf-8 -*-
"""I01/I02 — the V7-native production path is real, selectable, and capability-complete.

Proves what ``LLMPerceptionService.perceive`` routes to when ``native_commit`` is enabled:
  * a wired durable store makes the adapter native-capable;
  * ``interpret()`` runs real input through T0..T4 -> C -> T5 gate (+binding CAS) -> T6 and commits durably
    (a FACT asserted for a resolved value), with records physically present in the journal file after reopen;
  * I02: ``interpret()`` returns a FULL PerceptionResult whose candidate set (assertions/queries/commands)
    equals the legacy parse() for the same input+selector — so flipping the agent loop to it regresses nothing;
  * the legacy mode is untouched: ``parse()`` still returns a PerceptionResult.

Validates the production wiring on an isolated core before the agent-loop call sites are flipped to it.
"""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.core.operations import AHCore
from ah.core.store import AHStore
from ah.perception.contracts import PerceptionResult

from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.runtime_adapter import FormalizerAdapter


S3 = 'У меня есть книга.'          # "У меня есть книга." (nominative — the form the augmented selector resolves)
FACT = 'Книга принадлежит мне.'      # "Книга принадлежит мне."
S6 = 'Вороны любят червей.'          # "Вороны любят червей."


class TestNativeProductionPath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "journal.log"
        # Isolated core: the adapter's durable store wraps THIS core's real store.
        self.core = AHCore(AHStore())
        self.adapter = FormalizerAdapter(
            FakeSelector.demo("augmented"),
            store=AHStoreAdapter(self.core.store, JournalChannel(self.log_path)),
            binding=InterpretationRunBinding(),
        )

    def test_native_available_when_store_wired(self):
        self.assertTrue(self.adapter.native_available)
        unwired = FormalizerAdapter(FakeSelector.demo("augmented"))  # no store/binding
        self.assertFalse(unwired.native_available)
        with self.assertRaises(RuntimeError):
            unwired.interpret("x")

    def test_interpret_commits_durable_on_core_store(self):
        res = self.adapter.interpret(S3, context_facts=(FACT,))
        self.assertEqual(res.terminal, "APPLIED")
        self.assertTrue(res.applied)                       # fresh durable write on the real file
        self.assertNotEqual(len(res.committed_fragments), 0)   # a FACT was asserted (not observation-only)
        # I02: the native path returns a FULL PerceptionResult (capability-complete, not assertion-only).
        self.assertIsInstance(res.perception, PerceptionResult)
        self.assertEqual(len(res.perception.assertions), 1)    # S3 augmented -> exactly one resolved fact

        # Durability: reopen the journal from disk and confirm records were physically written.
        reopened = JournalChannel(self.log_path)
        recs = reopened.scan_unprocessed(0, "observation") + reopened.scan_unprocessed(0, "resolution_log")
        self.assertGreater(len(recs), 0)

    def test_legacy_parse_still_returns_perception_result(self):
        pr = self.adapter.parse(S3)
        self.assertIsInstance(pr, PerceptionResult)

    def test_native_perception_matches_legacy_parse(self):
        """I02 capability parity: for the same input+selector the native path's candidate set equals the
        legacy parse() (assertions/queries/commands) — so flipping the agent loop to it regresses nothing."""
        for text in (S6, S3):
            native = self.adapter.interpret(text)
            legacy = self.adapter.parse(text)
            self.assertEqual(native.perception.assertions, legacy.assertions, f"assertions diverge: {text}")
            self.assertEqual(native.perception.queries, legacy.queries, f"queries diverge: {text}")
            self.assertEqual(native.perception.commands, legacy.commands, f"commands diverge: {text}")


if __name__ == "__main__":
    unittest.main()
