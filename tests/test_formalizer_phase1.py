# -*- coding: utf-8 -*-
"""Phase 1 acceptance (V4 freeze rev2-8): the formalizer MECHANISM works without an LLM.

FakeSelector stands in for the bounded-selection backend; every test asserts mechanism
invariants, not model quality:
- T3 selections are PROVISIONAL; a semantic outcome is granted by T4 only (RESOLVED != COMMITTED);
  the validator itself grants NOTHING — it returns a verified protocol outcome only;
- RESOLVED requires a VALUE-SPECIFIC positive ground + completed search + cluster validity
  (§T4 rev8): slot-level grounds license the slot but ground no individual candidate;
- declared contextual statements are C grounds with visible provenance — no self-legalizing A;
  an augmented script may rely on a statement only if it is DECLARED in the prompt (anti-forgery);
- M is an admissible choice ground bound to its value, but repeating an identical M adds no
  evidentiality: oscillation freezes only on STATE REPETITION without new R/C/D/A CONTENT;
- protocol errors / provider outages are computational diagnostics — one budget charge per
  attempt, never accepted downstream (C3), never negative R-X experience;
- word order ranks but never excludes (T2 invariance); OOV is a first-class keep-as-is candidate.

Reference: docs/PILOT_DEMO_REFERENCES_V1.md (frozen v1), S1-S6.
"""
from __future__ import annotations

import json
import re
import unittest

from ah.formalizer.fake_selector import FakeSelector, ProviderUnavailableError  # noqa: F401
from ah.formalizer.pipeline import (
    MorphProvider,
    OscillationDetector,
    _slot_key,
    bounded_search,
    run,
    t0,
    t1,
    t2,
    t3,
    t4,
)
from ah.formalizer.selection_protocol import load_decision_schema, validate_selection_response
from ah.formalizer.state import Budget, ConstraintEdge, Decision, Ground, MorphVariant

SCHEMA = load_decision_schema()

S1 = "У вороны есть лапки."
S2 = "У стола есть ножки."
S3 = "У меня есть книга."
S4 = "Ворона обладает перьями."
S5 = "У вороны лапки."
S6 = "Вороны любят червей."

# Declared contextual statements (C grounds). The baseline run passes NONE of them:
# default pragmatic linkage is not a dictionary consequence and must not be smuggled in.
F1 = ("Лапки — часть тела этой вороны.",)
F2 = ("Ножки — часть этого стола.",)
F3 = ("Перья — часть тела этой вороны.",)


def value_dec(state):
    """The predicate-value decision of the first FLAT frame (demo sentences have one)."""
    for key, dec in state.decisions.items():
        if dec.slot_id == "predicate_value":
            return dec
    raise AssertionError("no predicate_value decision")


class StubMorph:
    """Deterministic morphology stub: tests T1/T2 contracts without dictionary quality.

    Returns WHOLE variants (linked features stay linked); the union index is derived."""

    def __init__(self, table: dict[str, tuple]):
        self.table = table  # token -> ((lemma, pos, case), ...) whole parses

    def analyze(self, token):
        row = self.table.get(token)
        if row is None:
            return ()  # OOV by construction
        out = []
        for (l, p, c) in row:
            out.append(MorphVariant(
                lemma=l, pos=p, cases=frozenset({c}) if c else frozenset(), score=0.9,
            ))
        return tuple(out)


class Phase1MechanismTest(unittest.TestCase):
    def test_s1_baseline_honest_unresolved_c2(self):
        st = run(S1, SCHEMA, FakeSelector.demo("baseline"))  # no contextual statements
        dec = value_dec(st)
        self.assertEqual(dec.lifecycle, "PROVISIONAL")  # T3 selection is provisional
        self.assertEqual(set(dec.selected), {"V1", "V2"})
        self.assertEqual(dec.outcome, "UNRESOLVED")  # honest {V1,V2} -> C2 material (rev7b)
        self.assertTrue(st.has_diag("NO_GROUNDED_CANDIDATE"))
        self.assertNotEqual(dec.outcome, "RESOLVED")  # no wrong commit (C3) in baseline

    def test_s1_augmented_resolved_not_committed(self):
        st = run(S1, SCHEMA, FakeSelector.demo("augmented"), context_facts=F1)
        dec = value_dec(st)
        self.assertEqual(dec.selected, ("V2",))
        self.assertEqual(dec.outcome, "RESOLVED")  # granted by T4 joint validation
        self.assertEqual(dec.lifecycle, "PROVISIONAL")  # RESOLVED != COMMITTED (T5 grants it)

    def test_s1_augmented_provenance_is_explicit(self):
        """rev7b/8: the deciding input is a DECLARED contextual statement; its C ground and
        the M trace are visible on the decision — no invisible assumption."""
        st = run(S1, SCHEMA, FakeSelector.demo("augmented"), context_facts=F1)
        dec = value_dec(st)
        c_texts = [g.text for g in dec.grounds if g.type == "C"]
        self.assertTrue(any(F1[0] in t for t in c_texts), f"context statement missing: {c_texts}")
        m_grounds = [g for g in dec.grounds if g.type == "M"]
        self.assertEqual(len(m_grounds), 1)
        self.assertIn("V2", m_grounds[0].text)  # recorded output of the bounded selection

    def test_s1_augmented_io_is_recorded_and_replayable(self):
        """rev8 (D3): the M ground is a RECORDED judgment — prompt and raw response are
        stored on the decision; replaying the raw response through the validator
        reproduces the same pick, and the declared statement appears in the prompt verbatim."""
        st = run(S1, SCHEMA, FakeSelector.demo("augmented"), context_facts=F1)
        dec = value_dec(st)
        self.assertIsNotNone(dec.last_prompt)
        self.assertIn(F1[0], dec.last_prompt)  # declared input visible in the prompt verbatim
        replayed = validate_selection_response(
            dec.raw_response, SCHEMA, allowed=frozenset(dec.candidates))
        self.assertEqual(replayed.selected, dec.selected)  # I/O trace is replayable

    def test_augmented_script_cannot_forge_undeclared_context(self):
        """rev8 (D3 anti-forgery): the augmented S1 script requires F1 to be DECLARED in
        the prompt. Without context_facts it degrades to the baseline behavior — an
        UNRESOLVED {V1,V2}, never a RESOLVED V2."""
        st = run(S1, SCHEMA, FakeSelector.demo("augmented"))  # NO context_facts!
        dec = value_dec(st)
        self.assertEqual(set(dec.selected), {"V1", "V2"})
        self.assertEqual(dec.outcome, "UNRESOLVED")

    def test_s3_resolved_by_textual_ground_not_assumption(self):
        """rev7b/8: S3 resolves in BASELINE (no contextual statement) — possession needs no
        assumption; provenance is the M trace bound to its value (recorded I/O)."""
        st = run(S3, SCHEMA, FakeSelector.demo("baseline"))  # NO context_facts
        d3 = value_dec(st)
        self.assertEqual(d3.selected, ("V1",))
        self.assertEqual(d3.outcome, "RESOLVED")
        m_grounds = [g for g in d3.grounds if g.type == "M"]
        self.assertEqual(len(m_grounds), 1)
        self.assertEqual(m_grounds[0].value, "V1")  # the trace is bound to its value (rev8)
        self.assertIn("book", m_grounds[0].text)  # the textual ground is visible, not implicit

    def test_s2_s4_transfer(self):
        st2b = run(S2, SCHEMA, FakeSelector.demo("baseline"))
        self.assertEqual(value_dec(st2b).outcome, "UNRESOLVED")  # C2 material as in S1
        st4a = run(S4, SCHEMA, FakeSelector.demo("augmented"), context_facts=F3)
        d4 = value_dec(st4a)
        self.assertEqual(d4.selected, ("V2",))
        self.assertEqual(d4.outcome, "RESOLVED")  # out-of-construction transfer (S4)

    def test_s5_ellipsis_is_mechanism_not_record(self):
        st1 = run(S1, SCHEMA, FakeSelector.demo("baseline"))
        st5 = run(S5, SCHEMA, FakeSelector.demo("baseline"))
        f1 = next(f for f in st1.frames if f.kind == "FLAT")
        f5 = next(f for f in st5.frames if f.kind == "FLAT")
        self.assertFalse(f1.copula_ellipsis)  # copula present (есть)
        self.assertTrue(f5.copula_ellipsis)  # ellipsis detected by mechanism, not pre-tasked
        self.assertEqual(f5.construction, f1.construction)  # same structural pattern u+GEN+NOM
        d1, d5 = value_dec(st1), value_dec(st5)
        self.assertEqual(set(d1.candidates), set(d5.candidates))  # identical candidate space
        self.assertEqual(d5.outcome, "UNRESOLVED")  # honest {HAVE, HAS_PART} -> C2 material

    def test_s6_negative_control_d2(self):
        st6 = run(S6, SCHEMA, FakeSelector.demo("baseline"))
        d6 = value_dec(st6)
        self.assertEqual(d6.selected, ("V4",))
        self.assertIn("V4", d6.candidates)  # rev8 (D1): V4 is in the decision's declared set
        self.assertEqual(d6.outcome, "RESOLVED")  # LIKE — attitude relation
        m_text = next(g.text for g in d6.grounds if g.type == "M")
        self.assertIn("attitude verb", m_text)  # provenance visible (rev7b)
        readings = set()
        for text, mode, facts in ((S1, "baseline", ()), (S2, "baseline", ()),
                                  (S3, "baseline", ()), (S4, "augmented", F3),
                                  (S5, "baseline", ())):
            st = run(text, SCHEMA, FakeSelector.demo(mode), context_facts=facts)
            d = value_dec(st)
            if d.outcome == "RESOLVED":
                readings.update(d.selected)
        self.assertNotIn("V4", readings)  # D2: S6 reading distinct from all of S1-S5

    def test_candidates_come_from_schema_rule_not_hardcode(self):
        """rev8 (D1): the decision's candidate set is derived from the schema's declared
        candidate_generation rule (all relations minus provable arity mismatch) — not a
        hardcoded pair. All four demo relations are binary, so all four are candidates."""
        st = run(S6, SCHEMA, FakeSelector.demo("baseline"))
        d6 = value_dec(st)
        self.assertEqual(set(d6.candidates), {"V1", "V2", "V3", "V4"})

    def test_out_of_set_refusal_is_no_candidate_with_miss_report(self):
        st = run("Кот спит.", SCHEMA, FakeSelector.demo("baseline"))  # unscripted -> NONE_FIT
        dec = value_dec(st)
        self.assertEqual(dec.outcome, "NO_CANDIDATE")
        self.assertTrue(st.miss_reports)  # miss report recorded (demo boundary, not silent mapping)

    def test_invalid_response_never_accepted_and_charged_once(self):
        sel = FakeSelector.demo("baseline")
        sel.scripts[("predicate_value", S1)] = ("INVALID", '{"outcome": "ONE_SELECTED", "selected": ["V9"]}')
        st = run(S1, SCHEMA, sel)
        dec = value_dec(st)
        self.assertTrue(st.has_diag("PROTOCOL_ERROR"))  # rejected call, counted in budget
        self.assertEqual(st.budget.llm_calls, 1)  # rev8 (D5): exactly ONE charge per attempt
        self.assertEqual(st.budget.llm_failed, 1)
        self.assertEqual(dec.lifecycle, "OPEN")  # never accepted downstream (accepting would be C3)
        self.assertIsNone(dec.outcome)

    def test_malformed_json_is_protocol_error(self):
        sel = FakeSelector.demo("baseline")
        sel.scripts[("predicate_value", S1)] = ("INVALID", "{not json at all")
        st = run(S1, SCHEMA, sel)
        self.assertTrue(st.has_diag("PROTOCOL_ERROR"))
        self.assertEqual(value_dec(st).lifecycle, "OPEN")

    def test_provider_unavailable_is_diagnostic_charged_once(self):
        sel = FakeSelector.demo("baseline")
        sel.scripts[("predicate_value", S1)] = "PROVIDER_UNAVAILABLE"
        st = run(S1, SCHEMA, sel)
        dec = value_dec(st)
        self.assertTrue(st.has_diag("PROVIDER_UNAVAILABLE"))
        self.assertEqual(st.budget.llm_calls, 1)  # rev8 (D5): no double charge on failure
        self.assertEqual(dec.lifecycle, "OPEN")
        self.assertIsNone(dec.outcome)  # not AMBIGUOUS, not NO_CANDIDATE: computational, not semantic

    def test_budget_exhausted_keeps_decision_open(self):
        st = run(S1, SCHEMA, FakeSelector.demo("baseline"), budget=Budget(llm_limit=0))
        dec = value_dec(st)
        self.assertTrue(st.has_diag("BUDGET_EXHAUSTED"))
        self.assertEqual(dec.lifecycle, "OPEN")  # honest: no probe was made; not NO_CANDIDATE

    def test_search_incomplete_under_tiny_budget(self):
        budget = Budget(llm_limit=8, search_step_limit=3)
        sols, complete, pos = bounded_search({"a": [1, 2], "b": [1, 2]}, [], budget)
        self.assertFalse(complete)  # space NOT exhausted: absence of a solution is not proven

    def test_bounded_search_continuation_does_not_repay(self):
        """rev8 (D5): the traversal position is resumable — continuing from it charges only
        the REMAINING steps; total cost across runs equals the single-run cost."""
        domains = {s: [0, 1] for s in ("a", "b", "c", "d")}  # full space: 30 leaf/branch steps

        def full_cost() -> int:
            b = Budget(llm_limit=8, search_step_limit=10_000)
            sols, complete, _ = bounded_search(domains, [], b)
            assert complete and len(sols) == 16
            return b.search_steps

        cost_full = full_cost()
        b1 = Budget(llm_limit=8, search_step_limit=5)
        sols1, done1, pos = bounded_search(domains, [], b1)
        self.assertFalse(done1)
        b2 = Budget(llm_limit=8, search_step_limit=10_000)
        sols2, done2, _ = bounded_search(domains, [], b2, position=pos)  # continuation
        self.assertTrue(done2)
        self.assertEqual(len(sols1) + len(sols2), 16)  # the split covers the whole space...
        self.assertEqual(b1.search_steps + b2.search_steps, cost_full)  # ...no step paid twice

    def test_uniqueness_at_t3_is_not_resolved(self):
        st = t0(S3)
        t1(st)
        t2(st)
        t3(st, SCHEMA, FakeSelector.demo("baseline"))
        dec = value_dec(st)
        self.assertEqual(dec.selected, ("V1",))  # unique pick at T3...
        self.assertIsNone(dec.outcome)  # ...still grants nothing: RESOLVED is a T4 act
        t4(st, SCHEMA)
        self.assertEqual(dec.outcome, "RESOLVED")

    def test_oov_keep_as_is_is_first_class_candidate(self):
        morph = StubMorph({"Кот": (("кот", "NOUN", "nom"),)})  # 'Xyzzy' is OOV by construction
        st = t0("Кот Xyzzy.")
        t1(st, morph=morph)
        lex = st.decisions.get("lex|Xyzzy")
        self.assertIsNotNone(lex)
        self.assertEqual(lex.selected, ("keep_as_is",))  # keep-as-is is a decision, not an error
        self.assertTrue(any(g.type == "D" for g in lex.grounds))
        self.assertTrue(st.has_diag("OOV_KEEP_AS_IS"))

    def test_t1_keeps_whole_variants_union_is_index_only(self):
        """rev7b/8: linked features stay inside a variant; the case union is an index.
        A token with two parses (NOUN nom / NOUN gen) keeps BOTH variants intact."""
        morph = StubMorph({"Вороны": (("ворона", "NOUN", "nom"), ("ворона", "NOUN", "gen"))})
        st = t0("Вороны.")
        t1(st, morph=morph)
        ev = st.evidence[0]
        self.assertEqual(len(ev.variants), 2)  # nothing dropped by a score cutoff
        self.assertEqual({(v.lemma, v.pos, tuple(sorted(v.cases))) for v in ev.variants},
                         {("ворона", "NOUN", ("nom",)), ("ворона", "NOUN", ("gen",))})
        self.assertEqual(ev.cases, frozenset({"nom", "gen"}))  # derived index

    def test_t1_variant_carries_full_feature_set(self):
        """rev8 (D4): a variant carries number/gender/person/tense/mood and the remaining
        tagset features (e.g. SUBX) — not just lemma/POS/case."""
        morph = StubMorph({"Вороны": (("ворона", "NOUN", "nom"),)})
        st = t0("Вороны.")
        t1(st, morph=morph)
        v = st.evidence[0].variants[0]
        for attr in ("number", "gender", "person", "tense", "mood", "features"):
            self.assertTrue(hasattr(v, attr))  # the fields exist on every variant

    def test_shared_form_rule_expands_variant_not_index(self):
        """rev8 (D4): -ами/-ями shared form. The correction expands the VARIANT's own case
        set; the index gains 'ins' only because a variant now supports it."""
        morph = StubMorph({"перьями": (("перо", "NOUN", "abl"),)})  # dictionary under-tags: abl only
        st = t0("Ворона обладает перьями.")
        t1(st, morph=morph)
        ev = next(e for e in st.evidence if e.span == "перьями")
        self.assertEqual(ev.variants[0].cases, frozenset({"abl", "ins"}))  # variant corrected
        self.assertEqual(ev.cases, frozenset({"abl", "ins"}))  # index = strict derivation

    def test_t2_word_order_ranks_but_never_excludes(self):
        table = {
            "Вороны": (("ворона", "NOUN", "nom"),),
            "вороны": (("ворона", "NOUN", "nom"),),
            "любят": (("любить", "VERB", None),),
            "Любят": (("любить", "VERB", None),),
            "червей": (("червь", "NOUN", "acc"),),
        }
        morph = StubMorph(table)

        def frames_of(text):
            st = t0(text)
            t1(st, morph=morph)
            return t2(st).frames

        f_orig = [f for f in frames_of("Вороны любят червей.") if f.kind == "FLAT"]
        f_inv = [f for f in frames_of("Любят вороны червей.") if f.kind == "FLAT"]  # inversion
        self.assertEqual(len(f_orig), 1)
        self.assertEqual(len(f_inv), 1)
        a, b = f_orig[0], f_inv[0]

        def core(s: str) -> str:  # canonical identity: strip punctuation and case
            return re.sub(r"[^0-9A-Za-zА-Яа-яЁё]", "", s).lower()

        self.assertEqual(a.construction, b.construction)  # same candidate space...
        self.assertEqual({core(x) for x in a.participants}, {core(x) for x in b.participants})
        self.assertEqual({core(x) for x in a.arguments}, {core(x) for x in b.arguments})

    def test_nonflat_frame_is_declared_not_silently_skipped(self):
        """rev8 (D6): OP4/OP5 are declared stubs — T3 records STRUCTURE_NOT_COVERED for a
        COORD frame instead of skipping it silently."""
        morph = StubMorph({
            "Вороны": (("ворона", "NOUN", "nom"),),
            "и": (("и", "CONJ", None),),
            "вороны": (("ворона", "NOUN", "nom"),),
        })
        st = t0("Вороны и вороны.")
        t1(st, morph=morph)
        t2(st)
        self.assertTrue(any(f.kind == "COORD" for f in st.frames))  # OP5 stub detected it
        t3(st, SCHEMA, FakeSelector.demo("baseline"))
        self.assertTrue(st.has_diag("STRUCTURE_NOT_COVERED"))

    def test_single_flip_is_not_oscillation(self):
        """rev7b/8: one change of value (V1 -> V2) is NOT a cycle; only STATE REPETITION
        without new R/C/D/A grounds freezes."""
        det = OscillationDetector()
        self.assertEqual(det.record("slot", "V1", ()), "accepted")  # first selection
        self.assertEqual(det.record("slot", "V2", (Ground("M", "trace"),)), "accepted")
        self.assertNotIn("slot", det.frozen)

    def test_same_value_repeat_without_change_is_not_oscillation(self):
        """rev8 (D5): a repeat of the SAME value with unchanged grounds is idempotent
        re-confirmation — accepted, not frozen."""
        det = OscillationDetector()
        self.assertEqual(det.record("slot", "V1", ()), "accepted")
        self.assertEqual(det.record("slot", "V1", (Ground("M", "trace"),)), "accepted")  # M is a trace
        self.assertNotIn("slot", det.frozen)

    def test_state_repetition_without_new_grounds_freezes(self):
        det = OscillationDetector()
        det.record("slot", "V1", ())
        det.record("slot", "V2", (Ground("M", "trace"),))  # M is a trace, not a new ground
        self.assertEqual(det.record("slot", "V1", (Ground("M", "trace"),)), "frozen")  # back to V1 state
        self.assertIn("slot", det.frozen)
        self.assertEqual(det.record("slot", "V2", (Ground("M", "trace"),)), "frozen")  # M-only never unfreezes
        self.assertEqual(det.record("other", "X", ()), "accepted")  # other slots unaffected

    def test_new_ground_content_rearms_after_freeze(self):
        """rev8 (D5): the signature compares ground CONTENT, not type letters. New R/C/D/A
        content after a freeze is legitimate re-selection — it re-arms the slot."""
        det = OscillationDetector()
        det.record("slot", "V1", ())
        det.record("slot", "V2", (Ground("M", "trace"),))
        self.assertEqual(det.record("slot", "V1", (Ground("M", "trace"),)), "frozen")
        new_r = Ground("R", "new dictionary evidence for V1")
        self.assertEqual(det.record("slot", "V1", (new_r,)), "rearmed")  # new CONTENT: legitimate
        self.assertNotIn("slot", det.frozen)

    def test_no_positive_grounds_never_resolved(self):
        """rev7/8: RESOLVED requires a value-specific positive ground for the SELECTED value.
        A unique pick with NO grounds at all is UNRESOLVED + diagnostic — never AMBIGUOUS."""
        st = t0(S1)
        t1(st)
        t2(st)
        frame = next(f for f in st.frames if f.kind == "FLAT")
        dec = Decision(slot_id="predicate_value", frame_id=frame.frame_id, candidates=("V1", "V2"))
        dec.selected = ("V1",)  # unique pick...
        dec.selector_outcome = "ONE_SELECTED"
        dec.lifecycle = "PROVISIONAL"
        st.decisions[_slot_key(frame.frame_id, "predicate_value")] = dec  # no grounds at all
        t4(st, SCHEMA)
        self.assertEqual(dec.outcome, "UNRESOLVED")
        self.assertTrue(st.has_diag("NO_GROUNDED_CANDIDATE"))

    def test_slot_level_grounds_no_individual_value(self):
        """rev8 (D2): a slot-level ground (value=None) licenses the slot but grounds no
        individual candidate. A unique pick supported only by slot-level grounds is UNRESOLVED."""
        st = t0(S1)
        t1(st)
        t2(st)
        frame = next(f for f in st.frames if f.kind == "FLAT")
        dec = Decision(slot_id="predicate_value", frame_id=frame.frame_id, candidates=("V1", "V2"))
        dec.selected = ("V1",)
        dec.selector_outcome = "ONE_SELECTED"
        dec.lifecycle = "PROVISIONAL"
        dec.grounds.append(Ground("C", "construction u+GEN+NOM licenses the slot"))  # value=None!
        st.decisions[_slot_key(frame.frame_id, "predicate_value")] = dec
        t4(st, SCHEMA)
        self.assertEqual(dec.outcome, "UNRESOLVED")

    def test_ambiguous_requires_per_value_positive_grounds(self):
        """§1.4: AMBIGUOUS is proven ambiguity — EVERY survivor needs its own value-specific
        positive ground. A slot-level trace (MULTIPLE_ADMISSIBLE) grounds no value."""
        st = t0(S1)
        t1(st)
        t2(st)
        frame = next(f for f in st.frames if f.kind == "FLAT")
        dec = Decision(slot_id="predicate_value", frame_id=frame.frame_id, candidates=("V1", "V2"))
        dec.selected = ("V1", "V2")
        dec.selector_outcome = "MULTIPLE_ADMISSIBLE"
        dec.lifecycle = "PROVISIONAL"
        dec.grounds.append(Ground("C", "construction u+GEN+NOM licenses the slot"))  # slot-level
        st.decisions[_slot_key(frame.frame_id, "predicate_value")] = dec
        t4(st, SCHEMA)
        self.assertEqual(dec.outcome, "UNRESOLVED")  # slot-level ground grounds no value
        # Now each survivor gets its own positive admissibility ground (e.g. from R-S):
        dec.grounds.append(Ground("R", "dictionary: 'есть' + GEN -> HAVE admissible", value="V1"))
        dec.grounds.append(Ground("R", "part-whole reading admissible for body terms", value="V2"))
        t4(st, SCHEMA)
        self.assertEqual(dec.outcome, "AMBIGUOUS")  # proven ambiguity

    def test_m_bound_to_value_is_admissible_ground(self):
        """rev7b/8: M (recorded model judgment with I/O) IS a positive ground — but only when
        bound to the value it supports. An unbound slot-level trace grounds nothing."""
        st = t0(S1)
        t1(st)
        t2(st)
        frame = next(f for f in st.frames if f.kind == "FLAT")
        dec = Decision(slot_id="predicate_value", frame_id=frame.frame_id, candidates=("V1", "V2"))
        dec.selected = ("V1",)
        dec.selector_outcome = "ONE_SELECTED"
        dec.lifecycle = "PROVISIONAL"
        dec.grounds.append(Ground("M", "selector chose ['V1']; note: recorded I/O trace", value="V1"))
        st.decisions[_slot_key(frame.frame_id, "predicate_value")] = dec
        t4(st, SCHEMA)
        self.assertEqual(dec.outcome, "RESOLVED")  # M bound to its value is admissible

    def test_cluster_constraint_edge_is_enforced(self):
        """rev8 (D2): T4 cluster validity is REAL — a declared ConstraintEdge between two
        decisions of the same cluster vetoes the forbidden value pair."""
        st = t0(S1)
        t1(st)
        t2(st)
        frame = next(f for f in st.frames if f.kind == "FLAT")
        key = _slot_key(frame.frame_id, "predicate_value")
        dec = Decision(slot_id="predicate_value", frame_id=frame.frame_id, candidates=("V1", "V2"))
        dec.selected = ("V1",)
        dec.selector_outcome = "ONE_SELECTED"
        dec.lifecycle = "PROVISIONAL"
        dec.grounds.append(Ground("M", "trace", value="V1"))
        st.decisions[key] = dec
        other_key = _slot_key(frame.frame_id, "other_slot")
        other = Decision(slot_id="other_slot", frame_id=frame.frame_id, candidates=("X1",))
        other.selected = ("X1",)
        other.selector_outcome = "ONE_SELECTED"
        st.decisions[other_key] = other
        st.constraints.append(ConstraintEdge(key, other_key, frozenset({("V1", "X1")})))
        t4(st, SCHEMA)
        self.assertEqual(dec.outcome, "UNRESOLVED")  # the pair is forbidden by the declared edge
        self.assertTrue(st.has_diag("CLUSTER_CONFLICT"))


if __name__ == "__main__":
    unittest.main()
