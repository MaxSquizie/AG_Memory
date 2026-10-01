# -*- coding: utf-8 -*-
"""P0 tests — InterpretationRunBinding (CAS) and ProviderCallLog (durable call states)."""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.formalizer.provider_call_log import ProviderCallLog
from ah.formalizer.run_binding import InterpretationRunBinding


class TestInterpretationRunBinding(unittest.TestCase):
    def test_cas_excludes_other_owner(self):
        b = InterpretationRunBinding()
        self.assertTrue(b.acquire("runA", "obs1", 3))
        self.assertFalse(b.acquire("runB", "obs1", 3))   # different owner -> CAS fail
        self.assertEqual(b.holder("obs1", 3), "runA")

    def test_same_owner_idempotent(self):
        b = InterpretationRunBinding()
        self.assertTrue(b.acquire("runA", "obs1", 3))
        self.assertTrue(b.acquire("runA", "obs1", 3))   # idempotent re-acquire

    def test_release_allows_new_owner(self):
        b = InterpretationRunBinding()
        b.acquire("runA", "obs1", 3)
        self.assertTrue(b.release("runA", "obs1", 3))
        self.assertTrue(b.acquire("runB", "obs1", 3))

    def test_bindings_are_durable(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        j = JournalChannel(Path(tmp.name) / "j.log")
        b = InterpretationRunBinding(journal=j)
        b.acquire("runA", "obs1", 3)
        recs = [r["payload"] for r in j.scan_unprocessed(0)]
        self.assertTrue(any(p.get("kind") == "run_bind" and p["owner"] == "runA" for p in recs))


class TestProviderCallLog(unittest.TestCase):
    def test_pending_then_received(self):
        log = ProviderCallLog()
        cid = log.begin("ollama", "digest-1")
        self.assertEqual(log.state(cid), "PENDING")
        self.assertTrue(log.received(cid, response_digest="r1"))
        self.assertEqual(log.state(cid), "RECEIVED")

    def test_ordinal_increments_per_provider(self):
        log = ProviderCallLog()
        a = log.begin("ollama", "d1")
        b = log.begin("ollama", "d2")
        c = log.begin("lmstudio", "d3")
        self.assertEqual(a, "ollama#1")
        self.assertEqual(b, "ollama#2")
        self.assertEqual(c, "lmstudio#1")

    def test_failed_bumps_next_attempt(self):
        log = ProviderCallLog()
        a = log.begin("ollama", "d1")          # attempt 1
        self.assertTrue(log.failed(a, error="timeout"))
        self.assertEqual(log.state(a), "FAILED")
        b = log.begin("ollama", "d1-retry")    # next ordinal -> attempt 2
        self.assertEqual(b, "ollama#2")

    def test_unknown_state_is_none(self):
        log = ProviderCallLog()
        self.assertIsNone(log.state("nope#9"))

    def test_transitions_are_durable(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        j = JournalChannel(Path(tmp.name) / "j.log")
        log = ProviderCallLog(journal=j)
        cid = log.begin("ollama", "d1")
        log.received(cid)
        states = [p.get("state") for p in (r["payload"] for r in j.scan_unprocessed(0)) if p.get("kind") == "prov_call"]
        self.assertEqual(states, ["PENDING", "RECEIVED"])


if __name__ == "__main__":
    unittest.main()
