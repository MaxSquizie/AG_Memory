# -*- coding: utf-8 -*-
"""End-to-end vertical tests — the thin orchestrator composes the proven modules correctly.

Asserts the LIVE flow, not re-implementations: T0..T4 outcomes (baseline UNRESOLVED / augmented
RESOLVED), a durable commit through the store, goals compiled only from an injected resolver (never
fabricated), and R-X ranking that reorders but never excludes an admissible candidate.
"""

import unittest

from ah.model.types import Ref, RefKind

from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.rx_cache import FormalizationCache
from ah.formalizer.selection_protocol import load_decision_schema
from ah.formalizer.store_interface import TerminalOutcome
from ah.formalizer.vertical import run_vertical

SCHEMA = load_decision_schema()
S1 = "У вороны есть лапки."
F1 = ("Лапки — часть тела этой вороны.",)


def value_dec(state):
    for dec in state.decisions.values():
        if dec.slot_id == "predicate_value":
            return dec
    raise AssertionError("no predicate_value decision")


def cand_ids(ir):
    return [g.graph_id or f"G{i + 1}" for i, g in enumerate(ir.semantic_candidates)]


class TestVertical(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()

    def test_baseline_unresolved_and_commits(self):
        rep = run_vertical(S1, schema=SCHEMA, selector=FakeSelector.demo("baseline"), store=self.store)
        dec = value_dec(rep.state)
        self.assertEqual(dec.outcome, "UNRESOLVED")      # honest {V1,V2} (rev7b)
        self.assertEqual(dec.lifecycle, "PROVISIONAL")   # RESOLVED/COMMITTED not granted in baseline
        self.assertTrue(rep.commit.applied)
        self.assertEqual(rep.commit.terminal, TerminalOutcome.APPLIED)

    def test_augmented_resolved_and_commits(self):
        rep = run_vertical(S1, schema=SCHEMA, selector=FakeSelector.demo("augmented"),
                           context_facts=F1, store=self.store)
        dec = value_dec(rep.state)
        self.assertEqual(dec.outcome, "RESOLVED")
        self.assertTrue(rep.commit.applied)

    def test_goals_only_from_injected_resolver_never_fabricated(self):
        # No resolver -> nothing resolves -> no goals (never fabricated).
        rep0 = run_vertical(S1, schema=SCHEMA, selector=FakeSelector.demo("baseline"), store=self.store)
        self.assertEqual(rep0.goals, ())

        # A resolver covering every lexical unit -> exactly C(n,2) pairwise goals.
        units = list(rep0.ir.lexical_units)
        ref_map = {u: Ref(f"r{i}", RefKind.N) for i, u in enumerate(units)}
        rep = run_vertical(S1, schema=SCHEMA, selector=FakeSelector.demo("baseline"),
                           store=self.store, ref_map=ref_map)
        n = len(units)
        self.assertEqual(len(rep.goals), n * (n - 1) // 2)

    def test_rx_ranking_never_excludes(self):
        rx = FormalizationCache({"formalizer_schema_version": "v1"})
        rep = run_vertical(S1, schema=SCHEMA, selector=FakeSelector.demo("baseline"),
                           store=self.store, rx=rx)
        # R-X reorders but never drops an admissible candidate: a permutation of the set.
        self.assertEqual(set(rep.ranked_semantic_ids), set(cand_ids(rep.ir)))


if __name__ == "__main__":
    unittest.main()
