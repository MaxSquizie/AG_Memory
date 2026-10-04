# -*- coding: utf-8 -*-
"""Acceptance tests for the IF answer surface (V7 §6.2/§6.3): clause detection wired into the goal path."""

import unittest

from ah.formalizer import clause_detection as cd
from ah.formalizer.if_query import IfStore, answer_if


class FakeTag:
    """Deterministic stand-in for TagSource: maps a sentence to pre-built tagged tokens (no pymorphy3)."""

    def __init__(self, mapping):
        self._m = mapping

    def detect(self, text):
        return cd.detect_clauses(self._m[text])


def T(text, pos=None):
    return cd.Token(text, pos)


SUB_FIRST = [T("Если", "CONJ_SUB"), T("идёт"), T("дождь"), T(","), T("зонт"), T("нужен")]
MAIN_FIRST = [T("Зонт"), T("нужен"), T(","), T("если", "CONJ_SUB"), T("идёт"), T("дождь")]
SINGLE = [T("Ворона"), T("сидит"), T(".")]


class TestIfQueryDeterministic(unittest.TestCase):
    def setUp(self):
        self.tag = FakeTag({"s": SUB_FIRST, "m": MAIN_FIRST, "x": SINGLE})

    def test_single_clause_is_unbound_not_guessed(self):
        a = answer_if("x", self.tag, IfStore())
        self.assertEqual(a.status, "UNBOUND")
        self.assertIsNone(a.holds)

    def test_answered_when_both_clauses_established(self):
        store = IfStore({"идёт дождь", "зонт нужен"})   # content forms (connective stripped before matching)
        a = answer_if("s", self.tag, store)
        self.assertEqual(a.status, "ANSWERED")
        self.assertTrue(a.holds)
        self.assertEqual(a.antecedent, "Если идёт дождь")
        self.assertEqual(a.consequent, "зонт нужен")

    def test_insufficient_when_consequent_missing(self):
        a = answer_if("s", self.tag, IfStore({"идёт дождь"}))
        self.assertEqual((a.status, a.reason), ("INSUFFICIENT", "CONSEQUENT_NOT_DERIVED"))
        self.assertIsNone(a.holds)

    def test_not_asserted_when_premise_missing(self):
        a = answer_if("s", self.tag, IfStore())
        self.assertEqual((a.status, a.reason), ("NOT_ASSERTED", "ANTECEDENT_NOT_IN_STORE"))

    def test_main_first_ordering_still_answers(self):
        store = IfStore({"идёт дождь", "зонт нужен"})
        a = answer_if("m", self.tag, store)
        self.assertEqual(a.status, "ANSWERED")
        self.assertEqual(a.antecedent, "если идёт дождь")   # the IF clause is the antecedent regardless of position
        self.assertEqual(a.consequent, "Зонт нужен")

    def test_deterministic_for_fixed_store_and_text(self):
        store = IfStore({"идёт дождь", "зонт нужен"})
        self.assertEqual(answer_if("s", self.tag, store), answer_if("s", self.tag, store))


class TestIfQueryRealMorph(unittest.TestCase):
    """End-to-end through the real pymorphy3 tag source (no stub)."""

    def setUp(self):
        from ah.formalizer.tag_source import TagSource
        self.src = TagSource()   # default -> real MorphAnalyzer

    def test_real_sentence_answers_when_store_matches(self):
        text = "Если идёт дождь, зонт нужен."
        s = self.src.detect(text)
        ant_idx, con_idx = s.if_pairs()[0]
        from ah.formalizer.if_query import _content
        store = IfStore({_content(s.clauses[ant_idx].text), _content(s.clauses[con_idx].text)})
        a = answer_if(text, self.src, store)
        self.assertEqual(a.status, "ANSWERED")
        self.assertTrue(a.holds)

    def test_real_sentence_not_asserted_on_empty_store(self):
        a = answer_if("Если идёт дождь, зонт нужен.", self.src, IfStore())
        self.assertEqual(a.status, "NOT_ASSERTED")

    def test_real_single_clause_unbound(self):
        a = answer_if("Ворона сидит.", self.src, IfStore({"ворона", "сидит"}))
        self.assertEqual(a.status, "UNBOUND")


if __name__ == "__main__":
    unittest.main()
