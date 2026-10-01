# -*- coding: utf-8 -*-
"""Temporal ledger tests (V7 §6.3) — half-open intervals, re-open, state_at, durability."""

import unittest

from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.temporal import TemporalLedger


class TestHalfOpenIntervals(unittest.TestCase):
    def test_open_interval_true_from_onwards(self):
        L = TemporalLedger()
        L.assert_true("A", 5)
        self.assertFalse(L.is_true_at("A", 4))
        self.assertTrue(L.is_true_at("A", 5))
        self.assertTrue(L.is_true_at("A", 10))

    def test_close_is_half_open(self):
        L = TemporalLedger()
        L.assert_true("A", 5)
        L.close("A", 8)
        self.assertTrue(L.is_true_at("A", 7))
        self.assertFalse(L.is_true_at("A", 8))   # half-open: [5,8) excludes 8
        self.assertFalse(L.is_true_at("A", 9))

    def test_reopen_after_close(self):
        L = TemporalLedger()
        L.assert_true("A", 5)
        L.close("A", 8)
        L.assert_true("A", 12)
        self.assertFalse(L.is_true_at("A", 10))   # gap between the two intervals
        self.assertTrue(L.is_true_at("A", 13))

    def test_close_without_open_returns_false(self):
        L = TemporalLedger()
        self.assertFalse(L.close("ghost", 3))


class TestStateAt(unittest.TestCase):
    def test_state_at_selects_by_time(self):
        L = TemporalLedger()
        L.assert_true("A", 1)
        L.assert_true("B", 4)
        L.close("A", 6)

        self.assertEqual(L.state_at(2), {"A"})          # only A open at t=2
        self.assertEqual(L.state_at(5), {"A", "B"})     # both open at t=5
        self.assertEqual(L.state_at(7), {"B"})          # A closed at 6, B still open

    def test_multiple_intervals_same_fact(self):
        L = TemporalLedger()
        L.assert_true("A", 1)
        L.close("A", 3)
        L.assert_true("A", 5)
        ivs = L.intervals("A")
        self.assertEqual(len(ivs), 2)
        self.assertTrue(L.is_true_at("A", 2))
        self.assertFalse(L.is_true_at("A", 4))
        self.assertTrue(L.is_true_at("A", 6))


class TestTemporalDurability(unittest.TestCase):
    def test_open_close_are_journaled(self):
        s = MemoryStore()
        L = TemporalLedger(store=s)
        L.assert_true("A", 1)
        L.close("A", 3)
        kinds = [r.payload.get("kind") for r in s.scan_unprocessed(0)]
        self.assertIn("time_open", kinds)
        self.assertIn("time_close", kinds)


if __name__ == "__main__":
    unittest.main()
