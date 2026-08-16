from __future__ import annotations

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
    def test_positive_content_link_cannot_be_overwritten_by_goal_fallback(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK", "GOAL_LINK"],
            "perception_content_addressee": ["NOT_CONTENT_ADDRESSEE"],
        })
        with self.assertRaisesRegex(
            AdaptiveParseError,
            "unresolved OBJECT-content participant role conflict",
        ):
            make_parser(backend).parse("Иван попросил Марию прочитать книгу.")

        # CONTENT is already proven. The unresolved participant role is fail-closed;
        # the parser must not ask a second relation probe and reinterpret the same
        # child as PURPOSE merely to make the frame fit.
        self.assertEqual(
            [role for role, _prompt in backend.calls],
            [
                "perception_frame_relation",
                "perception_content_addressee",
            ],
        )

    def test_content_addressee_cue_maps_deterministically_to_recipient(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_content_addressee": ["CONTENT_ADDRESSEE"],
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
            if role == "perception_content_addressee"
        )
        self.assertIn("KNOWN CONTENT:\nпрочитать", recipient_prompt)
        self.assertIn("Does the PARENT predicate direct the KNOWN CONTENT to PARTICIPANT", recipient_prompt)
        self.assertIn("person being asked, told, advised, instructed", recipient_prompt)
        self.assertIn("CHOICES:\nCONTENT_ADDRESSEE\nNOT_CONTENT_ADDRESSEE", recipient_prompt)
        self.assertNotIn("CHOICES:\nRECIPIENT", recipient_prompt)
        self.assertNotIn("beneficiary", recipient_prompt)


if __name__ == "__main__":
    unittest.main()
