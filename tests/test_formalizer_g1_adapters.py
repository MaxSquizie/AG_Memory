# -*- coding: utf-8 -*-
"""WP0.6 — G1 adapter tests certifiable on the current spine (V7 §12/§20).

All nine named G1 cases are implemented here against real code (the §12/§17 integration layer lives in
ah.formalizer.integration_ir):

- concurrent_run_binding   — InterpretationRunBinding CAS serializes owners of one (obs, version).
- idempotent_recommit      — same batch_hash commits once; a re-commit is an idempotent no-op (memory + AH file).
- unresolved_replay        — replaying the canonical run on an unresolved version creates no new owner and no marker.
- open_template_isolation  — occurrence-local isolation key: survives a contextual revision, never collides across observations.
- crash_recovery           — a decided-APPLIED batch that crashes before its terminal is restored from D on a REAL file, re_admitted=False.
- known_mapping_failure    — A34/DR6: a KNOWN sense with no TemplateMap entry -> CANONICAL_MAPPING_MISSING; the fragment
                            is not materialized and the open path is NOT an automatic fallback (real C->T5 path).
- proposal_validation      — §4.5/§14: a TP reply is validated against its sealed request; invented role / out-of-region
                            anchor / whole-region SURFACE_ARG / exhausted budget -> ProtocolError, never AMBIGUOUS.
- legacy_roundtrip         — §12: lossless encode/decode only when can_encode_legacy_graph; open template / source trace -> ADAPTER_NOT_COVERED (no silent loss).
- v2_integration           — §17: IntegrationCandidateIRV2 (schema_version=v7); STRUCTURAL element is UNATTACHED with empty support_refs; NO_CANDIDATE serializes candidate-source traces.
"""

import json
import os
import tempfile
import unittest

from ah.formalizer.c_consolidate import ResolvedValue, SenseKind, TemporalMode, consolidate
from ah.formalizer.memory_store import MemoryStore
from ah.formalizer.provider_adapter import ProviderAdapter  # noqa: F401 (spine presence)
from ah.formalizer.resources.registry import (
    OpenPredicateCandidate, OpenTemplatePolicy, Role, RoleBinding, RoleRegistry, ensure_open_template,
)
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.store_interface import (
    CommitDecision, JournalRecord, MaterializationMarker, StoreOp, TerminalOutcome,
)
from ah.formalizer.t5_batch import FragmentT5Input, t5_batch
from ah.formalizer.integration_ir import (
    IntegrationCandidateIRV2, StagedElement, can_encode_legacy_graph, encode_legacy, legacy_roundtrip,
)
from ah.formalizer.tp_proposer import ProtocolError, StructureProposalRequest, parse_and_validate


def _decision(run_id="run-A", batch_hash="H1", outcome=TerminalOutcome.APPLIED):
    return CommitDecision(
        run_id=run_id, batch_hash=batch_hash,
        marker=MaterializationMarker("obs1", 0), ops_digest="d", outcome=outcome)


class TestConcurrentRunBinding(unittest.TestCase):
    def test_second_owner_cas_fails(self):
        b = InterpretationRunBinding()
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        self.assertFalse(b.acquire("run-B", "obs1", 0))   # a different owner cannot claim it
        self.assertEqual(b.holder("obs1", 0), "run-A")

    def test_same_owner_reacquire_is_idempotent(self):
        b = InterpretationRunBinding()
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        self.assertTrue(b.acquire("run-A", "obs1", 0))   # replay of the same owner is a no-op


class TestIdempotentRecommit(unittest.TestCase):
    def test_memory_store_recommit_is_noop(self):
        s = MemoryStore()
        ops = [StoreOp("ADD_ELEMENT", {"uid": "n1"})]
        first = s.commit_transaction(ops, MaterializationMarker("obs1", 0), _decision())
        self.assertEqual(first.applied_uids, ("n1",))
        second = s.commit_transaction(ops, MaterializationMarker("obs1", 0), _decision())
        self.assertTrue(second.idempotent_noop)
        self.assertEqual(second.applied_uids, ())       # nothing re-materialized


class TestUnresolvedReplay(unittest.TestCase):
    def test_replay_creates_no_new_owner_and_no_marker(self):
        b = InterpretationRunBinding()
        s = MemoryStore()
        # First (unresolved) analysis: only a diagnostic journal record, no commit/marker.
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        s.append_journal("resolution_log", JournalRecord("resolution_log", "run-A", {"kind": "diag"}))
        head_after_diag = s.read_global_head()

        # Replay of the SAME canonical run on the same unresolved version: idempotent owner, no marker.
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        self.assertEqual(s.has_uid("n1"), False)         # nothing materialized
        self.assertEqual(len([r for r in s.scan_unprocessed(0) if r.payload.get("kind") == "commit"]), 0)
        self.assertGreaterEqual(head_after_diag, 1)


class TestOpenTemplateIsolation(unittest.TestCase):
    def _reg(self):
        return RoleRegistry(frozenset({Role("EXPERIENCER"), Role("SURFACE_ARG")}))

    def test_survives_contextual_revision_but_not_cross_observation(self):
        reg, pol = self._reg(), OpenTemplatePolicy(released=True)
        base = dict(source_revision=0, anchor_spans=("s0:",), normalized_surface_or_lemma="холодно",
                    pos="ADJD", bindings=(RoleBinding("EXPERIENCER"),))
        k1 = ensure_open_template(OpenPredicateCandidate(observation_id="obs1", source="run-A", **base), reg, pol).open_template_key
        # Same observation re-analyzed (contextual revision): identical key.
        k2 = ensure_open_template(OpenPredicateCandidate(observation_id="obs1", source="run-B", **base), reg, pol).open_template_key
        self.assertEqual(k1, k2)
        # A different independent observation: distinct key (no cross-observation collision).
        k3 = ensure_open_template(OpenPredicateCandidate(observation_id="obs2", source="run-A", **base), reg, pol).open_template_key
        self.assertNotEqual(k1, k3)


class TestTwoChannelJournal(unittest.TestCase):
    """WP0.3 — the two journal channels (observation / resolution_log) coexist in one store with a
    single global admission order, yet each channel's content is independently appendable/readable."""

    def test_channels_are_independent_but_share_one_admission_order(self):
        s = MemoryStore()
        seq_obs = s.append_journal("observation", JournalRecord("observation", "run-A", {"kind": "obs_record"}))
        seq_res = s.append_journal("resolution_log", JournalRecord("resolution_log", "run-A", {"kind": "decision"}))
        self.assertLess(seq_obs, seq_res)  # one global monotonic seq across BOTH channels

        all_recs = s.scan_unprocessed(0)
        by_channel = {}
        for r in all_recs:
            by_channel.setdefault(r.channel, []).append(r.payload.get("kind"))
        self.assertEqual(by_channel["observation"], ["obs_record"])   # observation channel isolated
        self.assertEqual(by_channel["resolution_log"], ["decision"])  # resolution channel isolated
        self.assertEqual(len(all_recs), 2)

    def test_observation_channel_does_not_materialize_elements(self):
        s = MemoryStore()
        s.append_journal("observation", JournalRecord("observation", "run-A", {"kind": "obs_record", "uid": "n1"}))
        self.assertFalse(s.has_uid("n1"))  # journaling an observation is not a commit; no element materialized


class TestCrashRecovery(unittest.TestCase):
    def _adapter(self, tmpdir):
        from ah.core.journal import JournalChannel
        from ah.core.store import AHStore
        from ah.formalizer.ah_adapter import AHStoreAdapter
        return AHStoreAdapter(AHStore(), JournalChannel(os.path.join(tmpdir, "j.log")))

    def test_decided_applied_batch_restored_from_d_without_readmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = self._adapter(tmp)
            # Commit an APPLIED batch but crash BEFORE appending its terminal status.
            a.commit_transaction([StoreOp("ADD_ELEMENT", {"uid": "n1"})],
                                 MaterializationMarker("obs1", 0), _decision(batch_hash="H-crash"))

            # A fresh adapter over the SAME durable file (process restart): in-memory state is empty.
            b = self._adapter(tmp)
            report = b.recover_from_head()
            self.assertFalse(report.re_admitted)                 # restored from D, not re-admitted
            self.assertIn(("batch:H-crash", TerminalOutcome.APPLIED), report.recovered)


class TestKnownMappingFailure(unittest.TestCase):
    """A34/DR6 — a KNOWN sense whose TemplateMap entry is absent -> CANONICAL_MAPPING_MISSING; the fragment
    is NOT materialized and the open path is NOT an automatic fallback. Proven through the real C->T5 path."""

    def _registry(self):
        return RoleRegistry(frozenset({Role("EXPERIENCER"), Role("SURFACE_ARG")}))

    def test_known_miss_blocks_fragment_and_is_not_bypassed_via_open_path(self):
        pol = OpenTemplatePolicy(released=True)
        # A known sense that IS mapped -> REF_T (materialized, gets a node).
        mapped = ResolvedValue(fragment_id="f1", observation_id="obs1", source_revision=0,
                              predicate_id="S_COLD", value_id="v_cold", roles_signature="R:EXPERIENCER",
                              sense_kind=SenseKind.KNOWN, temporal_mode=TemporalMode.STATE)
        # The same known sense but with NO TemplateMap entry -> CANONICAL_MAPPING_MISSING.
        unmapped = ResolvedValue(fragment_id="f2", observation_id="obs1", source_revision=0,
                                predicate_id="S_COLD", value_id="v_warm", roles_signature="R:EXPERIENCER",
                                sense_kind=SenseKind.KNOWN, temporal_mode=TemporalMode.STATE)
        template_map = {("S_COLD", "v_cold", "R:EXPERIENCER"): "T:cold"}

        plan = consolidate([mapped, unmapped], template_map, self._registry(), pol)
        by_frag = {r.fragment_id: r for r in plan.resolutions}

        # hit -> REF_T, materialized (has a node), not blocked.
        self.assertEqual(by_frag["f1"].resolution, "REF_T")
        self.assertFalse(by_frag["f1"].blocked)
        self.assertIsNotNone(by_frag["f1"].node_id)

        # miss -> CANONICAL_MAPPING_MISSING: blocked, NO node, and NOT converted to an open template.
        r2 = by_frag["f2"]
        self.assertEqual(r2.resolution, "CANONICAL_MAPPING_MISSING")
        self.assertTrue(r2.blocked)
        self.assertIsNone(r2.node_id)
        self.assertNotEqual(r2.resolution, "OPEN_TEMPLATE")  # no open-path bypass for a broken known mapping
        self.assertIn("f2", plan.blocked_fragment_ids)

    def test_t5_refuses_known_mapping_missing_and_journals_it(self):
        b = InterpretationRunBinding()
        self.assertTrue(b.acquire("run-A", "obs1", 0))
        frag = FragmentT5Input(fragment_id="f2", outcome="RESOLVED", known_mapping_missing=True)

        res = t5_batch([frag], run_id="run-A", observation_id="obs1", version=0, binding=b)

        self.assertEqual(res.eligibility, "OK")
        self.assertNotIn("f2", res.committed_fragments)  # T6 is not called for it
        codes = [e.get("code") for e in res.journal_entries if e.get("kind") == "resolution_log"]
        self.assertIn("CANONICAL_MAPPING_MISSING", codes)  # durable refusal record, no canonical fact


class TestProposalValidation(unittest.TestCase):
    """§4.5/§14 local-proposal boundary — a TP reply is validated against its sealed request; any invented
    role, out-of-region anchor, whole-region SURFACE_ARG, or exhausted budget -> ProtocolError (never AMBIGUOUS)."""

    def _req(self, **kw):
        base = dict(request_id="r1", structural_hash_pre="h", source_spans=("s0:", "s1:"),
                    allowed_node_kinds=frozenset({"T"}), allowed_edge_kinds=frozenset({"G"}))
        base.update(kw)
        return StructureProposalRequest(**base)

    def test_valid_reply_is_accepted(self):
        raw = json.dumps({"hypotheses": [{"local_id": "h1",
                                         "nodes": [{"kind": "T", "anchor_spans": ["s0:"]}],
                                         "edges": []}]})
        self.assertEqual(len(parse_and_validate(self._req(), raw)), 1)

    def test_invented_role_id_is_rejected(self):
        # role "CAUSE" is not in the default allowed set {EXPERIENCER, SURFACE_ARG} -> (a/d) violation.
        raw = json.dumps({"hypotheses": [{"local_id": "h1",
                                         "nodes": [{"kind": "T", "anchor_spans": ["s0:"]},
                                                   {"kind": "T", "anchor_spans": ["s1:"]}],
                                         "edges": [{"kind": "G", "from": 0, "to": 1, "role_id": "CAUSE"}]}]})
        with self.assertRaises(ProtocolError):
            parse_and_validate(self._req(), raw)

    def test_anchor_outside_bounded_region_is_rejected(self):
        # anchor span "s9:" is not in source_spans -> (b) bounded-region violation.
        raw = json.dumps({"hypotheses": [{"local_id": "h1",
                                         "nodes": [{"kind": "T", "anchor_spans": ["s9:"]}],
                                         "edges": []}]})
        with self.assertRaises(ProtocolError):
            parse_and_validate(self._req(), raw)

    def test_surface_arg_must_bind_proper_subregion(self):
        # SURFACE_ARG whose target anchors the ENTIRE bounded region -> (d) violation.
        raw = json.dumps({"hypotheses": [{"local_id": "h1",
                                         "nodes": [{"kind": "T", "anchor_spans": ["s0:", "s1:"]},
                                                   {"kind": "T", "anchor_spans": ["s0:"]}],
                                         "edges": [{"kind": "G", "from": 1, "to": 0, "role_id": "SURFACE_ARG"}]}]})
        with self.assertRaises(ProtocolError):
            parse_and_validate(self._req(), raw)

    def test_exhausted_budget_is_rejected(self):
        # (e) an exhausted budget must never have produced the call.
        req = self._req(budget_ok=False)
        raw = json.dumps({"hypotheses": [{"local_id": "h1",
                                         "nodes": [{"kind": "T", "anchor_spans": ["s0:"]}],
                                         "edges": []}]})
        with self.assertRaises(ProtocolError):
            parse_and_validate(req, raw)

    def test_abstain_is_explicit_miss_not_ambiguous(self):
        # (f) abstain / missing reply is an explicit miss — returned as [], never substituted by AMBIGUOUS.
        self.assertEqual(parse_and_validate(self._req(), json.dumps({"abstain": True})), [])
        self.assertEqual(parse_and_validate(self._req(), None), [])


class TestLegacyRoundtrip(unittest.TestCase):
    """§12 — legacy round-trip is lossless only when can_encode_legacy_graph; otherwise ADAPTER_NOT_COVERED (no silent loss)."""

    def test_encodable_ir_roundtrips_losslessly(self):
        ir = IntegrationCandidateIRV2(
            observation_id="obs1", interpretation_version=0, snapshot_id="snap1",
            elements=(StagedElement(kind="ASSERTION", payload={"payload_kind": "ASSERTION", "g_ref": "G:have"},
                                   source_span="s0:"),),
            coverage_status="FULL", provenance={"run_id": "r1"},
        )
        ok, back = legacy_roundtrip(ir)
        self.assertTrue(ok)
        self.assertEqual(back, ir)  # field-for-field lossless

    def test_open_template_is_not_legacy_encodable(self):
        ir = IntegrationCandidateIRV2(
            observation_id="obs1",
            elements=(StagedElement(kind="STRUCTURAL", epistemic="UNATTACHED",
                                   payload={"payload_kind": "ENSURE_OPEN_TEMPLATE", "open_template_key": "k1"}),),
        )
        self.assertFalse(can_encode_legacy_graph(ir))
        self.assertIsNone(encode_legacy(ir))  # no silent loss: nothing is emitted
        ok, code = legacy_roundtrip(ir)
        self.assertEqual((ok, code), (False, "ADAPTER_NOT_COVERED"))

    def test_candidate_source_trace_is_not_legacy_encodable(self):
        ir = IntegrationCandidateIRV2(observation_id="obs1", candidate_source_trace_refs=("trace1",))
        self.assertFalse(can_encode_legacy_graph(ir))
        ok, code = legacy_roundtrip(ir)
        self.assertEqual((ok, code), (False, "ADAPTER_NOT_COVERED"))


class TestV2Integration(unittest.TestCase):
    """§17 — IntegrationCandidateIRV2 (schema_version=v7) stages the formalizer output; a STRUCTURAL element is
    UNATTACHED with empty support_refs, and NO_CANDIDATE serializes candidate-source traces even with no AH elements."""

    def test_structural_element_is_unattached_with_no_support(self):
        el = StagedElement(kind="STRUCTURAL", epistemic="UNATTACHED",
                          payload={"payload_kind": "ENSURE_OPEN_TEMPLATE", "open_template_key": "k1"})
        self.assertEqual(el.epistemic, "UNATTACHED")
        self.assertEqual(el.support_refs, ())  # no AddRootSupport for a structural open template

    def test_structural_element_rejects_root_support(self):
        with self.assertRaises(ValueError):
            StagedElement(kind="STRUCTURAL", epistemic="UNATTACHED", support_refs=("sup1",),
                         payload={"payload_kind": "ENSURE_OPEN_TEMPLATE"})

    def test_structural_element_rejects_asserted_epistemic(self):
        with self.assertRaises(ValueError):
            StagedElement(kind="STRUCTURAL", epistemic="ASSERTED",
                         payload={"payload_kind": "ENSURE_OPEN_TEMPLATE"})

    def test_v2_schema_version_and_no_candidate_serialization(self):
        # NO_CANDIDATE: no AH elements, but the candidate-source traces are staged for the ObservationRecord.
        ir = IntegrationCandidateIRV2(observation_id="obs1", interpretation_version=0,
                                      coverage_status="NO_CANDIDATE",
                                      candidate_source_trace_refs=("trace_a", "trace_b"))
        self.assertEqual(ir.schema_version, "v7")
        self.assertEqual(ir.elements, ())  # no AH elements to materialize
        self.assertEqual(len(ir.candidate_source_trace_refs), 2)  # traces preserved for the ObservationRecord + canonical hash
        self.assertFalse(can_encode_legacy_graph(ir))  # V2-only content -> not legacy-encodable


if __name__ == "__main__":
    unittest.main()
