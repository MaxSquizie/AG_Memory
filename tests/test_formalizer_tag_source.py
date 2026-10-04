# -*- coding: utf-8 -*-
"""Acceptance tests for the tag source (V7 §6.2/§15): pymorphy3 (+ optional LLM probe) -> tagged tokens."""

import unittest

from ah.formalizer.tag_source import TagSource, tokenize


class _Tag:
    def __init__(self, pos, grams=()):
        self.POS = pos
        self.grammemes = list(grams)


class _Parse:
    def __init__(self, pos, normal_form, score, grams=()):
        self.tag = _Tag(pos, grams)
        self.normal_form = normal_form
        self.score = score


class StubMorph:
    """Deterministic stand-in mirroring observed pymorphy3 facts for the words under test."""

    def __init__(self):
        self.table = {
            "если":   [_Parse("CONJ", "если", 1.0)],
            "хотя":   [_Parse("CONJ", "хотя", 0.8), _Parse("PRCL", "хотя", 0.2)],
            "чтобы":  [_Parse("CONJ", "чтобы", 0.97)],
            "дабы":   [_Parse("CONJ", "дабы", 0.93)],
            "когда":  [_Parse("ADVB", "когда", 0.89), _Parse("CONJ", "когда", 0.11)],
            "пока":   [_Parse("ADVB", "пока", 0.59), _Parse("CONJ", "пока", 0.41)],
            "что":    [_Parse("CONJ", "что", 0.92), _Parse("PRCL", "что", 0.03)],
            "и":      [_Parse("CONJ", "и", 0.998)],
            "а":      [_Parse("CONJ", "а", 0.997)],
            "но":     [_Parse("CONJ", "но", 0.999)],
            "который": [_Parse("ADJF", "который", 0.83, grams=["ADJF", "Subx"])],
            "идёт":   [_Parse("VERB", "идти", 1.0)],
            "дождь":  [_Parse("NOUN", "дождь", 1.0)],
            "зонт":   [_Parse("NOUN", "зонт", 1.0)],
            "нужен":  [_Parse("ADJF", "нужный", 1.0)],
        }

    def parse(self, word):
        return self.table.get(word.lower(), [])


class TestTagSourceLabels(unittest.TestCase):
    def setUp(self):
        self.src = TagSource(StubMorph())

    def test_unambiguous_subordinators_auto_labeled(self):
        for w in ("если", "хотя", "чтобы", "дабы"):
            self.assertEqual(self.src.label(w), "CONJ_SUB", w)

    def test_relative_pronoun_by_morph_category(self):
        self.assertEqual(self.src.label("который"), "RELPRON")

    def test_coordinating_conjunctions_are_not_openers(self):
        # Plain CONJ pass-through (not CONJ_SUB) -> detect_clauses ignores them.
        for w in ("и", "а", "но"):
            self.assertEqual(self.src.label(w), "CONJ", w)

    def test_ambiguous_subordinator_needs_probe(self):
        self.assertNotEqual(self.src.label("пока"), "CONJ_SUB")   # no probe -> content (honest)
        probed = TagSource(StubMorph(), subord_probe=lambda w: w.lower() in {"когда", "пока"})
        self.assertEqual(probed.label("пока"), "CONJ_SUB")
        self.assertEqual(probed.label("когда"), "CONJ_SUB")

    def test_complementizer_chto_needs_probe(self):
        self.assertEqual(self.src.label("что"), "CONJ")          # no probe -> content
        probed = TagSource(StubMorph(), subord_probe=lambda w: w.lower() == "что")
        self.assertEqual(probed.label("что"), "CONJ_SUB")

    def test_probe_is_cached_per_word(self):
        calls = []
        src = TagSource(StubMorph(), subord_probe=lambda w: (calls.append(w), True)[1])
        src.label("пока"); src.label("пока"); src.tag("Пока пока.")
        self.assertEqual(calls.count("пока"), 1)                # probed at most once per word


class TestTagSourceEndToEnd(unittest.TestCase):
    def test_tokenize_keeps_punctuation_separate(self):
        from ah.formalizer.tag_source import tokenize
        self.assertEqual(tokenize("дождь, зонт."), ["дождь", ",", "зонт", "."])

    def test_tag_preserves_delimiters_and_labels_words(self):
        toks = TagSource(StubMorph()).tag("Если идёт дождь, зонт нужен.")
        texts = [t.text for t in toks]
        self.assertIn(",", texts)                                # punctuation kept as a token
        labels = {t.text: t.pos for t in toks}
        self.assertEqual(labels["Если"], "CONJ_SUB")

    def test_detect_end_to_end_stub(self):
        s = TagSource(StubMorph()).detect("Если идёт дождь, зонт нужен.")
        self.assertFalse(s.is_single)
        self.assertTrue(any(c.opener == "IF" for c in s.clauses))


class TestTagSourceRealMorph(unittest.TestCase):
    """Integration against the real pymorphy3 analyzer (no stub)."""

    def setUp(self):
        from ah.formalizer.tag_source import TagSource as TS
        self.src = TS()   # default -> real MorphAnalyzer

    def test_real_subordinators_and_relative(self):
        self.assertEqual(self.src.label("если"), "CONJ_SUB")
        self.assertEqual(self.src.label("хотя"), "CONJ_SUB")
        self.assertEqual(self.src.label("чтобы"), "CONJ_SUB")
        self.assertEqual(self.src.label("который"), "RELPRON")

    def test_real_coordinators_not_openers(self):
        for w in ("и", "а", "но"):
            self.assertNotEqual(self.src.label(w), "CONJ_SUB", w)

    def test_real_sentence_if_pair(self):
        s = self.src.detect("Если идёт дождь, зонт нужен.")
        pairs = s.if_pairs()
        self.assertEqual(len(pairs), 1)
        ant, cons = pairs[0]
        self.assertEqual(s.clauses[ant].opener, "IF")

    def test_real_relative_sentence(self):
        s = self.src.detect("Книга которую я читал интересная.")
        self.assertTrue(any(c.opener == "RELATIVE" for c in s.clauses))


if __name__ == "__main__":
    from ah.formalizer.tag_source import TagSource, tokenize  # noqa: E402
    unittest.main()
