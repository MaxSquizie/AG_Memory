# -*- coding: utf-8 -*-
"""Numeral extraction (declared language resource + declared additive composition).

Part A exercises the pure module on synthetic tokens (no pipeline): a single numeral maps to its
resource value, adjacent numerals compose additively, and an unknown lemma yields None (never guessed).
Part B drives the real pipeline: a sentence with the declared AT_LEAST_N trigger 'минимум' + a cardinal
numeral produces a scope tree whose threshold is extracted from the resource, and materializes as a value token.
"""

from __future__ import annotations

import unittest

from ah.formalizer.composition import assemble_ir
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.ir_to_graph import _node_to_op
from ah.formalizer.numeral_extraction import NUMERAL_LEXICON_V1, extract_cardinal_value
from ah.formalizer.pipeline import MorphProvider, run
from ah.formalizer.selection_protocol import load_decision_schema


class _Tok:  # minimal stand-in: extraction only reads .lemma
    def __init__(self, lemma):
        self.lemma = lemma


def _toks(*lemmas) -> list[_Tok]:
    return [_Tok(l) for l in lemmas]


class TestNumeralResource(unittest.TestCase):
    def test_single_numeral_maps_to_resource_value(self):
        self.assertEqual(extract_cardinal_value(_toks("пять"), 0), 5)
        self.assertEqual(extract_cardinal_value(_toks("двадцать"), 0), 20)

    def test_compound_composes_additively(self):
        # 'двадцать три' = 23 ; 'сто пять' = 105 (declared additive composition of adjacent numerals)
        self.assertEqual(extract_cardinal_value(_toks("двадцать", "три"), 0), 23)
        self.assertEqual(extract_cardinal_value(_toks("сто", "пять"), 0), 105)

    def test_skips_leading_non_numeral_tokens(self):
        # 'не менее трёх' -> the numeral expression is reached past the non-numeral lead-in
        # (tokens carry their LEMMA/normal form, as TokenEvidence does: 'трёх' -> lemma 'три')
        self.assertEqual(extract_cardinal_value(_toks("не", "менее", "три"), 0), 3)

    def test_unknown_lemma_is_never_assigned_a_value(self):
        self.assertIsNone(extract_cardinal_value(_toks("хрен"), 0))
        # an unknown token terminates the run; a following numeral is not reached across it
        self.assertEqual(extract_cardinal_value(_toks("пять", "хрен", "три"), 0), 5)

    def test_resource_is_a_declared_mapping_not_logic(self):
        # spot-check the resource covers the standard forms used by the tests above
        for lemma, value in {"ноль": 0, "один": 1, "десять": 10, "сто": 100, "тысяча": 1000}.items():
            self.assertEqual(NUMERAL_LEXICON_V1[lemma], value)


class TestAtLeastNIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_decision_schema()
        cls.morph = MorphProvider()

    def _ir(self, text):
        st = run(text, self.schema, FakeSelector(), morph=self.morph)
        return assemble_ir(st), st

    def test_minimum_trigger_extracts_threshold(self):
        ir, _ = self._ir("Минимум пять перьев выпало.")
        at_least = [n for t in ir.operator_trees for n in t.nodes if n.operator_type == "AT_LEAST_N"]
        self.assertTrue(at_least, "the declared 'минимум' trigger must yield an AT_LEAST_N scope")
        self.assertEqual(at_least[0].threshold, 5)

    def test_extracted_threshold_flows_to_materialization(self):
        ir, _ = self._ir("Минимум пять перьев выпало.")
        node = next(n for t in ir.operator_trees for n in t.nodes if n.operator_type == "AT_LEAST_N")
        op = _node_to_op(node)  # the same mapping build_scope_tree_ops uses per quantifier
        self.assertEqual(op.bound_value, 5.0)  # declared threshold -> materialized value bound


if __name__ == "__main__":
    unittest.main()
