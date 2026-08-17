from __future__ import annotations

from legacy_semantic_fixture import legacy_semantic_answer

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


class SemanticRoots1243Tests(unittest.TestCase):
    def test_addressee_is_runtime_cue_not_canonical_role_label(self):
        backend = RecordingBackend({
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_control_subject": ["SECOND"],
        })
        result = make_parser(backend).parse("Иван попросил Марию прочитать книгу.").perception
        parent = result.assertions[0]
        self.assertIn(ActantRole.RECIPIENT, {a.role for a in parent.actants})

        prompt = next(
            prompt
            for role, prompt in backend.calls
            if role == "perception_role_cue" and "TARGET:\nМарию\n" in prompt
        )
        self.assertIn("RECEIVER_OR_ADDRESSEE:", prompt)
        self.assertNotIn("CHOICES:\nRECIPIENT", prompt)
        self.assertFalse(any(role == "perception_content_addressee" for role, _ in backend.calls))

    def test_canonical_recipient_label_is_rejected_by_runtime_cue_protocol(self):
        backend = RecordingBackend({
            # First role cue is Иван; the second is Марию.  Returning the canonical
            # AH label for the second decision must be rejected: the LLM boundary
            # accepts only UID-free runtime semantic cues.
            "perception_role_cue": ["ACTOR_OR_EXPERIENCER", "RECIPIENT"],
        })
        with self.assertRaisesRegex(
            AdaptiveParseError,
            "role_cue expected exactly one of:",
        ):
            make_parser(backend).parse("Иван попросил Марию прочитать книгу.")


if __name__ == "__main__":
    unittest.main()
