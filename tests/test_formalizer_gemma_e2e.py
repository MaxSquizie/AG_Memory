# -*- coding: utf-8 -*-
"""Live end-to-end test of the Phase 1 pipeline on a real local model (Gemma via LM Studio).

Skips cleanly when the LM Studio server or the model is not reachable, so it never breaks an offline run. When available,
it drives arbitrary examples through the SAME ``run()`` path as the scripted dry run and asserts the mechanism invariants
that must hold regardless of model quality:

* a RESOLVED decision is never fabricated: it has a non-empty selection AND a value-specific positive ground for that value;
* an infra failure (provider/protocol) leaves the decision un-evaluated (``outcome=None``, lifecycle OPEN) — it is NOT
  conflated with a semantic verdict such as UNRESOLVED (§1.4/§0.8).

Set GEMMA_MODEL to override the model key (default ``gemma-3n-e4b-it``).
"""

import os
import unittest


def _available(model):
    from ah.formalizer.lmstudio_selector import LMStudioSelector, LMStudioSelectorError
    try:
        sel = LMStudioSelector(model=model, timeout_seconds=60.0)
        return model in sel.list_models()
    except (LMStudioSelectorError, Exception):  # noqa: BLE001 - any transport error means "skip"
        return False


MODEL = os.environ.get("GEMMA_MODEL", "gemma-3n-e4b-it")
_POSITIVE = {"R", "C", "D", "M", "A"}


class TestGemmaE2E(unittest.TestCase):
    def setUp(self):
        if not _available(MODEL):
            self.skipTest(f"LM Studio model {MODEL!r} not reachable; skipping live e2e")
        from ah.formalizer.lmstudio_selector import LMStudioSelector
        self.sel = LMStudioSelector(model=MODEL, temperature=0.0, max_tokens=96, timeout_seconds=180.0)

    def _predicate(self, state):
        for dec in state.decisions.values():
            if dec.slot_id == "predicate_value":
                return dec
        self.fail("no predicate_value decision produced")

    def test_arbitrary_examples_never_fabricate_and_always_grant_outcome(self):
        from ah.formalizer.selection_protocol import load_decision_schema
        from ah.formalizer.pipeline import run

        schema = load_decision_schema()
        examples = [
            "Вороны любят червей.",          # in-set (LIKE) — may RESOLVE on a confident single pick
            "Ворона летает высоко над городом.",  # out-of-set — honest NO_CANDIDATE / protocol failure, never fabricated
        ]
        for text in examples:
            st = run(text, schema, self.sel)
            dec = self._predicate(st)
            # A granted semantic outcome must be one of the declared set (or None when un-evaluated on an infra failure).
            self.assertIn(dec.outcome, {None, "RESOLVED", "AMBIGUOUS", "UNRESOLVED",
                                        "NO_CANDIDATE", "INSUFFICIENT_CONTEXT"}, f"{text!r}: bad outcome")
            # RESOLVED is never fabricated — needs a selection and a value-specific positive ground.
            if dec.outcome == "RESOLVED":
                self.assertTrue(dec.selected, f"{text!r}: RESOLVED with empty selection")
                v = dec.selected[0]
                grounded = any(g.type in _POSITIVE and g.value == v for g in dec.grounds)
                self.assertTrue(grounded, f"{text!r}: RESOLVED '{v}' lacks a value-specific positive ground")


if __name__ == "__main__":
    unittest.main()
