from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings

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


class SemanticRoots1243Tests(unittest.TestCase):
    def test_content_addressee_is_runtime_cue_not_canonical_role_label(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_content_addressee": ["CONTENT_ADDRESSEE"],
            "perception_control_subject": ["SECOND"],
        })
        result = make_parser(backend).parse("Иван попросил Марию прочитать книгу.").perception
        parent = result.assertions[0]
        self.assertIn(ActantRole.RECIPIENT, {a.role for a in parent.actants})

        prompt = next(prompt for role, prompt in backend.calls if role == "perception_content_addressee")
        self.assertIn("CHOICES:\nCONTENT_ADDRESSEE\nNOT_CONTENT_ADDRESSEE", prompt)
        self.assertNotIn("CHOICES:\nRECIPIENT", prompt)

    def test_old_canonical_recipient_label_is_rejected_by_cue_protocol(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_content_addressee": ["RECIPIENT"],
        })
        with self.assertRaisesRegex(
            AdaptiveParseError,
            "content_addressee expected exactly one of: CONTENT_ADDRESSEE, NOT_CONTENT_ADDRESSEE",
        ):
            make_parser(backend).parse("Иван попросил Марию прочитать книгу.")


if __name__ == "__main__":
    unittest.main()
