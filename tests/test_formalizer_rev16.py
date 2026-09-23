# -*- coding: utf-8 -*-
"""Rev16 acceptance for the Phase 1 vertical (V5 §18.7, user list A-E).

RawInput -> T0 -> SRL -> T1 -> T2 -> TD -> [I30 closure] -> T3/T4.

Checks the deterministic contour WITHOUT an LLM:
- A: "Иван сказал Петя пришёл" — linked alternatives exist (A/B segmentations),
     no early embedded fact, nothing committed;
- B: "Машина была быстраяя." — keep-as-is admissible, no distance-based verdict;
- C/D: "Он взлетел." M0 -> UNRESOLVED + miss; M1 {птица} -> RESOLVED via memory
     evidence; M1 {птица, самолёт} -> AMBIGUOUS; the pair 'он = X' exists only
     inside a decision (no identity link before resolution);
- E: structural closure I30 — T3/T4 create no structure; missing structure is a
     diagnostic, not silent generation;
- provenance chain Raw token -> SRL candidate -> alternative -> Decision.
"""
import unittest

from ah.formalizer import pipeline
from ah.formalizer.fake_selector import FakeSelector
from ah.formalizer.pipeline import MorphProvider, t0, srl, t1, t2, td, t3, t4
from ah.formalizer.selection_protocol import load_decision_schema


def run_full(text, memory_mentions=(), morph=None):
    schema = load_decision_schema()
    return pipeline.run(
        text, schema, FakeSelector(), morph=morph or MorphProvider(),
        memory_mentions=memory_mentions,
    )


class TestA_LinkedAlternatives(unittest.TestCase):
    TEXT = "Иван сказал Петя пришёл"

    def setUp(self):
        self.state = run_full(self.TEXT)

    def test_a_segmentation_alternatives_exist(self):
        segs = {cc.segmentation for cc in self.state.clause_candidates}
        # Alternative A: Иван сказал | Петя пришёл ; B: Иван сказал Петя | пришёл
        self.assertIn(((0, 1), (2, 3)), segs)
        self.assertIn(((0, 2), (3, 3)), segs)
        self.assertIn(((0, 3),), segs)  # no-boundary default survives too

    def test_a_linked_alternatives_have_provenance(self):
        alts = [a for a in self.state.linked_alternatives if a.kind == "CLAUSE_SEGMENTATION"]
        self.assertGreaterEqual(len(alts), 3)
        for alt in alts:
            self.assertTrue(alt.provenance.pattern_ids, f"{alt.alt_id} lacks pattern provenance")

    def test_a_boundary_decision_unresolved(self):
        decs = [d for d in self.state.decisions.values() if d.slot_id == "boundary"]
        self.assertEqual(len(decs), 1)
        self.assertEqual(decs[0].outcome, "UNRESOLVED")
        self.assertEqual(decs[0].selected, ())

    def test_a_no_early_embedded_fact(self):
        # Phase 1: nothing is COMMITTED; the embedded proposition is not a fact.
        for dec in self.state.decisions.values():
            self.assertIn(dec.lifecycle, ("OPEN", "PROVISIONAL"))


class TestB_KeepAsIs(unittest.TestCase):
    TEXT = "Машина была быстраяя."

    def setUp(self):
        self.state = run_full(self.TEXT)

    def test_b_hypothesis_variants(self):
        hyps = [h for h in self.state.token_hypotheses if h.span_ref == "быстраяя"]
        self.assertEqual(len(hyps), 1)
        self.assertIn("keep_as_is", hyps[0].variants)
        self.assertIn("быстрая", hyps[0].variants)
        self.assertIn("L1_double_letter", hyps[0].provenance.pattern_ids)

    def test_b_keep_as_is_admissible_no_distance_verdict(self):
        dec = self.state.decisions["lex|быстраяя"]
        self.assertIn("keep_as_is", dec.candidates)  # first-class, not an error
        self.assertEqual(dec.selected, ("keep_as_is",))  # a PROVISIONAL decision...
        self.assertEqual(dec.lifecycle, "PROVISIONAL")  # ...not a correction verdict
        for d in self.state.diagnostics:
            self.assertNotIn("corrected", d.detail.lower())


class TestCD_Reference(unittest.TestCase):
    TEXT = "Он взлетел."

    def test_c_m0_unresolved_and_miss(self):
        st = run_full(self.TEXT, memory_mentions=())
        decs = [d for d in st.decisions.values() if d.slot_id == "reference"]
        self.assertEqual(len(decs), 1)
        self.assertEqual(decs[0].candidates, ())
        self.assertEqual(decs[0].outcome, "UNRESOLVED")
        self.assertTrue(st.has_diag("REFERENCE_UNKNOWN"))
        self.assertTrue(any("REFERENCE_UNKNOWN" in m for m in st.miss_reports))

    def test_d_single_memory_resolved(self):
        st = run_full(self.TEXT, memory_mentions=("птица",))
        dec = next(d for d in st.decisions.values() if d.slot_id == "reference")
        self.assertEqual(dec.candidates, ("птица",))
        self.assertEqual(dec.outcome, "RESOLVED")  # value-specific W ground on record
        w = [g for g in dec.grounds if g.type == "W" and g.value == "птица"]
        self.assertTrue(w)

    def test_d_two_memory_ambiguous(self):
        st = run_full(self.TEXT, memory_mentions=("птица", "самолёт"))
        dec = next(d for d in st.decisions.values() if d.slot_id == "reference")
        self.assertEqual(dec.candidates, ("птица", "самолёт"))
        self.assertEqual(dec.outcome, "AMBIGUOUS")  # every survivor grounded on its own evidence

    def test_no_pair_before_resolution(self):
        st = run_full(self.TEXT, memory_mentions=())
        rc = st.reference_candidates[0]
        self.assertEqual(rc.candidates, ())  # the candidate SET is empty...
        dec = next(d for d in st.decisions.values() if d.slot_id == "reference")
        self.assertEqual(dec.selected, ())   # ...and no 'он = X' pair exists anywhere
        for d in st.decisions.values():      # ...before resolution (I24)
            self.assertNotEqual(d.lifecycle, "COMMITTED")


class TestE_StructuralClosure(unittest.TestCase):
    TEXT = "Иван встретил Петра."

    def test_e_i30_t3t4_create_no_structure(self):
        schema = load_decision_schema()
        st = t0(self.TEXT)
        srl(st); t1(st); t2(st); td(st)
        before = (len(st.frames), len(st.clause_candidates), len(st.boundary_candidates),
                 len(st.ellipsis_candidates), len(st.missing_argument_candidates))
        st.close_structures()
        self.assertTrue(st.structural_closed)
        t3(st, schema, FakeSelector()); t4(st, schema)
        after = (len(st.frames), len(st.clause_candidates), len(st.boundary_candidates),
                 len(st.ellipsis_candidates), len(st.missing_argument_candidates))
        self.assertEqual(before, after)  # T3/T4 only DECIDE over existing objects

    def test_e_i30_guard_raises_after_closure(self):
        st = t0(self.TEXT)
        srl(st); t1(st); t2(st); td(st)
        st.close_structures()
        with self.assertRaises(RuntimeError):
            srl(st)  # creating structure after closure is a contract violation

    def test_e_missing_argument_candidate(self):
        st = run_full("Взял.")
        mas = st.missing_argument_candidates
        self.assertEqual(len(mas), 1)
        self.assertEqual(mas[0].status, "UNRESOLVED")
        self.assertIn("valency_check_v1", mas[0].provenance.pattern_ids)
        self.assertTrue(any("argument gap" in m for m in st.miss_reports))

    def test_e_ellipsis_candidate(self):
        st = run_full("Пётр тоже.")
        gaps = [g for g in st.ellipsis_candidates if g.kind == "PREDICATE_GAP"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("E1_predicate_gap", gaps[0].provenance.pattern_ids)


class TestSrlPurityAndProvenance(unittest.TestCase):
    TEXT = "Иван сказал Петя пришёл"

    def test_srl_creates_no_semantics(self):
        st = t0(self.TEXT)
        srl(st, morph=MorphProvider())
        self.assertEqual(st.reference_candidates, [])  # TD's job [H2]
        self.assertEqual(st.frames, [])               # T2's job; I30
        self.assertEqual(st.decisions, {})            # no decisions before T1/TD
        self.assertFalse(any(d.lifecycle == "COMMITTED" for d in st.decisions.values()))

    def test_provenance_chain(self):
        st = run_full(self.TEXT)
        bc = [b for b in st.boundary_candidates if "B1_new_predicative_center" in b.provenance.pattern_ids]
        self.assertTrue(bc)  # raw token -> SRL candidate (pattern + resource version)
        alt = next(a for a in st.linked_alternatives if a.source_candidate_id == f"S{bc[0].candidate_id}")
        self.assertTrue(alt.provenance.pattern_ids)   # -> linked alternative
        bdec = next(d for d in st.decisions.values() if d.slot_id == "boundary")
        self.assertTrue(bdec.provenance.pattern_ids)  # -> decision
        frame = st.frames[0]
        self.assertIn("grammar", frame.provenance.resource_versions)  # T2 resource versioning


if __name__ == "__main__":
    unittest.main()
