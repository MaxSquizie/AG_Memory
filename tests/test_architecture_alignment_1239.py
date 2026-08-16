from __future__ import annotations

import unittest
from pathlib import Path

from ah.agent import InteractionContext
from ah.config import IntegrationSettings, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService, TemplateResolutionError
from ah.integration.template_resolver import TemplateResolver
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.llm_parser import LLMPerceptionService, LLMPerceptionSettings


class NoCallBackend:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, dict(override or {}), system))
        raise AssertionError(f"production template proposal must not call LLM: {role}")


PROJECT = Path(__file__).resolve().parents[1]


class ArchitectureAlignment1239Tests(unittest.TestCase):
    def test_production_template_candidate_contains_only_explicit_roles_and_makes_no_llm_call(self):
        backend = NoCallBackend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=12, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
        )
        result = parser.propose_template_candidate(
            "Иван подарил книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
            ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        )
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))
        self.assertEqual(backend.calls, [])
        self.assertTrue(any(t.stage == "template_candidate_explicit_roles" for t in result.traces))

    def test_existing_t_expands_in_place_from_later_explicit_recipient(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        resolver = TemplateResolver(core, Domain.C)
        created = resolver.resolve(
            PredicateCandidate(
                "подарил", "подарить",
                template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        expanded = resolver.resolve(
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(expanded.template.uid, created.template.uid)
        self.assertEqual(
            expanded.template.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        symbol = core.store.find_symbol_by_form("подарить")
        self.assertEqual(len(core.store.find_templates_by_predicate(symbol.uid)), 1)

    def test_old_n_remains_valid_after_t_expansion(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        resolver = TemplateResolver(core, Domain.C)
        created = resolver.resolve(
            PredicateCandidate(
                "подарил", "подарить",
                template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        ivan = core.add_entity(Domain.C, {"name": Property("name", "Иван", "str")})
        book = core.add_entity(Domain.C, {"name": Property("name", "книга", "str")})
        old_n, _ = core.add_hypernode(
            Domain.C,
            core.ref(created.template.uid),
            {ActantRole.SUBJECT: core.ref(ivan.uid), ActantRole.OBJECT: core.ref(book.uid)},
            0.4,
        )
        resolver.resolve(
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(set(core.store.get_hypernode(old_n.uid).actants), {ActantRole.SUBJECT, ActantRole.OBJECT})
        # Rebuilding indexes after T edit must keep old semantic dedup working.
        same, created_again = core.add_hypernode(
            Domain.C,
            core.ref(created.template.uid),
            {ActantRole.SUBJECT: core.ref(ivan.uid), ActantRole.OBJECT: core.ref(book.uid)},
            0.4,
        )
        self.assertFalse(created_again)
        self.assertEqual(same.uid, old_n.uid)

    def test_requested_query_role_expands_schema_without_creating_fact(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
        context = InteractionContext(user_ref=core.ref(user.uid))
        service = IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings()))
        TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(
                "подарил", "подарить",
                template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        query = QueryCandidate(
            predicate=PredicateCandidate("подарил", "подарить"),
            actants=(
                ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                ActantCandidate(ActantRole.OBJECT, mention="книга"),
            ),
            requested_role=ActantRole.RECIPIENT,
            query_mode=QueryMode.FILL_ROLE,
        )
        commit = service.integrate_external(PerceptionResult("Кому Иван подарил книгу?", queries=(query,)), context)
        symbol = core.store.find_symbol_by_form("подарить")
        template = core.store.find_templates_by_predicate(symbol.uid)[0]
        self.assertIn(ActantRole.RECIPIENT, template.roles)
        self.assertEqual(commit.assertions, ())

    def test_multiple_incompatible_legacy_t_frames_fail_closed_instead_of_merging(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        symbol = core.add_abstract_symbol({"делать"})
        core.add_template(Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.OBJECT))
        core.add_template(Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.LOCATION))
        with self.assertRaisesRegex(TemplateResolutionError, "Cannot choose one of 2 canonical T frames"):
            TemplateResolver(core, Domain.C).resolve(
                PredicateCandidate("делает", "делать"),
                (ActantRole.SUBJECT, ActantRole.RECIPIENT),
            )

    def test_speculative_candidate_roles_are_not_committed_without_explicit_evidence(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        resolution = TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(
                "подарил", "подарить",
                template_candidate=TemplateCandidate(
                    (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT, ActantRole.SOURCE)
                ),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.assertEqual(resolution.template.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))

    def test_ah_core_forbids_template_role_removal(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        symbol = core.add_abstract_symbol({"читать"})
        template = core.add_template(
            Domain.C, core.ref(symbol.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME),
        )
        from dataclasses import replace
        with self.assertRaisesRegex(ValueError, "only grow monotonically"):
            core.edit_element(
                Domain.C,
                replace(template, roles=(ActantRole.SUBJECT, ActantRole.OBJECT)),
            )

    def test_ah_core_expand_template_roles_is_idempotent_and_canonical_ordered(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        symbol = core.add_abstract_symbol({"подарить"})
        template = core.add_template(
            Domain.C, core.ref(symbol.uid), (ActantRole.OBJECT, ActantRole.SUBJECT),
        )
        expanded = core.expand_template_roles(
            template.uid, (ActantRole.RECIPIENT, ActantRole.SUBJECT)
        )
        self.assertEqual(
            expanded.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        again = core.expand_template_roles(template.uid, (ActantRole.RECIPIENT,))
        self.assertEqual(again, expanded)


    def test_t_expansion_rolls_back_with_failed_integration_transaction(self):
        from unittest.mock import patch

        core = AHCore(uid_generator=SequentialUidGenerator())
        user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
        context = InteractionContext(user_ref=core.ref(user.uid))
        service = IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings()))
        created = TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(
                "подарил", "подарить",
                template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        result = PerceptionResult(
            "Иван подарил Марии книгу.",
            assertions=(
                AssertionCandidate(
                    "A1", PredicateCandidate("подарил", "подарить"),
                    (
                        ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                        ActantCandidate(ActantRole.OBJECT, mention="книга"),
                        ActantCandidate(ActantRole.RECIPIENT, mention="Мария"),
                    ),
                ),
            ),
        )
        with patch("ah.integration.service.EntityResolver.resolve", side_effect=RuntimeError("forced downstream failure")):
            with self.assertRaisesRegex(RuntimeError, "forced downstream failure"):
                service.integrate_external(result, context)
        persisted = core.store.get_template(created.template.uid)
        self.assertEqual(persisted.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))


    def test_llm_perception_template_boundary_also_makes_no_auxiliary_model_call(self):
        backend = NoCallBackend()
        service = LLMPerceptionService(
            backend,
            LLMPerceptionSettings(
                protocol="adaptive_v3",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=0,
                morphology_backend="none",
            ),
        )
        candidate = service.propose_template_candidate(
            "Иван подарил книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
            ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        )
        self.assertEqual(candidate.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))
        self.assertEqual(backend.calls, [])



if __name__ == "__main__":
    unittest.main()
