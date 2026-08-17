from __future__ import annotations

from legacy_semantic_fixture import legacy_semantic_answer

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import (
    AdaptiveParseError,
    AdaptivePerceptionParser,
    AdaptiveSettings,
)

from test_acceptance_regressions_1218 import RequestMorphology

PROJECT = Path(__file__).resolve().parents[1]


class RecordingBackend:
    def __init__(self, answers: dict[str, list[str]]):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt))
        values = self.answers.get(role)
        if not values:
            fallback = legacy_semantic_answer(role, prompt)
            if fallback is not None:
                return LLMResponse(str(fallback), {})
            raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")
        return LLMResponse(values.pop(0), {})


def make_parser(backend: RecordingBackend) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=RequestMorphology(),
    )


class SemanticRoots1242Tests(unittest.TestCase):
    def test_positive_content_link_is_not_reprobed_as_goal_fallback(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK", "GOAL_LINK"],
            "perception_control_subject": ["SECOND"],
        })
        result = make_parser(backend).parse(
            "Иван попросил Марию прочитать книгу."
        ).perception
        parent, child = result.assertions
        content = next(a for a in parent.actants if a.role == ActantRole.OBJECT)
        self.assertEqual(content.candidate_ref, child.local_id)

        # Once the parent↔child relation is resolved as content, the parser must
        # not ask a second relation question and reinterpret the same child as a
        # goal merely to fit another reading.
        self.assertEqual(
            [role for role, _prompt in backend.calls].count("perception_frame_relation"),
            1,
        )

    def test_generic_role_cue_maps_addressee_semantics_to_recipient(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_control_subject": ["SECOND"],
        })
        result = make_parser(backend).parse(
            "Иван попросил Марию прочитать книгу."
        ).perception
        parent, child = result.assertions
        roles = {actant.role: actant for actant in parent.actants}
        self.assertEqual(roles[ActantRole.RECIPIENT].normalized_hint, "Мария")
        self.assertEqual(roles[ActantRole.OBJECT].candidate_ref, child.local_id)

        recipient_prompt = next(
            prompt
            for role, prompt in backend.calls
            if role == "perception_role_cue" and "TARGET:\nМарию\n" in prompt
        )
        self.assertIn("RECEIVER_OR_ADDRESSEE:", recipient_prompt)
        self.assertIn("CHOICES:", recipient_prompt)
        self.assertNotIn("CHOICES:\nRECIPIENT", recipient_prompt)
        self.assertNotIn("perception_content_addressee", [role for role, _ in backend.calls])


if __name__ == "__main__":
    unittest.main()
