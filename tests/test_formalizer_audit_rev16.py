# -*- coding: utf-8 -*-
"""Rev16 implementation audit — acceptance tests for the 7 checkpoints (CP1-CP7).

Fixes verified here (no language expansion, architecture compliance only):
- CP1: SRL rules run through a declarative RuleRegistry; the core is a generic
       evaluator with no pattern knowledge; a NEW rule registers without touching it.
- CP2: TokenHypothesis is produced by the general variant mechanism (L1 as a
       registered rule); keep_as_is stays first-class; no special handler per error.
- CP3: TD builds candidates through declared channels {morphology, syntax, discourse,
       memory}; morphology is a hard filter with RECORDED rejections (D-trace).
       Acceptance: "Иван увидел Петра. Он улыбнулся." keeps BOTH alternatives.
- CP4: I30 guards EVERY structural producer (also covered in test_formalizer_rev16).
- CP5: trace_decision() reconstructs RawInput -> SRL candidates -> Frame -> Decision;
       rejected_alternatives() returns the I29 audit trail with reasons.
- CP6: MissingArgument is a three-state machine (POSSIBLE_GAP/CONFIRMED_GAP/NO_GAP).
- CP7: M0/M1/M2 — context influence changes outcomes ONLY through recorded evidence.
"""
import inspect
import unittest

from ah.formalizer import pipeline
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.pipeline import (
    MorphProvider,
    rejected_alternatives,
    run,
    srl,
    t0,
    trace_decision,
)
from ah.formalizer.rules import StructuralRule, default_registry
from ah.formalizer.selection_protocol import load_decision_schema
from ah.formalizer.state import (
    BoundaryCandidate,
    MA_STATES,
    MissingArgumentCandidate,
    ResourceProvenance,
)

SCHEMA = load_decision_schema()


def run_full(text, memory_mentions=(), mode="baseline"):
    return run(
        text, SCHEMA, FakeSelector.demo(mode), morph=MorphProvider(),
        memory_mentions=tuple(memory_mentions),
    )


class TestCP1_SrlRuleRegistry(unittest.TestCase):
    """SRL rules go through a declarative registry; the core is generic."""

    def test_default_registry_is_declared_data(self):
        reg = default_registry()
        self.assertEqual(
            [r.rule_id for r in reg.rules],
            ["L1_double_letter", "B1_new_predicative_center", "E1_predicate_gap"],
        )
        for rule in reg.rules:  # every rule is data with a description and provenance hook
            self.assertTrue(rule.description)

    def test_srl_output_patterns_come_only_from_registry(self):
        st = run_full("Иван сказал Петя пришёл")
        fired = set()
        for obj in (*st.token_hypotheses, *st.boundary_candidates, *st.ellipsis_candidates):
            fired.update(obj.provenance.pattern_ids)
        registry_ids = {r.rule_id for r in default_registry().rules} | {"B0_no_boundary"}
        self.assertTrue(fired)  # B1 actually fires on this input
        self.assertTrue(fired <= registry_ids, f"unknown patterns: {fired - registry_ids}")

    def test_srl_core_contains_no_pattern_knowledge(self):
        src = inspect.getsource(srl)
        for literal in ("double_letter", "predicate_gap", "predicative_center", "INFN"):
            self.assertNotIn(literal, src, f"SRL core must not know pattern '{literal}'")

    def test_new_rule_registers_without_touching_core(self):
        # A declared NEW rule (test-local) is picked up by the unchanged generic loop.
        reg = default_registry().register(StructuralRule(
            "X1_test_boundary", "audit-only: boundary before every token",
            activate=lambda evs, parses: True,
            produce=lambda state, evs, parses: [BoundaryCandidate(
                candidate_id=f"X{i}", position=i, kind="CLAUSE_BOUNDARY",
                evidence=["audit rule X1"], provenance=ResourceProvenance(pattern_ids=("X1_test_boundary",)),
            ) for i in range(len(evs))],
        ))
        st = t0("Взял.")
        srl(st, morph=MorphProvider(), registry=reg)
        self.assertTrue(any(bc.provenance.pattern_ids == ("X1_test_boundary",)
                            for bc in st.boundary_candidates))


class TestCP2_TokenHypothesisGeneralMechanism(unittest.TestCase):

    def test_l1_variants_via_registry_keep_as_is_first_class(self):
        st = run_full("Машина была быстраяя.")
        hyps = [h for h in st.token_hypotheses if "быстраяя" in h.span_ref]
        self.assertEqual(len(hyps), 1)
        self.assertEqual(hyps[0].variants[0], "keep_as_is")  # first-class, not a fallback
        self.assertIn("L1_double_letter", hyps[0].provenance.pattern_ids)

    def test_no_special_handler_per_error(self):
        # The only orthographic mechanism is the registered L1 rule; nothing in the
        # pipeline core special-cases a concrete error or a concrete word.
        src = inspect.getsource(pipeline.srl) + inspect.getsource(pipeline.t1)
        self.assertNotIn("быстраяя", src)
        self.assertNotIn("dedup(", src)


class TestCP3_TdEvidenceChannels(unittest.TestCase):

    def test_acceptance_both_alternatives_survive(self):
        st = run_full("Иван увидел Петра. Он улыбнулся.")
        decs = [d for d in st.decisions.values() if d.slot_id == "reference"]
        self.assertEqual(len(decs), 1)
        dec = decs[0]
        # Morphology (masc/sing agreement) keeps BOTH Иван and Пётр -> proven ambiguity.
        self.assertEqual(dec.outcome, "AMBIGUOUS")
        self.assertIn("Иван", dec.selected)
        self.assertIn("Петра", dec.candidates)  # surface span of the second alternative
        # Linked alternatives stay addressable (I29): nothing deleted silently.
        self.assertTrue(st.linked_alternatives)
        cats = {cat for cat, _ in st.reference_candidates[0].evidence}
        self.assertTrue({"morphology", "syntax", "discourse"} <= cats)

    def test_morphology_filter_rejects_with_recorded_reason(self):
        st = run_full("Иван увидел собаку. Он улыбнулся.")
        decs = [d for d in st.decisions.values() if d.slot_id == "reference"]
        self.assertEqual(len(decs), 1)
        dec = decs[0]
        self.assertEqual(dec.outcome, "RESOLVED")  # only the masc candidate survives
        self.assertEqual(dec.selected, ("Иван",))
        rejs = rejected_alternatives(st)
        dog = [r for r in rejs if "собак" in r.candidate_id]  # root matches acc. 'собаку'
        self.assertTrue(dog, f"rejection not recorded: {rejs}")
        self.assertIn("coref_policy_v1", dog[0].reason)  # D-trace names the declared rule
        self.assertEqual(dog[0].stage, "TD")


class TestCP5_ProvenanceGraph(unittest.TestCase):

    def test_trace_reconstructs_chain_to_decision(self):
        st = run_full("У вороны есть лапки.", mode="augmented")
        keys = [k for k, d in st.decisions.items() if d.slot_id == "predicate_value"]
        self.assertTrue(keys)
        chain = trace_decision(st, keys[0])
        kinds = [kind for kind, _, _ in chain]
        self.assertEqual(chain[-1][0], "Decision")  # ends at the decision...
        self.assertIn("FrameCandidate", kinds)      # ...through the frame...
        self.assertTrue(any(k == "TokenEvidence" for k in kinds))  # ...to raw tokens.
        # Phase 1 honesty: SemanticGraphCandidate/Canonical Memory do not exist yet (I25).
        self.assertNotIn("SemanticGraphCandidate", kinds)

    def test_rejected_alternatives_carry_reasons(self):
        st = run_full("Иван увидел собаку. Он улыбнулся.")
        for rec in rejected_alternatives(st):
            self.assertTrue(rec.reason, "a rejection without a reason is an audit violation")
            self.assertTrue(rec.stage)


class TestCP6_MissingArgumentStates(unittest.TestCase):

    def test_three_state_machine(self):
        self.assertEqual(MA_STATES, ("POSSIBLE_GAP", "CONFIRMED_GAP", "NO_GAP"))
        st = run_full("Взял.")
        self.assertEqual(len(st.missing_argument_candidates), 1)
        self.assertEqual(st.missing_argument_candidates[0].status, "POSSIBLE_GAP")

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError):
            MissingArgumentCandidate(candidate_id="x", frame_ref="F0", status="UNRESOLVED")


class TestCP7_ContextInfluenceViaEvidenceOnly(unittest.TestCase):
    """M0/M1/M2: the SAME input under different memory contexts. Outcome differences
    must be fully explained by recorded value-specific grounds — no hidden rules."""

    TEXT = "Он взлетел."

    def _ref(self, st):
        decs = [d for d in st.decisions.values() if d.slot_id == "reference"]
        self.assertEqual(len(decs), 1)
        return decs[0]

    def test_m0_unresolved_without_memory(self):
        st = run_full(self.TEXT, memory_mentions=())
        dec = self._ref(st)
        self.assertEqual(dec.outcome, "UNRESOLVED")
        self.assertEqual(dec.candidates, ())  # nothing admissible — and NOTHING hidden:
        self.assertFalse([g for g in dec.grounds if g.type == "W"])

    def test_m1_resolved_via_recorded_memory_ground(self):
        st = run_full(self.TEXT, memory_mentions=("птица",))
        dec = self._ref(st)
        self.assertEqual(dec.outcome, "RESOLVED")
        self.assertEqual(dec.selected, ("птица",))
        w = [g for g in dec.grounds if g.type == "W" and g.value == "птица"]
        self.assertTrue(w, "the outcome must rest on a recorded W ground")

    def test_m2_ambiguous_every_survivor_grounded(self):
        st = run_full(self.TEXT, memory_mentions=("птица", "самолёт"))
        dec = self._ref(st)
        self.assertEqual(dec.outcome, "AMBIGUOUS")
        for v in dec.selected:  # every survivor has its OWN value-specific ground
            self.assertTrue([g for g in dec.grounds if g.type == "W" and g.value == v], v)

    def test_difference_explained_by_evidence_only(self):
        m0, m1 = run_full(self.TEXT), run_full(self.TEXT, memory_mentions=("птица",))
        self.assertNotEqual(self._ref(m0).outcome, self._ref(m1).outcome)
        # The ONLY difference between the runs is the declared journal window; every
        # candidate in M1 carries a W ground naming it — no unrecorded influence.
        for v in self._ref(m1).selected:
            self.assertTrue([g for g in self._ref(m1).grounds if g.value == v])


if __name__ == "__main__":
    unittest.main()
