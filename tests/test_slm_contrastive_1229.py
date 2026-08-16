from __future__ import annotations

from collections import deque
from pathlib import Path
from threading import Lock
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.llm.process_backend import LocalLLMProcessBackend
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptivePerceptionParser, AdaptiveSettings,
    _EVENT_RECIPIENT_COMPLETION,
)

from test_acceptance_regressions_1218 import AcceptanceMorphology, RequestMorphology

PROJECT = Path(__file__).resolve().parents[1]


class MarginBackend:
    def __init__(self, answers: dict[str, list[tuple[str, float] | str]]):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov))
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")
        item = values.pop(0)
        if isinstance(item, tuple):
            text, margin = item
            choices = list(ov.get("choice_outputs") or [])
            scores = {choice: -2.0 for choice in choices}
            if text in scores:
                scores[text] = -0.5
            return LLMResponse(text, {"choice_margin": margin, "choice_scores": scores})
        return LLMResponse(item, {})


def parser(backend):
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=8, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=AcceptanceMorphology(),
    )


class SLMContrastive1229Tests(unittest.TestCase):

    def test_request_participant_content_and_controller_are_independent_binary_cues(self):
        backend = MarginBackend({
            "perception_content_addressee": ["CONTENT_ADDRESSEE"],
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_control_subject": ["SECOND"],
        })
        parsed = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=8, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=RequestMorphology(),
        ).parse("Иван попросил Марию прочитать книгу.")
        parent, child = parsed.perception.assertions
        recipient = next(a for a in parent.actants if a.role == ActantRole.RECIPIENT)
        content = next(a for a in parent.actants if a.role == ActantRole.OBJECT)
        child_subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(content.candidate_ref, child.local_id)
        self.assertEqual(child_subject.entity_ref, recipient.entity_ref)
        for role, _prompt, override in backend.calls:
            if role in {"perception_frame_relation", "perception_content_addressee", "perception_control_subject"}:
                self.assertNotIn("choice_outputs", override)
                self.assertNotIn("decision_margin_threshold", override)

    def test_request_diagnostic_keeps_fixed_choice_evidence(self):
        backend = object.__new__(LocalLLMProcessBackend)
        backend._status_lock = Lock()
        backend._request_count = 7
        backend._request_diagnostics = deque(maxlen=50)
        backend._recent_log = deque(maxlen=200)
        backend._record_request(
            req_id="r1",
            role="perception_template_hidden_role",
            prompt="p",
            system="s",
            response_text="TAKES_RECEIVER",
            override={
                "choice_outputs": ["TAKES_RECEIVER", "NO_RECEIVER_SLOT"],
                "decision_margin_threshold": 0.10,
            },
            response_meta={
                "choice": "TAKES_RECEIVER",
                "choice_scores": {
                    "TAKES_RECEIVER": -0.4,
                    "NO_RECEIVER_SLOT": -1.1,
                },
                "choice_margin": 0.7,
            },
        )
        record = backend.request_diagnostics()[0]
        self.assertEqual(record.choice_outputs, ("TAKES_RECEIVER", "NO_RECEIVER_SLOT"))
        self.assertEqual(record.choice_scores["TAKES_RECEIVER"], -0.4)
        self.assertEqual(record.choice_winner, "TAKES_RECEIVER")
        self.assertEqual(record.choice_margin, 0.7)
        self.assertEqual(record.decision_margin_threshold, 0.10)
        self.assertTrue(record.decision_accepted)

    def test_low_margin_is_logged_as_rejected_evidence(self):
        backend = object.__new__(LocalLLMProcessBackend)
        backend._status_lock = Lock()
        backend._request_count = 8
        backend._request_diagnostics = deque(maxlen=50)
        backend._recent_log = deque(maxlen=200)
        backend._record_request(
            req_id="r2", role="perception_control_subject", prompt="p", system="s",
            response_text="SECOND",
            override={
                "choice_outputs": ["FIRST", "SECOND"],
                "decision_margin_threshold": 0.10,
            },
            response_meta={"choice": "SECOND", "choice_scores": {"FIRST": -1.0, "SECOND": -0.96}, "choice_margin": 0.04},
        )
        record = backend.request_diagnostics()[0]
        self.assertFalse(record.decision_accepted)
        self.assertEqual(record.choice_margin, 0.04)


if __name__ == "__main__":
    unittest.main()
