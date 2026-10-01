# -*- coding: utf-8 -*-
"""Reader-contract tests (V7 §7.4) — non-facts never satisfy a fact goal without explicit allowance."""

import unittest

from ah.formalizer.reader_contract import ItemStatus, MemoryItem, admit_for_fact_goal


def _mixed():
    return [
        MemoryItem("f1", ItemStatus.FACT),
        MemoryItem("h1", ItemStatus.HYPOTHETICAL),
        MemoryItem("e1", ItemStatus.EMBEDDED),
        MemoryItem("o1", ItemStatus.OBSERVATION_RECORD),
    ]


def _uids(items):
    return {it.uid for it in items}


class TestDefaultAdmission(unittest.TestCase):
    def test_only_facts_pass_by_default(self):
        self.assertEqual(_uids(admit_for_fact_goal(_mixed())), {"f1"})

    def test_each_nonfact_excluded_individually(self):
        for status, uid in ((ItemStatus.HYPOTHETICAL, "h"), (ItemStatus.EMBEDDED, "e"),
                            (ItemStatus.OBSERVATION_RECORD, "o")):
            self.assertEqual(admit_for_fact_goal([MemoryItem(uid, status)]), [])


class TestFlagIsolation(unittest.TestCase):
    def test_hypothetical_flag_admits_only_hypothetical(self):
        got = _uids(admit_for_fact_goal(_mixed(), allow_hypothetical=True))
        self.assertEqual(got, {"f1", "h1"})  # embedded + observation still excluded

    def test_embedded_flag_admits_only_embedded(self):
        got = _uids(admit_for_fact_goal(_mixed(), allow_embedded=True))
        self.assertEqual(got, {"f1", "e1"})

    def test_observation_flag_admits_only_observation(self):
        got = _uids(admit_for_fact_goal(_mixed(), allow_observation_record=True))
        self.assertEqual(got, {"f1", "o1"})

    def test_all_flags_admit_all(self):
        got = _uids(admit_for_fact_goal(_mixed(), allow_hypothetical=True, allow_embedded=True,
                                        allow_observation_record=True))
        self.assertEqual(got, {"f1", "h1", "e1", "o1"})


if __name__ == "__main__":
    unittest.main()
