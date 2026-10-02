# -*- coding: utf-8 -*-
"""WP3.4 — Replay determinism + StageTimingLog tests (V7 §0.8/§9)."""

import unittest

from ah.formalizer.oracle import canonical_hash
from ah.formalizer.replay import DeterministicPipeline, ReplayHarness, StageTimingLog


class TestReplayDeterminism(unittest.TestCase):
    def test_identical_input_and_run_id_give_identical_output(self):
        p = DeterministicPipeline([("T0", 2), ("T1", 3)], budget=5)
        r = ReplayHarness(p).run_pair("hello", "run-1")
        self.assertTrue(r["identical_within_run"])
        self.assertEqual(canonical_hash(r["a"]), canonical_hash(r["a_repeat"]))

    def test_stage_timing_log_is_deterministic(self):
        p = DeterministicPipeline([("T0", 2), ("T1", 3)], budget=5)
        r = ReplayHarness(p).run_pair("hello", "run-1")
        self.assertEqual(r["a"]["stage_timing"], r["a_repeat"]["stage_timing"])
        self.assertEqual(r["a"]["outcome"], "COMPLETED")

    def test_budget_exhaustion_is_deterministic_and_stops_at_first_unaffordable_stage(self):
        p = DeterministicPipeline([("T0", 2), ("T1", 3), ("T2", 4)], budget=5)   # T2 does not fit
        r = ReplayHarness(p).run_pair("hello", "run-1")
        self.assertEqual(r["a"]["outcome"], "BUDGET_EXHAUSTED")
        self.assertTrue(r["identical_within_run"])                              # stable across repeats
        stages = [s[0] for s in r["a"]["stage_timing"]["stages"]]
        self.assertEqual(stages, ["T0", "T1"])                                  # stopped before T2

    def test_fresh_run_id_is_an_independent_recomputation(self):
        p = DeterministicPipeline([("T0", 2)], budget=5)
        r = ReplayHarness(p).run_pair("hello", "run-1", run_id_b="run-2")
        self.assertTrue(r["independent_run_same_outcome"])                      # recomputed, not served from cache
        self.assertEqual(r["b"]["run_id"], "run-2")

    def test_stage_timing_log_reports_exhaustion(self):
        log = StageTimingLog(3)
        log.record("T0", 2)
        self.assertFalse(log.exhausted)
        log.record("T1", 2)             # total 4 > budget 3
        self.assertTrue(log.exhausted)


if __name__ == "__main__":
    unittest.main()
