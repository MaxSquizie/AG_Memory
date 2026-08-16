from __future__ import annotations

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

from test_acceptance_regressions_1218 import AcceptanceMorphology, RequestMorphology
from test_acceptance_regressions_1219 import DiscourseMorphology
from test_semantic_roots_1240 import PersonalRelativeMorphology

PROJECT = Path(__file__).resolve().parents[1]


class RecordingBackend:
    def __init__(self, answers: dict[str, list[str]] | None = None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
        self.calls: list[tuple[str, str, dict]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, dict(override or {})))
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")
        return LLMResponse(values.pop(0), {})


def make_parser(morphology, backend: RecordingBackend | None = None) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend or RecordingBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


class SemanticRoots1241Tests(unittest.TestCase):
    def test_ordinary_accusative_pronoun_is_not_sent_to_participant_semantic_probe(self):
        backend = RecordingBackend()
        result = make_parser(AcceptanceMorphology(), backend).parse(
            "Иван написал письмо и отправил его Марии."
        ).perception
        send = result.assertions[1]
        roles = {actant.role: actant for actant in send.actants}
        self.assertEqual(roles[ActantRole.OBJECT].mention, "его")
        self.assertEqual(roles[ActantRole.RECIPIENT].normalized_hint, "Мария")
        self.assertEqual(backend.calls, [])

    def test_discourse_pronoun_object_uses_coreference_after_deterministic_object_role(self):
        backend = RecordingBackend()
        result = make_parser(DiscourseMorphology(), backend).parse(
            "Сергей положил ключ на стол. Потом он взял его."
        ).perception
        placed, took = result.assertions
        placed_object = next(a for a in placed.actants if a.role == ActantRole.OBJECT)
        took_object = next(a for a in took.actants if a.role == ActantRole.OBJECT)
        self.assertEqual(took_object.entity_ref, placed_object.entity_ref)
        self.assertNotIn(ActantRole.TIME, {a.role for a in took.actants})
        self.assertEqual(backend.calls, [])

    def test_recipient_probe_runs_only_after_content_object_conflict_is_proven(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_content_addressee": ["CONTENT_ADDRESSEE"],
            "perception_control_subject": ["SECOND"],
        })
        result = make_parser(RequestMorphology(), backend).parse(
            "Иван попросил Марию прочитать книгу."
        ).perception
        parent, child = result.assertions
        self.assertEqual(
            [role for role, _prompt, _override in backend.calls],
            [
                "perception_frame_relation",
                "perception_content_addressee",
                "perception_control_subject",
            ],
        )
        recipient = next(a for a in parent.actants if a.role == ActantRole.RECIPIENT)
        content = next(a for a in parent.actants if a.role == ActantRole.OBJECT)
        self.assertEqual(content.candidate_ref, child.local_id)
        self.assertEqual(
            next(a.entity_ref for a in child.actants if a.role == ActantRole.SUBJECT),
            recipient.entity_ref,
        )
        controller_prompt = backend.calls[-1][1]
        self.assertIn("PARTICIPANTS:\nFIRST =", controller_prompt)
        self.assertIn("CHOICES:\nFIRST\nSECOND", controller_prompt)
        self.assertNotIn("CONTROLLER OPTIONS:", controller_prompt)

    def test_personal_provenance_blocks_cross_domain_name_hijack(self):
        text = "Я положил книгу рядом с журналом, который был новым."
        morphology = PersonalRelativeMorphology()
        perception = make_parser(morphology).parse(text).perception
        perception = replace(
            perception,
            assertions=tuple(
                replace(
                    assertion,
                    predicate=replace(
                        assertion.predicate,
                        template_candidate=TemplateCandidate(tuple(a.role for a in assertion.actants)),
                    ),
                )
                for assertion in perception.assertions
            ),
        )

        core = AHCore(uid_generator=SequentialUidGenerator())
        user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
        self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")})
        generic_journal = core.add_entity(Domain.C, {"name": Property("name", "журнал", "str")})
        context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
        TextSensoryService(core, morphology).process(text)

        commit = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.02)).integrate_external(
            perception, context
        )
        self.assertEqual([item.domain for item in commit.assertions], [Domain.P, Domain.P])
        p_journals = core.store.find_entities_by_name("журнал", Domain.P)
        c_journals = core.store.find_entities_by_name("журнал", Domain.C)
        self.assertEqual(len(p_journals), 1)
        self.assertEqual([item.uid for item in c_journals], [generic_journal.uid])
        self.assertNotEqual(p_journals[0].uid, generic_journal.uid)


if __name__ == "__main__":
    unittest.main()
