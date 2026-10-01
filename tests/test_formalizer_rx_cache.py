# -*- coding: utf-8 -*-
"""FormalizationCache (R-X) tests — the hard contracts of V7 §5.10."""

import unittest

from ah.formalizer.rx_cache import FormalizationCache, RxRecord


def _cache():
    return FormalizationCache({"formalizer_schema_version": "v1", "framegen_version": "f1"})


class TestStageIsolation(unittest.TestCase):
    def test_t1_read_never_sees_semantic_fields(self):
        c = _cache()
        rec = RxRecord(
            record_id="r1", key={"lemma": "книга"},
            stages={"R-X1": {"pos": "NOUN"}, "R-X3": {"role": "AGENT"}},
            versions={"formalizer_schema_version": "v1", "framegen_version": "f1"},
        )
        c.record(rec)

        morph = dict(c.read_for_stage("R-X1", {"lemma": "книга"})[0][1])
        self.assertEqual(morph, {"pos": "NOUN"})          # no 'role' leaks into R-X1
        self.assertNotIn("role", morph)

        sem = dict(c.read_for_stage("R-X3", {"lemma": "книга"})[0][1])
        self.assertEqual(sem, {"role": "AGENT"})


class TestRankingNotExclusion(unittest.TestCase):
    def test_rank_reorders_but_never_drops(self):
        c = _cache()
        rec = RxRecord(
            record_id="r", key={"p": 1}, stages={"R-X3": {"priorities": {"b": 5.0}}},
            versions={"formalizer_schema_version": "v1", "framegen_version": "f1"},
        )
        c.record(rec)
        ranked = c.rank("R-X3", ["a", "b"], {"p": 1})
        self.assertEqual(ranked, ["b", "a"])              # reordered by hint...
        self.assertEqual(set(ranked), {"a", "b"})         # ...but nothing excluded

    def test_rank_without_cache_keeps_all(self):
        c = _cache()
        self.assertEqual(c.rank("R-X3", ["x", "y"], {"p": 9}), ["x", "y"])


class TestNegativeExperience(unittest.TestCase):
    def test_only_d_c_r_create_negative_experience(self):
        c = _cache()
        for gt in ("D", "C", "R"):
            self.assertTrue(c.note_rejection({"k": 1}, "R-X3", gt))
        before = len(c.all_records())
        for diag in ("PROVIDER_UNAVAILABLE", "SEARCH_INCOMPLETE", "BUDGET_EXHAUSTED"):
            self.assertFalse(c.note_rejection({"k": 2}, "R-X3", diag))
        self.assertEqual(len(c.all_records()), before)    # diagnostics add nothing


class TestVersioning(unittest.TestCase):
    def test_version_mismatch_excluded_until_migrated(self):
        c = _cache()
        rec = RxRecord(
            record_id="old", key={"k": 1}, stages={"R-X1": {"pos": "NOUN"}},
            versions={"formalizer_schema_version": "v0", "framegen_version": "f1"},   # stale formalizer
        )
        c.record(rec)
        self.assertEqual(c.read_for_stage("R-X1", {"k": 1}), [])  # excluded, never auto-applied

        self.assertTrue(c.migrate("old", {"formalizer_schema_version": "v1"}))
        self.assertEqual(len(c.read_for_stage("R-X1", {"k": 1})), 1)


class TestSupersession(unittest.TestCase):
    def test_supersede_without_deletion(self):
        c = _cache()
        v2 = RxRecord(
            record_id="a", key={"k": 1}, stages={"R-X3": {"priorities": {}}},
            versions={"formalizer_schema_version": "v1"}, provenance={"interpretation_version": "V2"},
        )
        other = RxRecord(
            record_id="b", key={"k": 2}, stages={"R-X3": {}},
            versions={"formalizer_schema_version": "v1", "framegen_version": "f1"},
            provenance={"interpretation_version": "V1"},
        )
        c.record(v2)
        c.record(other)

        changed = c.supersede("V2")
        self.assertEqual(changed, 1)                       # only the V2 record flips
        by_id = {r.record_id: r for r in c.all_records()}
        self.assertEqual(by_id["a"].status, "SUPERSEDED")  # audit preserved (not deleted)
        self.assertEqual(by_id["b"].status, "LIVE")

        # superseded record no longer readable; the other still is
        self.assertEqual(c.read_for_stage("R-X3", {"k": 1}), [])
        self.assertEqual(len(c.read_for_stage("R-X3", {"k": 2})), 1)


if __name__ == "__main__":
    unittest.main()
