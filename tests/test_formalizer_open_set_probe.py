# -*- coding: utf-8 -*-
"""D — Open-set value-generation mechanism (V7 §2.3): bounded LLM probe + grounding verification, gated by the trigger.

Proves the honest contract: below threshold no probe runs; a proposal must be grounded in the observed text (no invention);
duplicates of declared values are dropped; and the result is only a *provisional* proposal — nothing is auto-applied.
"""

import json
import types
import unittest


class _ProbeSelector:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def select(self, prompt):
        self.calls += 1
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def _miss_state(text):
    dec = types.SimpleNamespace(slot_id="predicate_value", outcome="NO_CANDIDATE")
    return types.SimpleNamespace(text=text, decisions={"predicate_value": dec})


class TestOpenSetProbe(unittest.TestCase):
    def test_gate_not_fired_runs_no_probe(self):
        from ah.formalizer.open_set_probe import maybe_extend

        sel = _ProbeSelector({"value": "SUPPORTS", "grounding_text": "x"})
        states = [_miss_state("одно предложение")]          # only 1 distinct input -> below threshold (3)
        self.assertIsNone(maybe_extend(states, selector=sel))
        self.assertEqual(sel.calls, 0)                     # no LLM call below the trigger

    def test_grounded_proposal_is_verified_and_provisional(self):
        from ah.formalizer.open_set_probe import maybe_extend, ValueProposal

        sel = _ProbeSelector({"value": "SUPPORTS", "grounding_text": "крыло держит лапку"})
        states = [_miss_state("крыло держит лапку"), _miss_state("другой промах 1"), _miss_state("другой промах 2")]
        existing = ["HAVE", "HAS_PART"]
        res = maybe_extend(states, selector=sel, existing_values=existing)
        self.assertIsInstance(res, ValueProposal)
        self.assertEqual(res.value, "SUPPORTS")
        # provisional only: the declared set is untouched (no auto-apply)
        self.assertEqual(existing, ["HAVE", "HAS_PART"])

    def test_ungrounded_proposal_is_rejected(self):
        from ah.formalizer.open_set_probe import maybe_extend

        sel = _ProbeSelector({"value": "SUPPORTS", "grounding_text": "этого нет ни в одном входе"})
        states = [_miss_state("крыло держит лапку"), _miss_state("другой промах 1"), _miss_state("другой промах 2")]
        self.assertIsNone(maybe_extend(states, selector=sel))   # grounding not in any input -> no invention

    def test_duplicate_of_declared_value_is_dropped(self):
        from ah.formalizer.open_set_probe import maybe_extend

        sel = _ProbeSelector({"value": "HAVE", "grounding_text": "крыло держит лапку"})
        states = [_miss_state("крыло держит лапку"), _miss_state("другой промах 1"), _miss_state("другой промах 2")]
        self.assertIsNone(maybe_extend(states, selector=sel, existing_values=["HAVE", "HAS_PART"]))

    def test_none_response_proposes_nothing(self):
        from ah.formalizer.open_set_probe import maybe_extend

        sel = _ProbeSelector({"value": None, "grounding_text": ""})
        states = [_miss_state("a"), _miss_state("b"), _miss_state("c")]
        self.assertIsNone(maybe_extend(states, selector=sel))

    def test_no_selector_means_inert(self):
        from ah.formalizer.open_set_probe import maybe_extend

        states = [_miss_state("a"), _miss_state("b"), _miss_state("c")]
        self.assertIsNone(maybe_extend(states, selector=None))   # mechanism off by default


if __name__ == "__main__":
    unittest.main()
