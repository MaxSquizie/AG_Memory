# -*- coding: utf-8 -*-
"""Real-file durability tests for the append-only journal (V7 §7.2).

Unlike the in-memory double, these run against an actual log file and prove the two
properties a memory store cannot: records survive a reopen (durable), and a torn last
write is dropped on recovery while the valid prefix is preserved.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel


class TestJournalDurability(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log_path = Path(self._tmp.name) / "journal.log"

    def test_append_is_durable_across_reopen(self):
        j = JournalChannel(self.log_path)
        s1 = j.append("observation", {"k": 1}, run_id="r1")
        s2 = j.append("resolution_log", {"k": 2}, run_id="r1")
        self.assertEqual((s1, s2), (1, 2))

        # Reopen from disk: head and records must survive.
        j2 = JournalChannel(self.log_path)
        self.assertEqual(j2.read_global_head(), 2)
        recs = j2.scan_unprocessed(0)
        self.assertEqual([r["payload"]["k"] for r in recs], [1, 2])

    def test_seq_continues_after_reopen(self):
        JournalChannel(self.log_path).append("observation", {"i": 0})
        j = JournalChannel(self.log_path)
        nxt = j.append("observation", {"i": 1})
        self.assertEqual(nxt, 2)

    def test_torn_last_write_is_dropped_on_recovery(self):
        j = JournalChannel(self.log_path)
        for i in range(3):
            j.append("resolution_log", {"i": i})
        # Simulate a crash mid-write: append a partial (unparseable) line.
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write('{"seq": 4, "channel": "resol')  # torn — no closing brace

        j2 = JournalChannel(self.log_path)  # recover on open
        self.assertEqual(j2.read_global_head(), 3)  # torn seq 4 dropped
        recs = j2.scan_unprocessed(0)
        self.assertEqual([r["payload"]["i"] for r in recs], [0, 1, 2])

        # File on disk now holds only the valid prefix.
        lines = [ln for ln in self.log_path.read_text(encoding="utf-8").split("\n") if ln.strip()]
        self.assertEqual(len(lines), 3)
        json.loads(lines[-1])  # last surviving line is well-formed

    def test_channels_are_logical_partitions_of_one_log(self):
        j = JournalChannel(self.log_path)
        j.append("observation", {"t": "obs"})
        j.append("resolution_log", {"t": "res"})
        j.append("observation", {"t": "obs2"})

        obs = [r["payload"]["t"] for r in j.scan_unprocessed(0, channel="observation")]
        res = [r["payload"]["t"] for r in j.scan_unprocessed(0, channel="resolution_log")]
        self.assertEqual(obs, ["obs", "obs2"])
        self.assertEqual(res, ["res"])

    def test_scan_unprocessed_respects_after_seq(self):
        j = JournalChannel(self.log_path)
        for i in range(5):
            j.append("observation", {"i": i})
        after = [r["payload"]["i"] for r in j.scan_unprocessed(2)]  # seq>2 -> i in {2,3,4}
        self.assertEqual(after, [2, 3, 4])


if __name__ == "__main__":
    unittest.main()
