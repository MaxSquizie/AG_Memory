# -*- coding: utf-8 -*-
"""E — Reader contract (V7 §7.4/§17): a fact-requiring goal is satisfied ONLY by an admissible, live record.

Proves the invariant that HYPOTHETICAL / EMBEDDED / OBSERVATION_RECORD evidence does NOT satisfy a fact-requiring goal
by default; only an asserted committed fact (ASSERTED) does — and non-admissible evidence can be used only via explicit
allowance. No admissible live record -> UNKNOWN (open world, no silent NO).
"""

import unittest


def _rec(rid, prop, kind, status="LIVE"):
    from ah.formalizer.fact_query import FactRecord
    return FactRecord(record_id=rid, proposition=prop, kind=kind, status=status)


class TestReaderContract(unittest.TestCase):
    def test_asserted_fact_satisfies(self):
        from ah.formalizer.fact_query import answer_fact_goal

        res = answer_fact_goal([_rec("r1", "P", "ASSERTED")], "P")
        self.assertEqual(res["answer"], "YES")
        self.assertEqual(res["satisfied_by"], "r1")

    def test_hypothetical_alone_does_not_satisfy(self):
        from ah.formalizer.fact_query import answer_fact_goal

        res = answer_fact_goal([_rec("h1", "P", "HYPOTHETICAL")], "P")
        self.assertEqual(res["answer"], "UNKNOWN")
        self.assertEqual(res["reason"], "NON_ADMISSIBLE_EVIDENCE_ONLY")
        self.assertIn("HYPOTHETICAL", res["kinds_present"])

    def test_embedded_alone_does_not_satisfy(self):
        from ah.formalizer.fact_query import answer_fact_goal

        res = answer_fact_goal([_rec("e1", "P", "EMBEDDED")], "P")
        self.assertEqual(res["answer"], "UNKNOWN")
        self.assertIn("EMBEDDED", res["kinds_present"])

    def test_observation_record_alone_does_not_satisfy(self):
        from ah.formalizer.fact_query import answer_fact_goal

        res = answer_fact_goal([_rec("o1", "P", "OBSERVATION_RECORD")], "P")
        self.assertEqual(res["answer"], "UNKNOWN")
        self.assertIn("OBSERVATION_RECORD", res["kinds_present"])

    def test_retracted_asserted_is_not_live(self):
        from ah.formalizer.fact_query import answer_fact_goal

        res = answer_fact_goal([_rec("r1", "P", "ASSERTED", status="RETRACTED")], "P")
        self.assertEqual(res["answer"], "UNKNOWN")
        self.assertEqual(res["reason"], "NO_LIVE_RECORD")  # retracted -> not a live record at all

    def test_no_records_at_all(self):
        from ah.formalizer.fact_query import answer_fact_goal

        res = answer_fact_goal([], "P")
        self.assertEqual(res["answer"], "UNKNOWN")
        self.assertEqual(res["reason"], "NO_LIVE_RECORD")

    def test_admissible_wins_over_nonadmissible(self):
        from ah.formalizer.fact_query import answer_fact_goal

        records = [_rec("h1", "P", "HYPOTHETICAL"), _rec("r1", "P", "ASSERTED")]
        res = answer_fact_goal(records, "P")
        self.assertEqual(res["answer"], "YES")
        self.assertEqual(res["satisfied_by"], "r1")

    def test_explicit_allowance_permits_embedded(self):
        from ah.formalizer.fact_query import answer_fact_goal

        records = [_rec("e1", "P", "EMBEDDED")]
        # default: not admissible
        self.assertEqual(answer_fact_goal(records, "P")["answer"], "UNKNOWN")
        # explicit allowance: now it may satisfy
        res = answer_fact_goal(records, "P", allow_kinds=frozenset({"ASSERTED", "EMBEDDED"}))
        self.assertEqual(res["answer"], "YES")
        self.assertEqual(res["satisfied_by"], "e1")

    def test_different_proposition_not_matched(self):
        from ah.formalizer.fact_query import answer_fact_goal

        res = answer_fact_goal([_rec("r1", "Q", "ASSERTED")], "P")
        self.assertEqual(res["answer"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
