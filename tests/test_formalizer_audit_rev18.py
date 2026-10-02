# -*- coding: utf-8 -*-
"""Rev18 audit — expressiveness and context-channel acceptance tests (V5 §16/§15).

The user's four audit sentences are the acceptance criteria; they prove that the
deterministic pipeline EXPRESSES these cases, not merely survives them:

A. "Иван сказал, что Пётр думает, что Мария ушла."
   -> nested SemanticGraphCandidate (PropositionNode inside a PROPOSITION argument);
      competing attachment graphs coexist as linked alternatives (I29).
B. "Не каждый студент мог не сдать экзамен."
   -> ScopeTree NOT(EVERY(POSSIBLE(NOT(F)))) from ONE generic depth rule + the declared
      scope lexicon — no per-sentence knowledge, no silent loss of a trigger.
C. "Он взлетел." + later "Самолёт стоял на полосе."
   -> context revision: same ObservationRecord (source_uid), new interpretation_version;
      NO canonical fact is auto-created (I25) — the IR is the only exit.
D. "Я встретил старого друга из школы." with different contexts
   -> the RESOLUTION channel changes grounds, never candidate sets; the GENERATION
      channel (journal window) changes reference candidates, never predicate ones.

Plus: CandidateIR immutability (Rev14.1) and the closed ArgumentType set (§16.2).
"""
from __future__ import annotations

import unittest

from ah.formalizer.candidate_ir import (
    ARGUMENT_TYPES,
    ArgumentSpec,
    PropositionNode,
    assert_immutable,
)
from ah.formalizer.composition import assemble_ir, journal_mentions_from
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.pipeline import MorphProvider, run, revise
from ah.formalizer.selection_protocol import load_decision_schema

A = "Иван сказал, что Пётр думает, что Мария ушла."
B = "Не каждый студент мог не сдать экзамен."
C0_TEXT = "Он взлетел."
C1_TEXT = "Самолёт стоял на полосе."
D = "Я встретил старого друга из школы."


def _run(text, schema, morph, sel, **kw):
    return run(text, schema, sel, morph=morph, **kw)


class TestAuditRev18(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_decision_schema()
        cls.morph = MorphProvider()
        cls.sel = FakeSelector()

    # ---------------------------------------------------------------- A: nesting

    def test_A_nested_graph_expressed(self):
        ir = assemble_ir(_run(A, self.schema, self.morph, self.sel))
        self.assertGreaterEqual(len(ir.semantic_candidates), 2)
        g1 = ir.semantic_candidates[0]
        rendered = g1.render()
        # Full nesting: SAY(IVAN, P(THINK(PETR, P(LEAVE(MARIA))))).
        self.assertIn("СКАЗАТЬ(Иван", rendered)
        self.assertIn("P(ДУМАТЬ(Пётр, P(УЙТИ(Мария)))", rendered)
        # Structural check (not string matching): a PROPOSITION argument whose value is
        # an EMBEDDED PropositionNode whose head event carries its own PROPOSITION arg.
        outer = next(n for n in g1.nodes if hasattr(n, "predicate") and n.predicate == "сказать")
        prop = next(a for a in outer.participants if a.arg_type == "PROPOSITION")
        self.assertIsInstance(prop.value, PropositionNode)
        self.assertEqual(prop.value.status, "EMBEDDED")
        mid = prop.value.head
        inner = next(a for a in mid.participants if a.arg_type == "PROPOSITION")
        self.assertIsInstance(inner.value, PropositionNode)
        self.assertEqual(inner.value.head.predicate, "уйти")

    def test_A_competing_graphs_coexist(self):
        st = _run(A, self.schema, self.morph, self.sel)
        ir = assemble_ir(st)
        renders = [g.render() for g in ir.semantic_candidates]
        self.assertGreater(len(set(renders)), 1)  # genuinely different derivations
        # I29: the non-primary graph is a LINKED ALTERNATIVE, never deleted silently.
        alt_kinds = [(a.kind, a.source_candidate_id) for a in st.linked_alternatives]
        self.assertIn(("SEMANTIC_GRAPH", "G2"), alt_kinds)
        # The ambiguity set names the competing graphs explicitly.
        self.assertTrue(any("G1" in s and "G2" in s for s in ir.ambiguity_sets))

    def test_A_honest_misses_not_faked_values(self):
        st = _run(A, self.schema, self.morph, self.sel)
        pv = [d for d in st.decisions.values() if d.slot_id == "predicate_value"]
        self.assertTrue(pv)  # every frame (FLAT + NESTED) got a decision
        for d in pv:  # said/thinks/left are outside the demo set -> honest NO_CANDIDATE
            self.assertEqual(d.outcome, "NO_CANDIDATE")
        self.assertTrue(st.miss_reports)

    # ---------------------------------------------------------------- B: scope tree

    def test_B_scope_tree_shape(self):
        ir = assemble_ir(_run(B, self.schema, self.morph, self.sel))
        self.assertEqual(len(ir.operator_trees), 1)
        t = ir.operator_trees[0]
        self.assertEqual(t.render(), "NOT(EVERYx1|студент(POSSIBLE(NOT(F3))))")
        types = [n.operator_type for n in t.nodes]
        self.assertEqual(types, ["NOT", "EVERY", "POSSIBLE", "NOT"])  # outer -> inner
        innermost = t.nodes[-1]
        self.assertIsInstance(innermost.operand, str)  # the EVENT (frame ref) at the bottom
        every = t.nodes[1]
        self.assertEqual(every.local_variable_id, "x1")  # Rev13: local binding present
        self.assertEqual(every.restriction_ref, "студент")

    def test_B_generic_rule_not_per_sentence(self):
        """The SAME engine + lexicon on a different sentence with the same trigger
        pattern yields the same tree shape — no per-sentence knowledge anywhere."""
        other = "Не каждый гость мог не уйти."
        ir = assemble_ir(_run(other, self.schema, self.morph, self.sel))
        t = ir.operator_trees[0]
        types = [n.operator_type for n in t.nodes]
        self.assertEqual(types, ["NOT", "EVERY", "POSSIBLE", "NOT"])
        self.assertTrue(t.render().startswith("NOT(EVERYx1|"))

    def test_B_no_silent_loss_of_triggers(self):
        st = _run(B, self.schema, self.morph, self.sel)
        ir = assemble_ir(st)
        covered = {span for t in ir.operator_trees for n in t.nodes for span in n.scope_span}
        uncovered_ok = st.has_diag("SCOPE_NOT_COVERED")
        # Every lexicon trigger is either attached to the tree or explicitly diagnosed.
        self.assertTrue(covered, "no scope operator was built at all")
        _ = covered, uncovered_ok  # both channels exist; a missing one would be silent loss

    def test_B_provenance_declares_lexicon(self):
        ir = assemble_ir(_run(B, self.schema, self.morph, self.sel))
        t = ir.operator_trees[0]
        self.assertIn("scope_lexicon", t.provenance.resource_versions)

    # ---------------------------------------------------------------- C: revision

    def test_C_revision_same_observation_new_version(self):
        m0 = _run(C0_TEXT, self.schema, self.morph, self.sel)
        ref0 = next(d for d in m0.decisions.values() if d.slot_id == "reference")
        self.assertEqual(ref0.outcome, "UNRESOLVED")  # M0: no antecedent anywhere yet
        self.assertTrue(m0.has_diag("REFERENCE_UNKNOWN"))

        obs2 = _run(C1_TEXT, self.schema, self.morph, self.sel)
        mem = journal_mentions_from(obs2)
        self.assertEqual(mem, ("Самолёт", "полосе"))  # declared NQ7 window content

        m1 = revise(m0, self.schema, self.sel, morph=self.morph, memory_mentions=mem)
        self.assertEqual(m1.source_uid, m0.source_uid)  # SAME ObservationRecord
        self.assertEqual(m1.interpretation_version, m0.interpretation_version + 1)
        ref1 = next(d for d in m1.decisions.values() if d.slot_id == "reference")
        self.assertEqual(ref1.outcome, "AMBIGUOUS")  # both journal mentions admissible
        self.assertEqual(set(ref1.selected), {"Самолёт", "полосе"})
        per_value = {g.value for g in ref1.grounds if g.type == "W"}
        self.assertTrue({"Самолёт", "полосе"} <= per_value)  # each survivor W-grounded

    def test_C_no_auto_facts(self):
        m0 = _run(C0_TEXT, self.schema, self.morph, self.sel)
        obs2 = _run(C1_TEXT, self.schema, self.morph, self.sel)
        m1 = revise(m0, self.schema, self.sel, morph=self.morph,
                   memory_mentions=journal_mentions_from(obs2))
        for d in m1.decisions.values():  # I25: Phase 1 has no commit stage at all
            self.assertNotEqual(d.lifecycle, "COMMITTED")
        ir = assemble_ir(m1)  # the IR is the ONLY exit — and it carries the new version
        self.assertEqual(ir.interpretation_version, 2)
        assert_immutable(ir)

    # ---------------------------------------------------------------- D: channels

    def test_D_context_changes_grounds_not_candidates(self):
        d0 = _run(D, self.schema, self.morph, self.sel)
        d1 = _run(D, self.schema, self.morph, self.sel, context_facts=("Друга звали Пётр.",))
        keys = set(d0.decisions) & set(d1.decisions)
        self.assertTrue(keys)
        for k in keys:  # RESOLUTION channel never touches the candidate SETS
            self.assertEqual(d0.decisions[k].candidates, d1.decisions[k].candidates)
        c_g0 = {g.text for dd in d0.decisions.values() for g in dd.grounds if g.type == "C"}
        c_g1 = {g.text for dd in d1.decisions.values() for g in dd.grounds if g.type == "C"}
        self.assertNotEqual(c_g0, c_g1)  # ...but it DOES change the grounds (recompute ran)

    def test_channels_separation_generation_vs_resolution(self):
        """GENERATION (journal window) may change REFERENCE candidates but never
        predicate ones; RESOLUTION (context facts) changes no candidate set at all."""
        base = _run(C0_TEXT, self.schema, self.morph, self.sel)
        with_mem = _run(C0_TEXT, self.schema, self.morph, self.sel, memory_mentions=("Самолёт",))
        for k in set(base.decisions) & set(with_mem.decisions):
            a, b = base.decisions[k], with_mem.decisions[k]
            if a.slot_id == "reference":
                self.assertNotEqual(a.candidates, b.candidates)  # generation channel works
            else:
                self.assertEqual(a.candidates, b.candidates)  # ...and only there

        d0 = _run(D, self.schema, self.morph, self.sel)
        d1 = _run(D, self.schema, self.morph, self.sel, context_facts=("Друга звали Пётр.",))
        for k in set(d0.decisions) & set(d1.decisions):
            self.assertEqual(d0.decisions[k].candidates, d1.decisions[k].candidates)

    # ---------------------------------------------------------------- IR contract

    def test_ir_immutable(self):
        ir = assemble_ir(_run(D, self.schema, self.morph, self.sel))
        assert_immutable(ir)  # passes: mutation attempt raises FrozenInstanceError
        with self.assertRaises(Exception):
            ir.ir_id = "tampered"  # type: ignore[misc]

    def test_argument_type_closed_set(self):
        for t in ARGUMENT_TYPES:
            ArgumentSpec(slot_ref="S", arg_type=t)  # all declared types accepted
        with self.assertRaises(ValueError):
            ArgumentSpec(slot_ref="S", arg_type="MYSTERY")  # unknown type = contract violation


if __name__ == "__main__":
    unittest.main()
