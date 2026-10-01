# -*- coding: utf-8 -*-
"""WP0.2 — ProviderAdapter + BudgetSnapshot tests (V7 §0.8 / §14 line 514).

Proves the capability gate is PROVIDER_UNAVAILABLE (never AMBIGUOUS), replay returns identical bytes with a
single logged ordinal per run, the independent budget limits raise PROPOSAL_BUDGET / COMPUTATION_LIMIT (not
AMBIGUOUS), and a new run reusing another run's input digest is INTEGRITY_ERROR without any AH write.
"""

import unittest

from ah.formalizer.provider_adapter import (
    BudgetExceeded, BudgetSnapshot, IntegrityError, ProviderAdapter, ProviderUnavailable,
)
from ah.formalizer.provider_call_log import ProviderCallLog


def _adapter(caps=("select", "propose_local"), budget=None, transport=lambda p: f"R:{p}", log=None):
    return ProviderAdapter(name="fake", capabilities=frozenset(caps), transport=transport,
                          log=log or ProviderCallLog(), budget=budget or BudgetSnapshot())


class TestCapabilityGate(unittest.TestCase):
    def test_missing_capability_is_provider_unavailable_not_ambiguous(self):
        a = _adapter(caps=("propose_local",))  # no "select"
        with self.assertRaises(ProviderUnavailable):
            a.select("p", run_id="r1")

    def test_no_transport_is_provider_unavailable(self):
        a = ProviderAdapter(name="x", capabilities=frozenset({"select"}), transport=None)
        with self.assertRaises(ProviderUnavailable):
            a.select("p", run_id="r1")


class TestReplayAndOrdinal(unittest.TestCase):
    def test_replay_returns_identical_bytes_single_ordinal(self):
        log = ProviderCallLog()
        a = _adapter(log=log)
        out1 = a.select("hello", run_id="r1")
        out2 = a.select("hello", run_id="r1")  # replay within the same run
        self.assertEqual(out1, out2)
        received = [cid for cid in ("fake#1", "fake#2") if log.state(cid) == "RECEIVED"]
        self.assertEqual(received, ["fake#1"])  # only one logged exchange despite two calls

    def test_failed_transport_is_provider_unavailable(self):
        def boom(p):
            raise RuntimeError("down")
        a = _adapter(transport=boom)
        with self.assertRaises(ProviderUnavailable):
            a.select("p", run_id="r1")


class TestBudget(unittest.TestCase):
    def test_tp_calls_limit_is_proposal_budget(self):
        a = _adapter(budget=BudgetSnapshot(tp_calls=1))
        a.propose_local("s", run_id="r1")
        with self.assertRaises(BudgetExceeded) as ctx:
            a.propose_local("s2", run_id="r1")
        self.assertEqual(ctx.exception.code, "PROPOSAL_BUDGET")

    def test_validate_structure_over_limit_is_proposal_budget(self):
        a = _adapter(budget=BudgetSnapshot(max_nodes=3, max_edges=4, max_depth=2))
        a.validate_structure(3, 4, 2)          # exactly at the limit -> ok
        with self.assertRaises(BudgetExceeded) as ctx:
            a.validate_structure(4, 0, 0)      # one node over
        self.assertEqual(ctx.exception.code, "PROPOSAL_BUDGET")

    def test_token_limit_is_computation_limit(self):
        big = lambda p: "x" * 10_000           # ~2500 tokens by the len//4 charge
        a = _adapter(transport=big, budget=BudgetSnapshot(token_limit=10))
        with self.assertRaises(BudgetExceeded) as ctx:
            a.select("p", run_id="r1")
        self.assertEqual(ctx.exception.code, "COMPUTATION_LIMIT")


class TestIntegrity(unittest.TestCase):
    def test_new_run_reusing_input_digest_is_integrity_error(self):
        a = _adapter()
        a.select("same-input", run_id="run-A")
        with self.assertRaises(IntegrityError):
            a.select("same-input", run_id="run-B")  # a different, new run on the same input


if __name__ == "__main__":
    unittest.main()
