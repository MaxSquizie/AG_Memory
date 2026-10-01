# -*- coding: utf-8 -*-
"""WP1.4 — T4 consumes the 5-source traces end-to-end (V7 §5.1).

A BLOCKED applicable source makes the search incomplete, which forbids BOTH NO_CANDIDATE and RESOLVED.
Phase 1 never blocks a source, so existing demo outcomes are unchanged; these tests prove the gate at
the T4 level by injecting a blocked trace set directly.
"""

import unittest

from ah.formalizer.pipeline import t4
from ah.formalizer.selection_protocol import load_decision_schema
from ah.formalizer.state import Decision, FormalizationState, Ground
from ah.formalizer.t3_sources import build_source_traces

SCHEMA = load_decision_schema()


def _state(selected=(), outcome=None, blocked=False):
    st = FormalizationState.new("x")
    dec = Decision(slot_id="predicate_value", frame_id="F1", candidates=("V1", "V2"))  # V1=HAVE
    dec.selected = tuple(selected)
    dec.selector_outcome = outcome
    if selected:
        dec.grounds.append(Ground("M", f"selector chose {list(selected)}", value=selected[0]))
    dec.source_traces = build_source_traces(
        "F1", "predicate_value", schema_candidates=("V1", "V2"),
        blocked=frozenset({3}) if blocked else frozenset(),
        blocked_reasons={3: "R-X3 provider down"} if blocked else {},
    )
    st.decisions["F1|predicate_value"] = dec
    return st


class TestT4SourceTraceGate(unittest.TestCase):
    def test_blocked_search_suppresses_no_candidate(self):
        st = _state(selected=(), outcome="NONE_FIT", blocked=True)
        t4(st, SCHEMA)
        dec = st.decisions["F1|predicate_value"]
        self.assertEqual(dec.outcome, "UNRESOLVED")          # not NO_CANDIDATE
        self.assertTrue(st.has_diag("COMPUTATION_LIMIT"))

    def test_blocked_search_suppresses_resolved(self):
        st = _state(selected=("V1",), outcome="ONE_SELECTED", blocked=True)
        t4(st, SCHEMA)
        dec = st.decisions["F1|predicate_value"]
        self.assertEqual(dec.outcome, "UNRESOLVED")          # not RESOLVED
        self.assertTrue(st.has_diag("COMPUTATION_LIMIT"))

    def test_unblocked_none_fit_is_no_candidate(self):
        st = _state(selected=(), outcome="NONE_FIT", blocked=False)
        t4(st, SCHEMA)
        dec = st.decisions["F1|predicate_value"]
        self.assertEqual(dec.outcome, "NO_CANDIDATE")

    def test_unblocked_grounded_selection_is_resolved(self):
        st = _state(selected=("V1",), outcome="ONE_SELECTED", blocked=False)
        t4(st, SCHEMA)
        dec = st.decisions["F1|predicate_value"]
        self.assertEqual(dec.outcome, "RESOLVED")


if __name__ == "__main__":
    unittest.main()
