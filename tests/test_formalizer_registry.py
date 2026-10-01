# -*- coding: utf-8 -*-
"""WP0.4 — RoleRegistry / ProposalPolicy / OpenTemplatePolicy + EnsureOpenTemplate tests (V7 §2.1, §7.1).

Proves the write-boundary gates (REGISTRY_REJECT / OPEN_TEMPLATE_INVALID), the mandatory-role invariant,
the isolation-key properties (deterministic; survives a contextual revision but never collides across
independent observations; SURFACE_ARG attachment change forces a new key), and that there is no
nearest-match fallback to an existing canonical T.
"""

import unittest

from ah.formalizer.resources.registry import (
    MANDATORY_ROLES, OpenPredicateCandidate, OpenTemplateInvalid, OpenTemplatePolicy, ProposalPolicy,
    RegistryReject, Role, RoleBinding, RoleRegistry, build_role_signature, compute_open_template_key,
    ensure_open_template,
)


def _registry():
    return RoleRegistry(frozenset({
        Role("EXPERIENCER"),
        Role("SURFACE_ARG"),
        Role("AGENT", allowed_argument_kinds=("ENTITY",)),
    }))


def _policy(released: bool = True):
    return OpenTemplatePolicy(released=released)


def _cand(**kw):
    base = dict(observation_id="obs1", source_revision=0, anchor_spans=("s0:s2",),
                normalized_surface_or_lemma="холодно", pos="ADJD",
                bindings=(RoleBinding("EXPERIENCER"),))
    base.update(kw)
    return OpenPredicateCandidate(**base)


class TestRegistryInvariants(unittest.TestCase):
    def test_mandatory_roles_required(self):
        with self.assertRaises(ValueError):
            RoleRegistry(frozenset({Role("AGENT")}))  # missing EXPERIENCER + SURFACE_ARG

    def test_validate_unknown_role_rejects(self):
        with self.assertRaises(RegistryReject):
            _registry().validate_roles(["EXPERIENCER", "GHOST"])

    def test_proposal_policy_defaults_unreleased(self):
        self.assertFalse(ProposalPolicy().released)


class TestEnsureOpenTemplate(unittest.TestCase):
    def test_unreleased_policy_blocks_materialization(self):
        with self.assertRaises(OpenTemplateInvalid):
            ensure_open_template(_cand(), _registry(), _policy(released=False))

    def test_returns_unlinked_exact_attestation_only(self):
        t = ensure_open_template(_cand(), _registry(), _policy())
        self.assertEqual(t.semantic_status, "UNLINKED")
        self.assertEqual(t.inference_capabilities, ("EXACT_ATTESTATION",))
        # no canonical-alias surface by construction: only the four declared fields exist
        self.assertEqual(set(type(t).__dataclass_fields__), {"open_template_key", "semantic_status",
                                                            "inference_capabilities", "source"})

    def test_unknown_role_via_ensure_rejects(self):
        with self.assertRaises(RegistryReject):
            ensure_open_template(_cand(bindings=(RoleBinding("GHOST"),)), _registry(), _policy())

    def test_incompatible_argument_kind_rejected(self):
        cand = _cand(bindings=(RoleBinding("AGENT", arg_kind="EVENT"),))  # AGENT allows ENTITY only
        with self.assertRaises(OpenTemplateInvalid):
            ensure_open_template(cand, _registry(), _policy())


class TestIsolationKey(unittest.TestCase):
    def test_deterministic(self):
        k1 = ensure_open_template(_cand(), _registry(), _policy()).open_template_key
        k2 = ensure_open_template(_cand(), _registry(), _policy()).open_template_key
        self.assertEqual(k1, k2)

    def test_survives_contextual_revision_not_interpretation_version(self):
        # 'source' is provenance, not part of the key: a re-analysis of the same text keeps the key.
        k1 = ensure_open_template(_cand(source="run-A"), _registry(), _policy()).open_template_key
        k2 = ensure_open_template(_cand(source="run-B"), _registry(), _policy()).open_template_key
        self.assertEqual(k1, k2)

    def test_never_collides_across_independent_observations(self):
        k1 = ensure_open_template(_cand(observation_id="obs1"), _registry(), _policy()).open_template_key
        k2 = ensure_open_template(_cand(observation_id="obs2"), _registry(), _policy()).open_template_key
        self.assertNotEqual(k1, k2)

    def test_surface_arg_attachment_change_forces_new_key(self):
        a = _cand(bindings=(RoleBinding("SURFACE_ARG", slot_index=0, anchor_spans=("s1:",)),))
        b = _cand(bindings=(RoleBinding("SURFACE_ARG", slot_index=1, anchor_spans=("s2:",)),))
        ka = ensure_open_template(a, _registry(), _policy()).open_template_key
        kb = ensure_open_template(b, _registry(), _policy()).open_template_key
        self.assertNotEqual(ka, kb)

    def test_no_nearest_match_distinct_surfaces_do_not_merge(self):
        k1 = ensure_open_template(_cand(normalized_surface_or_lemma="холодно"), _registry(), _policy()).open_template_key
        k2 = ensure_open_template(_cand(normalized_surface_or_lemma="тепло"), _registry(), _policy()).open_template_key
        self.assertNotEqual(k1, k2)

    def test_role_signature_includes_surface_arg_details(self):
        sig = build_role_signature((RoleBinding("SURFACE_ARG", slot_index=3, case="gent"),))
        self.assertIn("slot=3", sig)
        self.assertIn("case=gent", sig)


if __name__ == "__main__":
    unittest.main()
