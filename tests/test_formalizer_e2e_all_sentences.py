# -*- coding: utf-8 -*-
"""Path B slice 3 — all six demo sentences end-to-end through the canonical store (V7 §14).

Fully demo-grounded (no dead mechanics): every assertion pins a REAL sentence's observed-correct behavior.
Proves across ALL relation types (HAVE/HAS_PART/LOCATIVE/LIKE) that the replacement seam is robust —
resolved declaratives land in the canonical store, unresolved ones are honestly empty (never fabricated),
and declared contextual statements resolve HAS_PART end-to-end. The copula/structural path integrates cleanly.
"""

import unittest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import Domain, Property
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.runtime_adapter import FormalizerAdapter

# etalon v1 demo set (S1..S6) and the declared contextual statements that resolve HAS_PART.
SENTENCES = [
    "У вороны есть лапки.",   # S1
    "У стола есть ножки.",    # S2
    "У меня есть книга.",     # S3
    "Ворона обладает перьями.",  # S4
    "У вороны лапки.",        # S5 (pure ellipsis, no copula)
    "Вороны любят червей.",   # S6
]
FACTS = {0: "Лапки — часть тела этой вороны.", 1: "Ножки — часть этого стола.", 3: "Перья — часть тела этой вороны."}


def _harness():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, properties={"name": Property("name", "Пользователь", "str")}, uid="M_USER")
    context = InteractionContext(user_ref=core.ref(user.uid))
    integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2, 0.18))
    return core, context, integration


class AllSentencesE2ETest(unittest.TestCase):
    def test_every_sentence_integrates_without_error(self):
        for mode in ("baseline", "augmented"):
            core, context, integration = _harness()
            adapter = FormalizerAdapter(FakeSelector.demo(mode))
            for i, text in enumerate(SENTENCES):
                cf = (FACTS[i],) if (mode == "augmented" and i in FACTS) else ()
                result = adapter.parse(text, context_facts=cf)
                integration.integrate_external(result, context)  # must not raise for any relation type

    def test_baseline_unresolved_sentences_emit_no_fabricated_assertion(self):
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        counts = [len(adapter.parse(t).assertions) for t in SENTENCES]
        # Only S3 (copula HAVE) and S6 (verbal LIKE) resolve uniquely without context; the rest stay honest.
        self.assertEqual(counts, [0, 0, 1, 0, 0, 1])

    def test_resolved_verbal_lands_in_store(self):
        core, context, integration = _harness()
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        result = adapter.parse(SENTENCES[5])  # S6 "Вороны любят червей."
        self.assertEqual(len(result.assertions), 1)
        integration.integrate_external(result, context)
        self.assertIsNotNone(core.store.find_symbol_by_form("любить"))

    def test_augmented_context_resolves_has_part_end_to_end(self):
        core, context, integration = _harness()
        adapter = FormalizerAdapter(FakeSelector.demo("augmented"))
        counts = []
        for i, text in enumerate(SENTENCES):
            cf = (FACTS[i],) if i in FACTS else ()
            result = adapter.parse(text, context_facts=cf)
            integration.integrate_external(result, context)  # must not raise
            counts.append(len(result.assertions))
        # S1/S2/S4 resolve to HAS_PART via their declared statement; S5 (no fact) stays unresolved.
        self.assertEqual(counts, [1, 1, 1, 1, 0, 1])


if __name__ == "__main__":
    unittest.main()
