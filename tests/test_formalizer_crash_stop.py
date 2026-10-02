# -*- coding: utf-8 -*-
"""WP2.9 — crash-stop run on real files (V7 §6.4/§8.3, G4): restart-from-disk goal recovery R0/R1/R2.

The executable proxy for the crash-stop run: state is written to a REAL file with fsync; a "crash" is modeled by not writing
the terminal append; on restart the store is reloaded from disk and GoalRecovery drains the PENDING record decision-first.
Proves R0 (a fixed decision is honored, no duplicate path), R2-apply (live+licensed -> applied now), and R2-abort (a dead
premise -> ABORTED{GOAL_PREMISES_STALE}).
"""

import json
import os
import tempfile
import unittest

from ah.formalizer.goal_executor import GoalExecutor, GoalRequest, GoalStore, PathRecord
from ah.formalizer.recovery import GoalJournalRecord, GoalRecovery
from ah.formalizer.temporal_license import point, cont


def _save(store: GoalStore, path: str) -> None:
    data = {
        "nodes": store.nodes,
        "live_premises": sorted(store.live_premises),
        "decisions": store.decisions,
        "paths": [
            {"key": [k[0], list(k[1]), k[2]], "record_id": v.record_id, "node_id": v.node_id}
            for k, v in store.paths.items()
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
        fh.flush()
        os.fsync(fh.fileno())


def _load(path: str) -> GoalStore:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    store = GoalStore()
    store.nodes = data["nodes"]
    store.live_premises = set(data["live_premises"])
    store.decisions = data["decisions"]
    for entry in data["paths"]:
        k = entry["key"]
        key = (k[0], tuple(k[1]), k[2])
        store.paths[key] = PathRecord(record_id=entry["record_id"], rule_id=k[0],
                                      premise_support_ids=tuple(k[1]), node_id=entry["node_id"])
    return store


def _pending():
    return GoalJournalRecord("run1", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7)))


class TestCrashStopRecovery(unittest.TestCase):
    def test_r0_fixed_decision_honored_no_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "store.json")
            store = GoalStore()
            store.live_premises.update({"s_or", "s_not"})
            res = GoalExecutor(store).execute(GoalRequest("run1", "OR_ELIMINATION", ("s_or", "s_not"), "P1", (point(5), cont(3, 7))))
            self.assertEqual(res["outcome"], "APPLIED")
            _save(store, path)                       # crash: state+decision persisted, terminal append never written

            store2 = _load(path)                    # restart from disk
            out = GoalRecovery(store2, GoalExecutor(store2)).recover(_pending())
            self.assertEqual(out["outcome"], "APPLIED")   # R0: decision found on disk
            self.assertEqual(len(store2.paths), 1)        # no duplicate path

    def test_r2_applies_now_when_live_and_licensed(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "store.json")
            store = GoalStore()                     # crash before any decision/apply
            store.live_premises.update({"s_or", "s_not"})
            _save(store, path)

            store2 = _load(path)
            out = GoalRecovery(store2, GoalExecutor(store2)).recover(_pending())
            self.assertEqual(out["outcome"], "APPLIED")   # R2: live+licensed -> applied now on recovery
            self.assertIn("P1", store2.nodes)             # node created during recovery

    def test_r2_aborts_when_premise_died(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "store.json")
            store = GoalStore()                     # s_not died before the crash (not in live set)
            store.live_premises.update({"s_or"})
            _save(store, path)

            store2 = _load(path)
            out = GoalRecovery(store2, GoalExecutor(store2)).recover(_pending())
            self.assertEqual(out["outcome"], "ABORTED")
            self.assertEqual(out.get("reason"), "GOAL_PREMISES_STALE")


if __name__ == "__main__":
    unittest.main()
