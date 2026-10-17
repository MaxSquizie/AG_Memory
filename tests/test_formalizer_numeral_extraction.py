# -*- coding: utf-8 -*-
"""Whole selected quantity interpretation: deterministic literals, contextual compounds, no partial sums."""

from __future__ import annotations

import json
import unittest

from ah.formalizer.composition import assemble_ir
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.state import FormalizationState, MorphVariant, TokenEvidence
from ah.formalizer.ir_to_graph import _node_to_op
from ah.formalizer.numeral_extraction import (
    NUMERAL_LEXICON_V1,
    NumeralProbe,
    NumeralProbeError,
    build_numeral_probe_prompt,
    extract_cardinal_value,
    parse_numeral_probe_response,
)
from ah.formalizer.pipeline import MorphProvider, run
from ah.formalizer.selection_protocol import load_decision_schema


class _Tok:  # minimal stand-in for a caller-selected quantity
    def __init__(self, lemma):
        self.lemma = lemma
        self.pos = None
        self.span = (lemma,)


def _toks(*lemmas) -> list[_Tok]:
    return [_Tok(l) for l in lemmas]


class _NumTok:  # carries optional morphology; no POS whitelist gates the probe
    def __init__(self, lemma, pos="NUMR"):
        self.lemma = lemma
        self.pos = pos
        self.span = (lemma,)


class FakeSelect:
    """Test double for the low-level select(prompt)->raw-JSON interface; keyed on the surface form."""

    def __init__(self, mapping):
        self._mapping = mapping  # {surface: raw JSON str} ; missing key -> provider-unavailable raise
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        for surface, raw in self._mapping.items():
            if repr(surface) in prompt:
                self.calls.append(surface)
                return raw
        raise RuntimeError("provider unavailable")  # simulate an unreachable backend


class TestSeedLayer(unittest.TestCase):
    def test_single_numeral_maps_to_resource_value(self):
        self.assertEqual(extract_cardinal_value(_toks("пять")), 5)
        self.assertEqual(extract_cardinal_value(_toks("двадцать")), 20)

    def test_compound_requires_whole_expression_evidence(self):
        self.assertIsNone(extract_cardinal_value(_toks("двадцать", "три")))
        self.assertIsNone(extract_cardinal_value(_toks("сто", "пять")))

    def test_does_not_strip_bounds_from_the_selected_expression(self):
        # tokens carry their LEMMA/normal form (as TokenEvidence does: 'трёх' -> lemma 'три')
        self.assertIsNone(extract_cardinal_value(_toks("не", "менее", "три")))

    def test_unknown_lemma_is_never_assigned_a_value(self):
        self.assertIsNone(extract_cardinal_value(_toks("хрен")))
        # an unknown token terminates the run; a following numeral is not reached across it
        self.assertIsNone(extract_cardinal_value(_toks("пять", "хрен", "три")))

    def test_resource_is_a_declared_mapping_not_logic(self):
        for lemma, value in {"ноль": 0, "один": 1, "десять": 10, "сто": 100, "тысяча": 1000}.items():
            self.assertEqual(NUMERAL_LEXICON_V1[lemma], value)


class _SpanTok:  # minimal token carrying only a surface form (digit rule reads ev.span first)
    def __init__(self, span):
        self.span = span
        self.lemma = None
        self.pos = None


class TestDigitLiterals(unittest.TestCase):
    """Digits are an unambiguous orthographic literal -> read directly (no table, no model)."""

    def test_bare_digits_read_directly(self):
        sources: list = []
        self.assertEqual(extract_cardinal_value([_SpanTok("52")], sources=sources), 52)
        self.assertEqual(sources, [("digits", 52)])

    def test_separators_require_context(self):
        self.assertIsNone(extract_cardinal_value([_SpanTok("1 000")]))
        self.assertIsNone(extract_cardinal_value([_SpanTok("1.000")]))

    def test_decimal_and_ordinal_are_not_cardinal_literals(self):
        self.assertIsNone(extract_cardinal_value([_SpanTok("3,5")]))   # decimal -> not a clean count
        self.assertIsNone(extract_cardinal_value([_SpanTok("42-й")]))  # ordinal, different construct

    def test_digit_beats_seed_and_needs_no_probe(self):
        sel = FakeSelect({})  # would raise if the model were ever consulted
        toks = [_NumTok("52")]  # even with a POS, the digit literal short-circuits first
        self.assertEqual(extract_cardinal_value(toks, probe=NumeralProbe(sel)), 52)
        self.assertEqual(sel.calls, [])


class TestBoundedProbe(unittest.TestCase):
    def test_table_hit_short_circuits_without_probing(self):
        sel = FakeSelect({})  # would raise if ever called
        probe = NumeralProbe(sel)
        sources: list = []
        self.assertEqual(extract_cardinal_value(_toks("пять"), probe=probe, sources=sources), 5)
        self.assertEqual(sel.calls, [])  # the seed answered; the model was never asked
        self.assertEqual(sources, [("table", 5)])

    def test_oov_numeral_is_resolved_by_the_model_and_tagged_m(self):
        sel = FakeSelect({"тридцать три": json.dumps({"value": 33})})
        toks = [_NumTok("тридцать три")]  # not in seed, POS NUMR -> bounded probe resolves it
        sources: list = []
        self.assertEqual(extract_cardinal_value(toks, probe=NumeralProbe(sel), sources=sources), 33)
        self.assertEqual(sources, [("probe", 33)])  # model judgment, not declared fact

    def test_probe_refusal_contributes_nothing(self):
        sel = FakeSelect({"несколько": json.dumps({"value": None})})
        toks = [_NumTok("несколько")]  # absent from seed -> probe refuses (fuzzy quantity) -> no value
        self.assertIsNone(extract_cardinal_value(toks, probe=NumeralProbe(sel)))

    def test_provider_unavailable_is_honest_not_a_guess(self):
        sel = FakeSelect({})  # any call raises provider-unavailable
        toks = [_NumTok("какое-то")]
        self.assertIsNone(extract_cardinal_value(toks, probe=NumeralProbe(sel)))

    def test_call_budget_is_bounded(self):
        sel = FakeSelect({"a b c": json.dumps({"value": 123})})
        toks = [_NumTok("a"), _NumTok("b"), _NumTok("c")]
        # One call interprets the entire selected expression; it cannot return a prefix sum.
        self.assertEqual(extract_cardinal_value(toks, probe=NumeralProbe(sel), max_probes=1), 123)
        self.assertEqual(len(sel.calls), 1)

    def test_parse_contract_rejects_malformed(self):
        self.assertIsNone(parse_numeral_probe_response(json.dumps({"value": None})))
        self.assertEqual(parse_numeral_probe_response(json.dumps({"value": 7})), 7)
        with self.assertRaises(NumeralProbeError):
            parse_numeral_probe_response(json.dumps({"value": "seven"}))
        with self.assertRaises(NumeralProbeError):
            parse_numeral_probe_response(json.dumps({"other": 1}))


class TestAtLeastNIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_decision_schema()
        cls.morph = MorphProvider()

    def _ir(self, text):
        st = run(text, self.schema, FakeSelector(), morph=self.morph)
        return assemble_ir(st,numeral_probe=NumeralProbe(FakeSelect({"пять перьев": '{"value":5}'}))), st

    def test_minimum_window_passes_complete_quantity_to_probe(self):
        ir, _ = self._ir("Минимум пять перьев выпало.")
        at_least = [n for t in ir.operator_trees for n in t.nodes if n.operator_type == "AT_LEAST_N"]
        self.assertTrue(at_least, "the declared 'минимум' trigger must yield an AT_LEAST_N scope")
        self.assertEqual(at_least[0].threshold, 5)

    def test_extracted_threshold_flows_to_materialization(self):
        ir, _ = self._ir("Минимум пять перьев выпало.")
        node = next(n for t in ir.operator_trees for n in t.nodes if n.operator_type == "AT_LEAST_N")
        op = _node_to_op(node)  # the same mapping build_scope_tree_ops uses per quantifier
        self.assertEqual(op.bound_value, 5.0)  # declared threshold -> materialized value bound


class TestProbeEndToEnd(unittest.TestCase):
    """The bounded probe is reachable through the real seam: assemble_ir -> build_scope_trees ->
    extract_cardinal_value(probe=...). A controlled state (OOV NUMR token after 'минимум') proves the
    model judgment flows to the AT_LEAST_N threshold, not just the isolated extraction function."""

    def _state(self):
        st = FormalizationState.new("x")
        st.evidence.extend([
            TokenEvidence(span="минимум", lemma="минимум", pos="NOUN",
                         variants=(MorphVariant(lemma="минимум", pos="NOUN"),)),
            # a numeral NOT in the seed table, structurally NUMR -> only the bounded probe can value it
            TokenEvidence(span="тридцать три", lemma="тридцать три", pos="NUMR",
                         variants=(MorphVariant(lemma="тридцать три", pos="NUMR"),)),
            TokenEvidence(span="выпало", lemma="выпасть", pos="VERB",
                         variants=(MorphVariant(lemma="выпасть", pos="VERB", tense="past"),)),
        ])
        return st

    def test_oov_numeral_threshold_comes_from_the_probe(self):
        sel = FakeSelect({"тридцать три": json.dumps({"value": 33})})
        ir = assemble_ir(self._state(), numeral_probe=NumeralProbe(sel))
        at_least = [n for t in ir.operator_trees for n in t.nodes if n.operator_type == "AT_LEAST_N"]
        self.assertTrue(at_least)
        self.assertEqual(at_least[0].threshold, 33)  # model judgment, threaded end-to-end

    def test_without_probe_the_oov_numeral_asserts_nothing(self):
        ir = assemble_ir(self._state())  # seed-only: the OOV numeral is not in the table -> no threshold
        at_least = [n for t in ir.operator_trees for n in t.nodes if n.operator_type == "AT_LEAST_N"]
        self.assertTrue(at_least)
        self.assertIsNone(at_least[0].threshold)  # honest incompleteness, never a guess

    def test_quantity_with_noun_flows_end_to_end_with_context(self):
        """The legacy caller supplies the whole quantity window, including its noun."""
        st = run("Минимум 52 перья выпало.", load_decision_schema(), FakeSelector(), morph=MorphProvider())
        ir = assemble_ir(st,numeral_probe=NumeralProbe(FakeSelect({"52 перья": '{"value":52}'})))
        at_least = [n for t in ir.operator_trees for n in t.nodes if n.operator_type == "AT_LEAST_N"]
        self.assertTrue(at_least, "the declared 'минимум' trigger must yield an AT_LEAST_N scope")
        self.assertEqual(at_least[0].threshold, 52)


if __name__ == "__main__":
    unittest.main()
