# -*- coding: utf-8 -*-
"""WP2.1 — C-consolidation tests (V7 §7.1).

Proves the deterministic decision invariants on a pure module (no store writes):
KNOWN via TemplateMap / CANONICAL_MAPPING_MISSING blocks without open bypass; OPEN_LEXICAL -> UNLINKED
EXACT_ATTESTATION with an occurrence-local key that survives a contextual revision but never collides across
observations; incompatible senses sharing one key stay AMBIGUOUS; RelationKey dedup (STATE merges, EVENT and
UNKNOWN separate); identity conflict blocks the fragment.
"""

import unittest

from ah.formalizer.c_consolidate import (
    IdentityRef, ResolvedValue, SenseKind, TemporalMode, consolidate, relation_key, _open_key,
)
from ah.formalizer.resources.registry import OpenTemplatePolicy, Role, RoleRegistry


def reg():
    # SURFACE_ARG is a mandatory role the registry must register on release.
    return RoleRegistry(frozenset({Role("EXPERIENCER"), Role("SURFACE_ARG")}))


POL = OpenTemplatePolicy(released=True)


def rv(fid="f1", obs="obs1", rev=0, pred="P", val="v", roles="r", kind=SenseKind.KNOWN,
       mode=TemporalMode.STATE, lemma="", pos="UNKNOWN", label=""):
    return ResolvedValue(
        fragment_id=fid, observation_id=obs, source_revision=rev, predicate_id=pred, value_id=val,
        roles_signature=roles, sense_kind=kind, temporal_mode=mode,
        normalized_surface_or_lemma=lemma, pos=pos, sense_label=label)


class TestKnownSense(unittest.TestCase):
    def test_hit_yields_ref_t(self):
        plan = consolidate([rv()], {("P", "v", "r"): "T123"}, reg(), POL)
        res = plan.resolutions[0]
        self.assertEqual(res.resolution, "REF_T")
        self.assertEqual(res.template_uid, "T123")
        self.assertFalse(res.blocked)

    def test_miss_blocks_without_open_bypass(self):
        # No mapping for the chosen known sense -> CANONICAL_MAPPING_MISSING; fragment blocked, no open T.
        plan = consolidate([rv()], {}, reg(), POL)
        res = plan.resolutions[0]
        self.assertEqual(res.resolution, "CANONICAL_MAPPING_MISSING")
        self.assertTrue(res.blocked)
        self.assertIn("f1", plan.blocked_fragment_ids)
        self.assertIsNone(res.open_template_key)  # the open path is NOT an automatic fallback


class TestOpenLexical(unittest.TestCase):
    def test_single_sense_unlinked_exact_attestation(self):
        v = rv(kind=SenseKind.OPEN_LEXICAL, lemma="холодно", pos="ADJD")
        plan = consolidate([v], {}, reg(), POL)
        res = plan.resolutions[0]
        self.assertEqual(res.resolution, "OPEN_TEMPLATE")
        self.assertFalse(res.blocked)
        self.assertIsNotNone(res.open_template_key)

    def test_key_survives_reanalysis_but_not_text_change_or_cross_observation(self):
        # The key EXCLUDES interpretation_version (re-analyzing the same text+revision keeps it) but INCLUDES
        # source_revision (text identity) and observation_id (never collides across observations).
        a = rv(obs="obs1", rev=0, kind=SenseKind.OPEN_LEXICAL, lemma="холодно")
        b = rv(fid="f2", obs="obs1", rev=0, kind=SenseKind.OPEN_LEXICAL, lemma="холодно")  # same text+revision re-analyzed
        c = rv(fid="f3", obs="obs1", rev=1, kind=SenseKind.OPEN_LEXICAL, lemma="холодно")  # source TEXT changed
        d = rv(fid="f4", obs="obs2", rev=0, kind=SenseKind.OPEN_LEXICAL, lemma="холодно")  # independent observation
        self.assertEqual(_open_key(a), _open_key(b))   # survives re-analysis of the same text (no interpretation_version in key)
        self.assertNotEqual(_open_key(a), _open_key(c))  # a changed source revision changes the key
        self.assertNotEqual(_open_key(a), _open_key(d))  # never collides across observations

    def test_incompatible_senses_same_key_stay_ambiguous(self):
        x = rv(fid="f1", kind=SenseKind.OPEN_LEXICAL, lemma="холодно", label="temperature")
        y = rv(fid="f2", kind=SenseKind.OPEN_LEXICAL, lemma="холодно", label="attitude")  # same key, distinct sense
        self.assertEqual(_open_key(x), _open_key(y))
        plan = consolidate([x, y], {}, reg(), POL)
        for res in plan.resolutions:
            self.assertEqual(res.resolution, "AMBIGUOUS_SENSE")
            self.assertTrue(res.blocked)


class TestRelationKeyDedup(unittest.TestCase):
    def test_state_same_key_merges_to_one_node(self):
        a = rv(fid="f1", obs="obs1")
        b = rv(fid="f2", obs="obs1")  # identical RelationKey, both STATE
        self.assertEqual(relation_key(a), relation_key(b))
        plan = consolidate([a, b], {("P", "v", "r"): "T"}, reg(), POL)
        nodes = [r.node_id for r in plan.resolutions]
        self.assertEqual(nodes[0], nodes[1])            # merged into one canonical N
        self.assertEqual(len(plan.node_groups), 1)

    def test_event_occurrences_never_merge(self):
        a = rv(fid="f1", obs="obs1", mode=TemporalMode.EVENT)
        b = rv(fid="f2", obs="obs1", mode=TemporalMode.EVENT)  # same key, EVENT
        plan = consolidate([a, b], {("P", "v", "r"): "T"}, reg(), POL)
        nodes = [r.node_id for r in plan.resolutions]
        self.assertNotEqual(nodes[0], nodes[1])         # separate node each

    def test_unknown_mode_not_merged_and_reported(self):
        a = rv(fid="f1", obs="obs1", mode=TemporalMode.UNKNOWN)
        b = rv(fid="f2", obs="obs1", mode=TemporalMode.STATE)  # mixed -> not merged
        plan = consolidate([a, b], {("P", "v", "r"): "T"}, reg(), POL)
        nodes = [r.node_id for r in plan.resolutions]
        self.assertNotEqual(nodes[0], nodes[1])
        self.assertTrue(any(d.startswith("STATE_CLASS_UNKNOWN") for d in plan.diagnostics))

    def test_open_lexical_cross_observation_not_merged_by_lemma(self):
        a = rv(fid="f1", obs="obs1", kind=SenseKind.OPEN_LEXICAL, lemma="холодно")
        b = rv(fid="f2", obs="obs2", kind=SenseKind.OPEN_LEXICAL, lemma="холодно")  # same lemma/roles, different obs
        self.assertNotEqual(relation_key(a), relation_key(b))  # occurrence-local key embeds observation_id


class TestIdentityUnification(unittest.TestCase):
    def test_conflict_blocks_fragment(self):
        vals = [rv(fid="f1")]
        refs = [
            IdentityRef(ref_id="r1", fragment_id="f1", entity_key="E1"),
            IdentityRef(ref_id="r1", fragment_id="f1", entity_key="E2"),  # same ref, two entities -> conflict
        ]
        plan = consolidate(vals, {("P", "v", "r"): "T"}, reg(), POL, identity_refs=refs)
        res = plan.resolutions[0]
        self.assertEqual(res.resolution, "IDENTITY_CONFLICT")
        self.assertTrue(res.blocked)
        self.assertIn("f1", plan.blocked_fragment_ids)

    def test_consistent_identity_does_not_block(self):
        vals = [rv(fid="f1")]
        refs = [IdentityRef(ref_id="r1", fragment_id="f1", entity_key="E1")]
        plan = consolidate(vals, {("P", "v", "r"): "T"}, reg(), POL, identity_refs=refs)
        self.assertEqual(plan.resolutions[0].resolution, "REF_T")
        self.assertNotIn("f1", plan.blocked_fragment_ids)


if __name__ == "__main__":
    unittest.main()
