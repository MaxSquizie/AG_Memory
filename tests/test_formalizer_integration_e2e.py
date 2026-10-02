# -*- coding: utf-8 -*-
"""Path B slice 2 — end-to-end: FormalizerAdapter -> IntegrationService.integrate_external (V7 §14).

Proves the replacement seam reaches the canonical store, mirroring the proven harness in
test_architecture_alignment_1220. Verbal frames carry a REAL predicate (surface + lemma) and register
cleanly; copula frames carry the real copula word from evidence; only a genuine verb-less ellipsis
yields a declared STRUCTURAL predicate — never a fabricated lexeme.
"""

import types
import unittest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import Domain, Property
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.formalizer.state import MorphVariant, TokenEvidence


class FormalizerIntegrationE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        user = self.core.add_entity(
            Domain.P, properties={"name": Property("name", "Пользователь", "str")}, uid="M_USER"
        )
        # integrate_external requires a user_ref (the speaker the assertion is attributed to).
        self.context = InteractionContext(user_ref=self.core.ref(user.uid))
        self.integration = IntegrationService(self.core, IntegrationConfig(0.4, 0.3, 0.2, 0.18))

    def test_verbal_like_lands_in_core_store(self):
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        result = adapter.parse("Вороны любят червей.")  # ONE_SELECTED V4 -> RESOLVED (verbal NOM+V+ACC)
        self.assertEqual(len(result.assertions), 1)
        commit = self.integration.integrate_external(result, self.context)
        self.assertIsNotNone(commit, "integrate_external must return a commit (seam reaches the store)")
        # The real verb lemma is registered as a canonical symbol — the assertion flowed end-to-end.
        self.assertIsNotNone(self.core.store.find_symbol_by_form("любить"))

    def test_copula_frame_carries_real_surface_from_evidence(self):
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        result = adapter.parse("У меня есть книга.")  # copula "есть" parses as VERB -> real surface carried
        self.assertEqual(len(result.assertions), 1)
        self.assertEqual(result.assertions[0].predicate.surface, "есть")

    def test_structural_fallback_only_when_no_verb_in_evidence(self):
        adapter = FormalizerAdapter(FakeSelector.demo("baseline"))
        # A genuine verb-less ellipsis (no VERB variant anywhere in evidence) -> declared STRUCTURAL predicate.
        no_verb_state = types.SimpleNamespace(
            evidence=[TokenEvidence(span="лапки", variants=(MorphVariant(lemma="лапка", pos="NOUN", cases=frozenset(), score=1.0),))]
        )
        pred = adapter._build_predicate(frame=None, state=no_verb_state, value="V2")
        self.assertTrue((pred.sense_hint or "").startswith("STRUCTURAL_"))


if __name__ == "__main__":
    unittest.main()
