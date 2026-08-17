from __future__ import annotations

from legacy_semantic_fixture import legacy_semantic_answer

from dataclasses import replace
from pathlib import Path
import unittest

from ah.agent import InteractionContext
from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import TemplateCandidate, TextSensoryService
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import MorphInfo

from test_acceptance_regressions_1218 import AcceptanceMorphology, RequestMorphology
from test_slm_pairwise_1228 import NestedMorphology

PROJECT = Path(__file__).resolve().parents[1]


class ScriptedBackend:
    def __init__(self, answers: dict[str, list[str]] | None = None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
        self.calls: list[tuple[str, str, dict]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov))
        values = self.answers.get(role)
        if not values:
            fallback = legacy_semantic_answer(role, prompt)
            if fallback is not None:
                return LLMResponse(str(fallback), {})
            raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")
        return LLMResponse(values.pop(0), {"choice_margin": 0.0})


def parser(backend: ScriptedBackend, morphology) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


class PersonalRelativeMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        special = {
            "был": MorphInfo("быть", "VERB", score=1.0),
            "новым": MorphInfo("новый", "ADJF", case="ablt", score=1.0),
        }
        value = special.get(word.casefold())
        if value is not None:
            return (value,)
        return super().analyze_all(word)


class SemanticRoots1240Tests(unittest.TestCase):
    def test_request_uses_recipient_plus_nested_object_and_recipient_controls_child(self):
        backend = ScriptedBackend({
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_control_subject": ["SECOND"],
        })
        result = parser(backend, RequestMorphology()).parse(
            "Иван попросил Марию прочитать книгу."
        ).perception
        parent, child = result.assertions
        recipient = next(a for a in parent.actants if a.role == ActantRole.RECIPIENT)
        content = next(a for a in parent.actants if a.role == ActantRole.OBJECT)
        child_subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(content.candidate_ref, child.local_id)
        self.assertEqual(child_subject.entity_ref, recipient.entity_ref)
        roles = [role for role, _prompt, _ov in backend.calls]
        self.assertIn("perception_frame_relation", roles)
        self.assertIn("perception_role_cue", roles)
        self.assertIn("perception_control_subject", roles)
        self.assertTrue(all("choice_outputs" not in ov for _role, _prompt, ov in backend.calls))

    def test_wanted_situation_is_nested_object_not_purpose(self):
        backend = ScriptedBackend({"perception_frame_relation": ["CONTENT_LINK"]})
        result = parser(backend, NestedMorphology()).parse("Мария хочет купить билет.").perception
        parent, child = result.assertions
        nested = next(a for a in parent.actants if a.candidate_ref == child.local_id)
        self.assertEqual(nested.role, ActantRole.OBJECT)
        self.assertNotIn(ActantRole.PURPOSE, {a.role for a in parent.actants})
        self.assertNotIn("choice_outputs", backend.calls[0][2])

    def test_relative_noun_inside_relational_location_reuses_parent_entity_ref(self):
        backend = ScriptedBackend({"perception_antecedent_choice": ["C3"]})
        result = parser(backend, PersonalRelativeMorphology()).parse(
            "Я положил книгу рядом с журналом, который был новым.",
            structural_resolution="PREDICATE_ATTACHMENT",
        ).perception
        placed, described = result.assertions
        location = next(a for a in placed.actants if a.role == ActantRole.LOCATION)
        subject = next(a for a in described.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(location.evidence.text, "рядом с журналом")
        self.assertEqual(subject.evidence.text, "журналом")
        self.assertIsNotNone(location.entity_ref)
        self.assertEqual(subject.entity_ref, location.entity_ref)
        self.assertTrue(all("choice_outputs" not in ov for _r, _p, ov in backend.calls))

    def test_shared_relative_identity_preserves_personal_domain_provenance(self):
        text = "Я положил книгу рядом с журналом, который был новым."
        morphology = PersonalRelativeMorphology()
        perception = parser(
            ScriptedBackend({"perception_antecedent_choice": ["C3"]}), morphology
        ).parse(text, structural_resolution="PREDICATE_ATTACHMENT").perception
        # The normal LLM parser wrapper supplies occurrence-only TemplateCandidates;
        # mirror that boundary here without adding any hidden valency.
        assertions = tuple(
            replace(
                assertion,
                predicate=replace(
                    assertion.predicate,
                    template_candidate=TemplateCandidate(tuple(a.role for a in assertion.actants)),
                ),
            )
            for assertion in perception.assertions
        )
        perception = replace(perception, assertions=assertions)

        core = AHCore(uid_generator=SequentialUidGenerator())
        user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
        self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")})
        context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
        TextSensoryService(core, morphology).process(text)
        commit = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.02)).integrate_external(
            perception, context
        )
        self.assertEqual(
            [core.store.domain_of(item.ref.uid) for item in commit.assertions],
            [Domain.P, Domain.P],
        )
        self.assertEqual(len(core.store.find_entities_by_name("журнал", Domain.P)), 1)
        self.assertEqual(core.store.find_entities_by_name("журнал", Domain.C), ())


if __name__ == "__main__":
    unittest.main()
