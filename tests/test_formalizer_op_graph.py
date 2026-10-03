# -*- coding: utf-8 -*-
"""P2 slice — op→graph materialization (WP0.5 seam / §12/§17).

Proves the new formalizer's commit writes REAL elements into a live AHStore graph, not just journal
rows: admitted lexical units become AbstractSymbols (S), verified by reading them back from the store
after a full vertical commit on a real file; an idempotent re-commit does NOT duplicate them; and a
non-head (rejected) run materializes no version-specific content.
"""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.core.operations import AHCore
from ah.core.store import AHStore

from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.commit_stage import commit
from ah.formalizer.state import FormalizationState, TokenEvidence
from ah.formalizer.store_interface import TerminalOutcome
from ah.formalizer.t6_core import PendingBatch


def _state() -> FormalizationState:
    st = FormalizationState.new("Ворона имеет перья")
    for span in ("Ворона", "имеет", "перья"):
        st.evidence.append(TokenEvidence(span=span))
    return st


class TestOpGraphMaterialization(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self._tmp.name) / "journal.jsonl"
        self.core = AHCore(AHStore())
        self.adapter = AHStoreAdapter(self.core.store, JournalChannel(self.log_path), core=self.core)
        # Register the lexical op→graph handler: an admitted word form becomes a live AbstractSymbol.
        self.adapter.register_op_handler("ADD_SYMBOL", lambda core, p: core.add_abstract_symbol({p["form"]}))

    def tearDown(self):
        self._tmp.cleanup()

    def _symbol_count(self, form: str) -> int:
        return len(self.core.store.find_symbols_by_form(form))

    def test_commit_materializes_symbols_into_live_graph(self):
        rep = commit(_state(), self.adapter, run_id="r1")
        self.assertTrue(rep.admitted_at_head)
        self.assertIs(rep.terminal, TerminalOutcome.APPLIED)
        # The admitted lexical units are now REAL symbols in the live store (not just journal rows).
        for form in ("Ворона", "имеет", "перья"):
            self.assertGreaterEqual(self._symbol_count(form), 1, f"expected a live symbol for {form!r}")

    def test_recommit_is_idempotent_and_does_not_duplicate_symbols(self):
        commit(_state(), self.adapter, run_id="r1")
        before = {f: self._symbol_count(f) for f in ("Ворона", "имеет", "перья")}
        second = commit(_state(), self.adapter, run_id="r1")  # same IR + run -> same batch_hash
        self.assertIs(second.terminal, TerminalOutcome.APPLIED)  # run fate unchanged by a no-op re-commit
        after = {f: self._symbol_count(f) for f in ("Ворона", "имеет", "перья")}
        self.assertEqual(before, after, "idempotent re-commit must not duplicate live symbols")

    def test_non_head_run_writes_no_symbols(self):
        pending = [PendingBatch(batch_id="aaa", seq=0)]
        rep = commit(_state(), self.adapter, run_id="zzz", pending=pending)  # "aaa" < "zzz" -> not at head
        self.assertFalse(rep.admitted_at_head)
        for form in ("Ворона", "имеет", "перья"):
            self.assertEqual(self._symbol_count(form), 0, f"a rejected run must materialize no {form!r}")


if __name__ == "__main__":
    unittest.main()
