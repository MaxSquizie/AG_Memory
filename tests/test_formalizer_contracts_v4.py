"""Executable checks for four V4 architecture contracts (revisions 2-7b).

C1 — bounded tuple search after propagation, RESUMABLE: the traversal position is
     saved between calls; a continuation with a larger budget does NOT re-pay steps
     already executed (checked via accumulated step accounting); non-empty sets do
     not prove a common solution exists; only a completed zero-tuple search proves
     absence.
C2 — two independent DURABLE persistence channels over REAL FILES (write-through +
     fsync per record; restart = reopen from disk): an unresolved observation survives
     without any canonical commit; a materialization marker whose journal record is
     missing yields LOST (never a reconstructed RESOLVED); reconciliation checks the
     EXACT (observation_id, interpretation_version) pair — a surviving v1 must not hide
     a lost v2; a duplicate commit of the same (observation, version) is actually rejected.
C3 — canonical distinction of same-schema templates on the real AHCore; an unbound
     value is NEVER auto-bound to an existing template (not even when it is the only
     structural candidate); restart recovery flags conflicting bindings instead of
     silently taking the first template; paraphrase dedup as the compatibility direction.
C4 — revision retracts support by EXACT observation+version identity (v1 != v10) on
     the real SupportLedger, and a derived proof transitions LIVE -> STALE through a
     shared status tracker when its only premise is fully superseded. The tracker is
     CYCLE-SAFE: mutual references without external base support sustain nothing.

These verify architectural decisions only; they do not extend the language parser.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from ah.core import AHCore, SequentialUidGenerator
from ah.core.supports import SupportLedger, SupportRecord
from ah.model import ActantRole, Domain, Property, RefKind


# --------------------------------------------------------------------------- C1

class BoundedSearch:
    """Resumable deterministic enumeration of full assignments with a step budget.

    The traversal position (frame stack + current assignment) is SAVED between calls;
    ``run(budget)`` continues the SAME search and charges only steps taken in this
    call. ``steps_total`` accumulates charged steps across all runs, so a
    continuation that re-paid finished work would show up as an inflated total.

    Statuses: 'COMPLETE' (enumeration finished), 'PROVISIONAL' (tuples found but the
    search is cut off — absence NOT proven), 'INCOMPLETE_NO_TUPLES' (cut off, nothing
    found yet). Continuing with a larger budget takes no new semantic grounds.
    """

    def __init__(self, slots: dict[str, tuple], constraints: list[tuple[tuple[str, ...], frozenset]]) -> None:
        self.slots = {k: tuple(v) for k, v in sorted(slots.items())}
        self.order = list(self.slots)
        self.constraints = constraints
        self.found: list[dict] = []
        self.completed = False
        self.steps_total = 0
        # Saved traversal position: one frame per open depth (slot_pos, next_value_idx).
        self._stack: list[tuple[int, int]] = [(0, 0)] if self.order else []
        self._assign: dict[str, object] = {}

    def _satisfies(self, assign: dict[str, object]) -> bool:
        for slot_ids, forbidden in self.constraints:
            if all(s in assign for s in slot_ids):
                if tuple(assign[s] for s in slot_ids) in forbidden:
                    return False
        return True

    def run(self, budget: int) -> str:
        if self.completed:
            return "COMPLETE"
        steps = 0
        while self._stack and not self.completed:
            slot_pos, value_idx = self._stack[-1]
            values = self.slots[self.order[slot_pos]]
            if value_idx >= len(values):
                # All values at this depth exhausted: backtrack (no step charged).
                self._assign.pop(self.order[slot_pos], None)
                self._stack.pop()
                continue
            if steps >= budget:
                break  # stop BEFORE charging an unproductive step; position is saved
            steps += 1
            self.steps_total += 1
            slot = self.order[slot_pos]
            value = values[value_idx]
            self._assign[slot] = value
            self._stack[-1] = (slot_pos, value_idx + 1)
            if slot_pos == len(self.order) - 1:
                # Leaf: a full assignment. The frame STAYS on the stack so its
                # remaining values are tried before backtracking to the parent.
                if self._satisfies(self._assign):
                    self.found.append(dict(self._assign))
                del self._assign[slot]
            else:
                self._stack.append((slot_pos + 1, 0))
        if not self._stack:
            self.completed = True
            return "COMPLETE"
        return "PROVISIONAL" if self.found else "INCOMPLETE_NO_TUPLES"


class ContractC1BoundedSearchTests(unittest.TestCase):
    def test_gac_passes_but_no_global_solution(self) -> None:
        # Three binary variables, pairwise "not equal": every value is locally
        # supported (non-empty sets after propagation), yet no global solution.
        slots = {"a": (0, 1), "b": (0, 1), "c": (0, 1)}
        neq = frozenset({(0, 0), (1, 1)})
        constraints = [(("a", "b"), neq), (("b", "c"), neq), (("a", "c"), neq)]
        for slot_id in slots:
            self.assertTrue(slots[slot_id], "propagation must not empty these sets")
        search = BoundedSearch(slots, constraints)
        self.assertEqual(search.run(budget=10_000), "COMPLETE")
        self.assertEqual(search.found, [], "pigeonhole: no compatible tuple exists")
        # Contract: completion with zero tuples is the ONLY absence proof.

    def test_incomplete_search_keeps_selection_provisional(self) -> None:
        search = BoundedSearch({"a": (0, 1), "b": (0, 1), "c": (0, 1), "d": (0, 1)}, [])
        self.assertEqual(search.run(budget=5), "PROVISIONAL")
        self.assertFalse(search.completed)
        self.assertTrue(0 < len(search.found) < 16)
        prefix = list(search.found)

    def test_continuation_does_not_repay_finished_steps(self) -> None:
        # The required property: the SAME search resumes from its saved position and
        # does not re-execute (re-pay) steps already done in an earlier run.
        search = BoundedSearch({"a": (0, 1), "b": (0, 1), "c": (0, 1), "d": (0, 1)}, [])
        self.assertEqual(search.run(budget=5), "PROVISIONAL")
        prefix = list(search.found)
        self.assertEqual(search.run(budget=10_000), "COMPLETE")
        self.assertTrue(search.completed)
        # Deterministic order: the provisional results are a prefix of the full set.
        self.assertEqual(len(search.found), 16)
        self.assertEqual(search.found[: len(prefix)], prefix)
        # Full enumeration cost for four binary slots is 2+4+8+16 = 30 charged steps.
        # A restart-from-scratch implementation would pay 5 + 30 = 35 here.
        self.assertEqual(search.steps_total, 30)

    def test_completed_zero_tuple_search_is_the_only_absence_proof(self) -> None:
        search = BoundedSearch(
            {"a": (0, 1), "b": (0, 1), "c": (0, 1)},
            [(ids, frozenset({(0, 0), (1, 1)})) for ids in (("a", "b"), ("b", "c"), ("a", "c"))],
        )
        self.assertEqual(search.run(budget=200), "COMPLETE")
        self.assertEqual(search.found, [])  # absence proven only because search_complete

    def test_found_tuples_are_the_only_selector_input(self) -> None:
        neq = frozenset({(0, 0), (1, 1)})
        search = BoundedSearch({"a": (0, 1), "b": (0, 1)}, [(("a", "b"), neq)])
        self.assertEqual(search.run(budget=200), "COMPLETE")
        # Exactly the compatible tuples — and only them — reach the selector.
        self.assertEqual(len(search.found), 2)
        for t in search.found:
            self.assertNotIn((t["a"], t["b"]), neq)


# --------------------------------------------------------------------------- C2

class _DurableLog:
    """REAL durable storage: an append-only file with write-through + fsync per record.

    Durability is not simulated in memory: every ``append`` lands on disk (flush +
    os.fsync) before returning, so a 'crash' means simply dropping the in-memory
    objects and reopening the file — the records must be there."""

    def __init__(self, path: str | None = None, lines: list[str] | None = None) -> None:
        if path is None:
            fd, path = tempfile.mkstemp(prefix="durable-")
            os.close(fd)
        self.path = path
        if lines is not None:
            with open(self.path, "w", encoding="utf-8") as fh:
                for line in lines:
                    fh.write(line + "\n")
            os.fsync(os.open(self.path, os.O_RDONLY))
        self.lines: list[str] = []  # in-memory mirror only; disk is the authority

    def append(self, line: str) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())  # durable BEFORE the in-memory view updates
        self.lines.append(line)

    @classmethod
    def from_disk(cls, path: str) -> "_DurableLog":
        log = cls(path=path)
        with open(path, encoding="utf-8") as fh:
            log.lines = [ln for ln in fh.read().splitlines() if ln]
        return log


class DuplicateCommitError(Exception):
    pass


class _FactStore:
    """Canonical channel: elements and the idempotency marker commit atomically to a
    durable log; restart replays committed batches in order."""

    def __init__(self, log: _DurableLog | None = None) -> None:
        self.log = log or _DurableLog()
        self.facts: dict[str, dict] = {}
        self.markers: set[tuple[str, int]] = set()
        for line in self.log.lines:  # replay
            batch = json.loads(line)
            for uid, element in batch["elements"]:
                self.facts[uid] = element
            self.markers.add((batch["marker"][0], batch["marker"][1]))

    @classmethod
    def from_disk(cls, path: str) -> "_FactStore":
        return cls(_DurableLog.from_disk(path))

    def atomic_commit(self, elements: list[dict], marker: tuple[str, int]) -> None:
        if marker in self.markers:
            raise DuplicateCommitError(f"marker {marker} already committed")
        staged = dict(self.facts)
        for element in elements:  # validate everything before anything lands
            if "uid" not in element:
                raise ValueError("malformed element")
            staged[element["uid"]] = element
        batch = json.dumps(
            {"elements": [[e["uid"], e] for e in elements], "marker": list(marker)}, sort_keys=True
        )
        self.log.append(batch)  # durable first, then the in-memory view
        self.facts = staged
        self.markers.add(marker)


class _ObservationJournal:
    """Independent append-only channel over its own durable log; records are never
    overwritten. Written on create/update regardless of any canonical commit.

    rev8 (D7): records are keyed by the EXACT (observation_id, interpretation_version)
    pair — every version is stored separately, so a surviving v1 record can neither hide
    nor satisfy a lost v2 marker."""

    def __init__(self, log: _DurableLog | None = None) -> None:
        self.log = log or _DurableLog()
        self.records: dict[tuple[str, int], dict] = {}
        for line in self.log.lines:  # replay
            entry = json.loads(line)
            key = (entry["id"], entry["version"])
            if key not in self.records:
                self.records[key] = entry["record"]

    @classmethod
    def from_disk(cls, path: str) -> "_ObservationJournal":
        return cls(_DurableLog.from_disk(path))

    def write(self, observation_id: str, record: dict) -> None:
        version = int(record["interpretation_version"])
        self.log.append(json.dumps(
            {"id": observation_id, "version": version, "record": record}, sort_keys=True))
        key = (observation_id, version)
        if key not in self.records:  # append-only: first write of a pair wins
            self.records[key] = record


def _restart(fact_path: str, journal_path: str):
    """Restart: replay both channels from DISK; reconcile by EXACT identity.

    A materialization marker (observation_id, version) is reconciled against a journal
    record carrying the SAME observation_id AND the SAME interpretation_version. A
    surviving v1 record must NOT hide a lost v2 marker: each marker is checked on its
    own exact pair. Missing pairs yield LOST diagnostics — never reconstructed RESOLVED.
    """
    facts = _FactStore.from_disk(fact_path)
    journal = _ObservationJournal.from_disk(journal_path)
    diagnostics: list[dict] = []
    for marker in sorted(facts.markers):
        record = journal.records.get(marker)  # rev8 (D7): exact-pair lookup
        if record is None:
            provenance = next(
                (e["meta"] for e in facts.facts.values() if e["meta"].get("observation_id") == marker[0]), {}
            )
            diagnostics.append({"observation": marker[0], "version": marker[1], "status": "LOST", "provenance": provenance})
    return facts, journal, diagnostics


class ContractC2TwoChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="c2-")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _path(self, name: str) -> str:
        return os.path.join(self._tmp.name, name)

    def test_unresolved_observation_survives_restart_without_any_commit(self) -> None:
        fact_path = self._path("facts.log")
        open(fact_path, "a").close()  # exists but empty: crash before any materialization
        journal_log = _ObservationJournal(_DurableLog(self._path("journal.log")))
        record = {
            "source_id": "U9", "span": [0, 12], "status": "UNRESOLVED",
            "interpretation_version": 1,
            "linked_alternatives": [[{"rel": "HAVE"}, {"rel": "HAS_PART"}]],
            "resolution_log": [],
        }
        journal_log.write("obs-U9-0-12", record)
        # Restart from DISK only (in-memory objects dropped): the observation must survive.
        facts, restored_journal, diagnostics = _restart(fact_path, journal_log.log.path)
        key = ("obs-U9-0-12", 1)  # rev8 (D7): exact-pair key
        self.assertIn(key, restored_journal.records)
        self.assertEqual(restored_journal.records[key]["status"], "UNRESOLVED")
        self.assertEqual(
            restored_journal.records[key]["linked_alternatives"], record["linked_alternatives"]
        )
        self.assertEqual(facts.facts, {})  # nothing was materialized
        self.assertEqual(diagnostics, [])

    def test_durability_is_on_disk_not_in_memory(self) -> None:
        log = _DurableLog(self._path("d.log"))
        log.append(json.dumps({"id": "o1", "version": 1, "record": {"interpretation_version": 1}}))
        # Simulated crash: the in-memory object is dropped; only the file remains.
        del log
        reopened = _DurableLog.from_disk(self._path("d.log"))
        self.assertEqual(len(reopened.lines), 1)
        with open(self._path("d.log"), "rb") as fh:
            self.assertIn(b'"interpretation_version": 1', fh.read())

    def test_marker_without_journal_record_is_lost_not_reconstructed(self) -> None:
        fact_log = _FactStore(_DurableLog(self._path("facts.log")))
        journal_path = self._path("journal.log")
        open(journal_path, "a").close()  # exists but empty: crash before the journal write
        element = {"uid": "n1", "meta": {"observation_id": "obs-U1-0-7", "interpretation_version": 1}}
        fact_log.atomic_commit([element], ("obs-U1-0-7", 1))
        _, restored_journal, diagnostics = _restart(fact_log.log.path, journal_path)
        # The lost record is flagged LOST with its provenance — never resurrected as RESOLVED.
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["status"], "LOST")
        self.assertEqual(diagnostics[0]["provenance"]["interpretation_version"], 1)
        self.assertNotIn(("obs-U1-0-7", 1), restored_journal.records)

    def test_surviving_v1_does_not_hide_lost_v2(self) -> None:
        # rev7b: reconciliation is on the EXACT (observation_id, interpretation_version)
        # pair. A journal record for v1 must not satisfy a materialization marker of v2.
        fact_log = _FactStore(_DurableLog(self._path("facts.log")))
        journal = _ObservationJournal(_DurableLog(self._path("journal.log")))
        journal.write(
            "obs-U3-0-5",
            {"source_id": "U3", "status": "RESOLVED", "interpretation_version": 1},
        )
        fact_log.atomic_commit(
            [{"uid": "nA", "meta": {"observation_id": "obs-U3-0-5", "interpretation_version": 1}}],
            ("obs-U3-0-5", 1),
        )
        fact_log.atomic_commit(
            [{"uid": "nB", "meta": {"observation_id": "obs-U3-0-5", "interpretation_version": 2}}],
            ("obs-U3-0-5", 2),  # v2 materialized, but its journal record was lost
        )
        facts, restored_journal, diagnostics = _restart(fact_log.log.path, journal.log.path)
        self.assertEqual(len(diagnostics), 1)  # exactly the lost pair is flagged...
        self.assertEqual((diagnostics[0]["observation"], diagnostics[0]["version"]), ("obs-U3-0-5", 2))
        self.assertEqual(restored_journal.records[("obs-U3-0-5", 1)]["interpretation_version"], 1)

    def test_journal_keeps_every_version_under_its_exact_pair(self) -> None:
        # rev8 (D7): the journal stores ALL versions separately under their exact pairs —
        # v1 and v2 coexist; nothing is overwritten, so a later v3 loss stays visible too.
        journal = _ObservationJournal(_DurableLog(self._path("journal.log")))
        journal.write("obs-U4-0-9", {"source_id": "U4", "status": "UNRESOLVED", "interpretation_version": 1})
        journal.write("obs-U4-0-9", {"source_id": "U4", "status": "RESOLVED", "interpretation_version": 2})
        restored = _ObservationJournal.from_disk(journal.log.path)
        self.assertEqual(set(restored.records), {("obs-U4-0-9", 1), ("obs-U4-0-9", 2)})
        self.assertEqual(restored.records[("obs-U4-0-9", 1)]["status"], "UNRESOLVED")
        self.assertEqual(restored.records[("obs-U4-0-9", 2)]["status"], "RESOLVED")

    def test_duplicate_commit_is_rejected(self) -> None:
        facts = _FactStore(_DurableLog(self._path("facts.log")))
        element = {"uid": "n1", "meta": {"observation_id": "obs-U1-0-7"}}
        facts.atomic_commit([element], ("obs-U1-0-7", 1))
        facts_before, markers_before = dict(facts.facts), set(facts.markers)
        with self.assertRaises(DuplicateCommitError):
            facts.atomic_commit([{"uid": "n2"}], ("obs-U1-0-7", 1))  # same observation+version
        self.assertEqual(facts.facts, facts_before)  # store untouched by the rejected commit
        self.assertEqual(facts.markers, markers_before)

    def test_marker_and_elements_are_all_or_nothing(self) -> None:
        log = _DurableLog(self._path("facts.log"))
        facts = _FactStore(log)
        with self.assertRaises(ValueError):
            # One valid element plus one malformed: the whole commit must fail.
            facts.atomic_commit([{"uid": "nX"}, {"broken": True}], ("obs-U2-0-3", 1))
        self.assertEqual(facts.facts, {})
        self.assertEqual(facts.markers, set())
        self.assertEqual(log.lines, [])  # nothing durable was written


# --------------------------------------------------------------------------- C3

def resolve_value(registry: dict[str, str], value: str) -> str | None:
    """Pure lookup of RECORDED bindings. The mechanism has no auto-binding path:
    a value is bound to a template only by an explicit recorded decision."""
    return registry.get(value)


def record_selection(registry: dict[str, str], value: str, t_uid: str) -> None:
    """Explicit bounded decision (template_selection): bind the value to an existing T."""
    registry[value] = t_uid


def create_binding(core: AHCore, s_uid: str, roles: tuple, value: str, registry: dict[str, str]) -> str:
    """Explicit schema extension for a NEW value: dedicated template + recorded binding."""
    if value in registry:
        return registry[value]
    t = core.add_template(Domain.C, core.ref(s_uid), roles)
    registry[value] = t.uid
    return t.uid


def recover_value_map(core: AHCore, s_uid: str) -> tuple[dict[str, str], list[str]]:
    """Restart fallback: scan N under candidate templates and read properties.

    A value bound to several distinct templates in the scan is NOT silently assigned
    to the first one; it is reported as a conflict instead."""
    seen: dict[str, set[str]] = {}
    for t in core.store.find_templates_by_predicate(s_uid):
        for node in core.store.find_hypernodes_by_template(t.uid):
            relation = node.properties.get("relation")
            if relation is not None:
                seen.setdefault(relation.value, set()).add(t.uid)
    recovered: dict[str, str] = {}
    conflicts: list[str] = []
    for value in sorted(seen):
        uids = seen[value]
        if len(uids) == 1:
            recovered[value] = next(iter(uids))
        else:
            conflicts.append(f"value {value!r} bound to multiple templates: {sorted(uids)}")
    return recovered, conflicts


def reconcile_value_map(
    core: AHCore, s_uid: str, persisted: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Persisted registry vs scan; disagreement is a diagnostic, not re-binding."""
    scanned, scan_conflicts = recover_value_map(core, s_uid)
    trusted: dict[str, str] = {}
    diagnostics: list[str] = list(scan_conflicts)
    for value, uid in persisted.items():
        if value in scanned and scanned[value] != uid:
            diagnostics.append(f"value {value!r}: registry={uid} scan={scanned[value]}")
        else:
            trusted[value] = uid
    return trusted, diagnostics


class ContractC3TemplateDistinctionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        s = self.core.add_abstract_symbol({"есть"})
        self.s_uid = s.uid
        roles = (ActantRole.SUBJECT, ActantRole.OBJECT)
        self.roles = roles
        # Same predicate S and identical role schema — distinct canonical values.
        self.t_have = self.core.add_template(Domain.C, self.core.ref(s.uid), roles)
        self.t_part = self.core.add_template(Domain.C, self.core.ref(s.uid), roles)
        crow = self.core.add_entity(Domain.P, properties={"name": Property("name", "crow", "str")})
        feet = self.core.add_entity(Domain.C, properties={"name": Property("name", "feet", "str")})
        self.actants = {
            ActantRole.SUBJECT: self.core.ref(crow.uid),
            ActantRole.OBJECT: self.core.ref(feet.uid),
        }

    def test_same_schema_templates_stay_distinct(self) -> None:
        n_have, created_a = self.core.add_hypernode(Domain.P, self.core.ref(self.t_have.uid), self.actants, weight=0.5)
        n_part, created_b = self.core.add_hypernode(Domain.P, self.core.ref(self.t_part.uid), self.actants, weight=0.5)
        self.assertTrue(created_a and created_b)
        self.assertNotEqual(n_have.uid, n_part.uid)
        # The resolver must not merge them: signature is keyed by template uid.
        sig = self.core.store.find_hypernode_by_signature(
            Domain.P,
            (self.t_part.uid, ((ActantRole.SUBJECT.value, "REF", RefKind.M.value, self.actants[ActantRole.SUBJECT].uid),
                               (ActantRole.OBJECT.value, "REF", RefKind.M.value, self.actants[ActantRole.OBJECT].uid)),
             None, None, None),
        )
        self.assertIsNotNone(sig)
        self.assertEqual(sig.uid, n_part.uid)

    # --- value -> canonical template mapping (no auto-binding; exact recovery) --

    def _materialize_tagged(self, t_uid: str, relation: str):
        n, created = self.core.add_hypernode(
            Domain.P,
            self.core.ref(t_uid),
            self.actants,
            weight=0.5,
            properties={"relation": Property("relation", relation, "str")},
        )
        self.assertTrue(created)
        return n

    def test_unbound_value_is_never_guessed_even_with_single_candidate(self) -> None:
        # Regression for the reported defect: with exactly ONE structurally matching
        # template under S, an unbound value must NOT be auto-bound to it.
        core = AHCore(uid_generator=SequentialUidGenerator())
        s = core.add_abstract_symbol({"есть"})
        only_t = core.add_template(Domain.C, core.ref(s.uid), self.roles)
        candidates = [t for t in core.store.find_templates_by_predicate(s.uid)
                     if tuple(r.value for r in t.roles) == tuple(r.value for r in self.roles)]
        self.assertEqual(len(candidates), 1)  # the tempting unique structural candidate
        registry: dict[str, str] = {}
        self.assertIsNone(resolve_value(registry, "HAVE"))  # uniqueness does not confirm the value
        record_selection(registry, "HAVE", only_t.uid)  # explicit bounded decision binds it
        self.assertEqual(resolve_value(registry, "HAVE"), only_t.uid)

    def test_bound_values_resolve_without_creating_new_templates(self) -> None:
        registry = {"HAVE": self.t_have.uid, "HAS_PART": self.t_part.uid}
        templates_before = len(self.core.store.find_templates_by_predicate(self.s_uid))
        self.assertEqual(resolve_value(registry, "HAVE"), self.t_have.uid)
        self.assertEqual(resolve_value(registry, "HAS_PART"), self.t_part.uid)
        # A genuinely new value is an explicit schema extension, not a guess.
        uid = create_binding(self.core, self.s_uid, self.roles, "LIKE", registry)
        self.assertNotIn(uid, {registry["HAVE"], registry["HAS_PART"]})
        self.assertEqual(len(self.core.store.find_templates_by_predicate(self.s_uid)), templates_before + 1)

    def test_value_map_recovers_after_restart_and_flags_conflicts(self) -> None:
        self._materialize_tagged(self.t_have.uid, "HAVE")
        self._materialize_tagged(self.t_part.uid, "HAS_PART")
        # Restart: the persisted registry is lost; recover by scanning N properties.
        recovered, conflicts = recover_value_map(self.core, self.s_uid)
        self.assertEqual(recovered["HAVE"], self.t_have.uid)
        self.assertEqual(recovered["HAS_PART"], self.t_part.uid)
        self.assertEqual(conflicts, [])
        # A stale persisted registry disagreeing with the scan -> diagnostic, never
        # silent re-binding.
        check, diagnostics = reconcile_value_map(self.core, self.s_uid, {"HAVE": self.t_part.uid})
        self.assertNotIn("HAVE", check)  # no binding trusted
        self.assertTrue(diagnostics)

    def test_conflicting_scan_never_picks_first_silently(self) -> None:
        # Regression for the reported defect: one value materialized under two
        # distinct templates must NOT resolve to whichever template is scanned first.
        t_extra = self.core.add_template(Domain.C, self.core.ref(self.s_uid), self.roles)
        self._materialize_tagged(self.t_have.uid, "HAVE")
        self._materialize_tagged(t_extra.uid, "HAVE")  # same value, different template
        recovered, conflicts = recover_value_map(self.core, self.s_uid)
        self.assertNotIn("HAVE", recovered)  # no silent first-wins binding
        self.assertTrue(any("HAVE" in c for c in conflicts))

    def test_paraphrase_dedup_is_the_compatibility_direction(self) -> None:
        first, created = self.core.add_hypernode(Domain.P, self.core.ref(self.t_have.uid), self.actants, weight=0.5)
        second, created_again = self.core.add_hypernode(Domain.P, self.core.ref(self.t_have.uid), self.actants, weight=0.9)
        self.assertTrue(created and not created_again)
        self.assertEqual(first.uid, second.uid)
        self.assertEqual(int(second.meta["occurrence_count"]), 2)


# --------------------------------------------------------------------------- C4

def _obs_tag(observation_id: str, version: int) -> str:
    """Exact observation+version identity; 'v1' and 'v10' are distinct strings."""
    return f"OBS|{observation_id}|v{version}"


class _StatusTracker:
    """Contract-level element statuses recomputed from the live ledger.

    LIVE — has at least one support record whose premise elements are all LIVE
    (source-derived mentions count as LIVE); SUPERSEDED — no support records remain;
    STALE — records exist but every proof rests on a non-LIVE element.

    rev7b: the computation is an ITERATIVE monotone fixpoint, not recursion. Cyclic
    proofs cannot crash it, and mutual references without external base support
    sustain NOTHING: A<-B<-A with no source premise stays STALE (a recursive tracker
    either crashes or wrongly lights both up)."""

    def __init__(self, ledger: SupportLedger, source_uids: set[str]) -> None:
        self.ledger = ledger
        self.source = set(source_uids)

    def _live_set(self) -> set[str]:
        live = set(self.source)
        changed = True
        while changed:  # monotone fixpoint: terminates in <= n rounds, cycle-safe
            changed = False
            for uid, _records in self.ledger.items():
                if uid in live:
                    continue
                records = self.ledger.get(uid)
                if any(all(premise.uid in live for premise in record.premise_refs) for record in records):
                    live.add(uid)
                    changed = True
        return live

    def status(self, uid: str) -> str:
        if uid in self.source:
            return "LIVE"
        if not self.ledger.get(uid):
            return "SUPERSEDED"
        return "LIVE" if uid in self._live_set() else "STALE"


class ContractC4SupportRetractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        s = self.core.add_abstract_symbol({"есть"})
        t = self.core.add_template(Domain.C, self.core.ref(s.uid), (ActantRole.SUBJECT, ActantRole.OBJECT))
        crow = self.core.add_entity(Domain.P, properties={"name": Property("name", "crow", "str")})
        feet = self.core.add_entity(Domain.C, properties={"name": Property("name", "feet", "str")})
        # Source-derived mention elements: one per observation (pre-merge provenance).
        self.mention_u1 = self.core.add_entity(Domain.P, properties={"name": Property("name", "crow@U1", "str")})
        self.mention_u2 = self.core.add_entity(Domain.P, properties={"name": Property("name", "crow@U2", "str")})
        actants = {ActantRole.SUBJECT: self.core.ref(crow.uid), ActantRole.OBJECT: self.core.ref(feet.uid)}
        # Both observations dedup into ONE canonical fact (fact identity is shared).
        n1, _ = self.core.add_hypernode(Domain.P, self.core.ref(t.uid), actants, weight=0.5)
        n2, created = self.core.add_hypernode(Domain.P, self.core.ref(t.uid), actants, weight=0.5)
        self.assertFalse(created)
        self.fact = n1
        # A derived conclusion supported by the fact via a declared rule.
        # NOT is a registered deterministic g; the registry rejects unknown ids,
        # which itself enforces the v4 invariant on functional semantics.
        self.conclusion = self.core.add_function(Domain.C, "NOT", (self.core.ref(n1.uid),))
        self.ledger = SupportLedger()
        self.tag_u1_v1 = _obs_tag("U1", 1)
        self.tag_u2_v1 = _obs_tag("U2", 1)
        self.ledger.add(self.fact.uid, SupportRecord((self.core.ref(self.mention_u1.uid),), rule_id=self.tag_u1_v1))
        self.ledger.add(self.fact.uid, SupportRecord((self.core.ref(self.mention_u2.uid),), rule_id=self.tag_u2_v1))
        self.ledger.add(self.conclusion.uid, SupportRecord((self.core.ref(n1.uid),), rule_id="R-I1"))

    def _retract_observation(self, ledger: SupportLedger, observation_id: str, version: int) -> None:
        """Observation-level retraction on existing primitives: clone the view, drop
        records with EXACT (observation_id, version) identity, restore."""
        tag = _obs_tag(observation_id, version)
        rebuilt: dict[str, list[SupportRecord]] = {}
        for uid, records in ledger.items():
            kept = [r for r in records if r.rule_id != tag]  # exact match, never a prefix
            if kept:
                rebuilt[uid] = kept
        ledger.restore(rebuilt)

    def test_retracting_one_observation_keeps_the_shared_fact(self) -> None:
        self._retract_observation(self.ledger, "U1", 1)
        # The fact still has the live U2 support -> it survives; only U1's
        # interpretation is revised, the shared fact is not replaced wholesale.
        remaining = self.ledger.get(self.fact.uid)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].rule_id, self.tag_u2_v1)

    def test_derived_conclusion_survives_single_observation_retraction(self) -> None:
        # The required case: a derived proof whose only premise is the shared N
        # must survive retraction of ONE of the N's observations.
        tracker = _StatusTracker(
            self.ledger, {self.mention_u1.uid, self.mention_u2.uid}
        )
        self.assertEqual(tracker.status(self.fact.uid), "LIVE")
        self.assertEqual(tracker.status(self.conclusion.uid), "LIVE")
        self._retract_observation(self.ledger, "U1", 1)
        remaining = self.ledger.get(self.fact.uid)
        self.assertEqual(len(remaining), 1)  # fact still live via U2
        conclusion_records = self.ledger.get(self.conclusion.uid)
        self.assertEqual(len(conclusion_records), 1)  # downstream proof untouched
        self.assertEqual(conclusion_records[0].premise_refs[0].uid, self.fact.uid)
        self.assertEqual(tracker.status(self.conclusion.uid), "LIVE")

    def test_exact_version_identity_v1_vs_v10(self) -> None:
        # Regression for the reported defect: prefix matching would let a v1 retraction
        # hit v10. Exact identity must not.
        mention_u1_later = self.core.add_entity(Domain.P, properties={"name": Property("name", "crow@U1-later", "str")})
        tag_u1_v10 = _obs_tag("U1", 10)
        # The old prefix filter WAS wrong: a v1 tag is a string prefix of the v10 tag.
        self.assertTrue(tag_u1_v10.startswith(self.tag_u1_v1))
        # Exact identity must not conflate them.
        self.ledger.add(self.fact.uid, SupportRecord((self.core.ref(mention_u1_later.uid),), rule_id=tag_u1_v10))
        self._retract_observation(self.ledger, "U1", 1)  # retracts v1 ONLY
        remaining = {r.rule_id for r in self.ledger.get(self.fact.uid)}
        self.assertEqual(remaining, {self.tag_u2_v1, tag_u1_v10})

    def test_status_transitions_to_stale_after_full_supersession(self) -> None:
        # The required transition check via the shared tracker (not a local function):
        # LIVE -> STALE for the derived proof once its only premise is fully superseded.
        tracker = _StatusTracker(self.ledger, {self.mention_u1.uid, self.mention_u2.uid})
        self.assertEqual(tracker.status(self.fact.uid), "LIVE")
        self.assertEqual(tracker.status(self.conclusion.uid), "LIVE")
        # Retract U1: the fact is still live via U2; the proof stays LIVE.
        self._retract_observation(self.ledger, "U1", 1)
        self.assertEqual(tracker.status(self.fact.uid), "LIVE")
        self.assertEqual(tracker.status(self.conclusion.uid), "LIVE")
        # Retract U2: ALL observation-level supports are gone -> the fact is
        # SUPERSEDED and its only dependent proof transitions to STALE. Records are
        # NOT deleted at this level — deletion belongs to element-level invalidation.
        self._retract_observation(self.ledger, "U2", 1)
        self.assertEqual(tracker.status(self.fact.uid), "SUPERSEDED")
        self.assertEqual(len(self.ledger.get(self.conclusion.uid)), 1)  # record still present...
        self.assertEqual(tracker.status(self.conclusion.uid), "STALE")  # ...but its proof is dead
        # Element-level invalidation now applies: the stale proof is revisited/dropped.
        affected = self.ledger.invalidate_by_premise(self.fact.uid)
        self.assertIn(self.conclusion.uid, affected)
        self.assertEqual(tracker.status(self.conclusion.uid), "SUPERSEDED")

    def test_element_level_invalidation_only_after_full_supersession(self) -> None:
        self._retract_observation(self.ledger, "U1", 1)
        # Anti-pattern guard: element-level invalidation of a still-LIVE shared N
        # would wrongly drop the surviving downstream proof.
        probe = self.ledger.clone()
        affected_by_probe = probe.invalidate_by_premise(self.fact.uid)
        self.assertIn(self.conclusion.uid, affected_by_probe)  # what it WOULD do...
        self.assertEqual(len(self.ledger.get(self.conclusion.uid)), 1)  # ...but is not applied
        # Only after ALL observation-level supports are gone does the element level apply.
        self._retract_observation(self.ledger, "U2", 1)
        self.assertEqual(self.ledger.get(self.fact.uid), ())
        affected = self.ledger.invalidate_by_premise(self.fact.uid)
        self.assertIn(self.conclusion.uid, affected)  # premise superseded -> proof revisited

    def test_fact_identity_differs_from_observation_identity(self) -> None:
        # Two observations share one fact uid but keep distinct provenance records.
        records = self.ledger.get(self.fact.uid)
        self.assertEqual(len(records), 2)  # same bucket, per-observation tags
        self.assertEqual({r.rule_id for r in records}, {self.tag_u1_v1, self.tag_u2_v1})

    def test_cyclic_proof_without_base_support_sustains_nothing(self) -> None:
        # rev7b regression: A<-B<-A with NO external base premise. Mutual reference is
        # not proof: both stay STALE (and the tracker does not crash on the cycle).
        a = self.core.add_entity(Domain.P, properties={"name": Property("name", "a", "str")})
        b = self.core.add_entity(Domain.P, properties={"name": Property("name", "b", "str")})
        ledger = SupportLedger()
        ledger.add(a.uid, SupportRecord((self.core.ref(b.uid),), rule_id="R-CYC"))
        ledger.add(b.uid, SupportRecord((self.core.ref(a.uid),), rule_id="R-CYC"))
        tracker = _StatusTracker(ledger, set())  # no source-derived base premises
        self.assertEqual(tracker.status(a.uid), "STALE")
        self.assertEqual(tracker.status(b.uid), "STALE")

    def test_cyclic_proof_with_external_support_lights_up(self) -> None:
        # The same cycle gains ONE external base premise: the fixpoint must light both.
        a = self.core.add_entity(Domain.P, properties={"name": Property("name", "a2", "str")})
        b = self.core.add_entity(Domain.P, properties={"name": Property("name", "b2", "str")})
        base = self.core.add_entity(Domain.P, properties={"name": Property("name", "base", "str")})
        ledger = SupportLedger()
        ledger.add(a.uid, SupportRecord((self.core.ref(b.uid),), rule_id="R-CYC"))
        # b has TWO proofs: the cyclic one (needs a) and an independent base proof.
        ledger.add(b.uid, SupportRecord((self.core.ref(a.uid),), rule_id="R-CYC"))
        ledger.add(b.uid, SupportRecord((self.core.ref(base.uid),), rule_id="R-BASE"))
        tracker = _StatusTracker(ledger, {base.uid})
        self.assertEqual(tracker.status(b.uid), "LIVE")  # via the base premise
        self.assertEqual(tracker.status(a.uid), "LIVE")  # then through the cycle


if __name__ == "__main__":
    unittest.main()
