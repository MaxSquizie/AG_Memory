from __future__ import annotations

from legacy_semantic_fixture import legacy_semantic_answer

from collections import deque
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.llm.process_backend import LocalLLMProcessBackend
from ah.llm.worker import _score_calibrated_choice_details
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptiveParseError,
    AdaptivePerceptionParser,
    AdaptiveSettings,
    _EVENT_NONE_COMPLETION,
    _EVENT_RECIPIENT_COMPLETION,
    _EVENT_SOURCE_COMPLETION,
)

from test_acceptance_regressions_1218 import AcceptanceMorphology, RequestMorphology

PROJECT = Path(__file__).resolve().parents[1]


class SemanticBackend:
    def __init__(self, semantic: str, margin: float = 0.8):
        self.semantic = semantic
        self.margin = margin
        self.calls: list[tuple[str, str, dict, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov, system))
        if role == "perception_template_hidden_valency":
            if self.semantic == "RECIPIENT":
                winner = "HAS_RECIPIENT_SLOT"
            elif self.semantic == "SOURCE":
                winner = (
                    "NO_RECIPIENT_SLOT"
                    if "HAS_RECIPIENT_SLOT" in prompt
                    else "HAS_SOURCE_SLOT"
                )
            elif self.semantic == "NONE":
                winner = (
                    "NO_RECIPIENT_SLOT"
                    if "HAS_RECIPIENT_SLOT" in prompt
                    else "NO_SOURCE_SLOT"
                )
            else:
                winner = "AMBIGUOUS"
            return LLMResponse(winner, {"choice_margin": self.margin})
        if role == "perception_frame_relation":
            return LLMResponse("GOAL_LINK", {"choice": "GOAL_LINK", "choice_margin": 0.8})
        fallback = legacy_semantic_answer(role, prompt)
        if fallback is not None:
            return LLMResponse(str(fallback), {})
        raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")


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


class ArchitectureAlignment1233Tests(unittest.TestCase):
    def test_worker_calibration_can_reverse_a_raw_continuation_prior(self):
        try:
            import torch
        except ModuleNotFoundError:
            self.skipTest("optional torch test dependency is not installed")

        class Tokenizer:
            def __call__(self, text, *, return_tensors="pt", add_special_tokens=False):
                token = {"A": 1, "B": 2}[text]
                return {"input_ids": torch.tensor([[token]], dtype=torch.long)}

        class Model:
            device = "cpu"

            def __call__(self, *, input_ids, attention_mask, use_cache=False):
                logits = torch.zeros((1, input_ids.shape[-1], 8), dtype=torch.float32)
                # Actual context (first token 5): A has a small raw advantage.
                # Neutral context (first token 7): A has a huge prior advantage.
                # Prior subtraction must therefore prefer B.
                if int(input_ids[0, 0]) == 5:
                    logits[:, 1, 1] = 6.0
                    logits[:, 1, 2] = 5.0
                else:
                    logits[:, 1, 1] = 10.0
                    logits[:, 1, 2] = 0.0
                return SimpleNamespace(logits=logits)

        runtime = {
            "torch": torch,
            "tokenizer": Tokenizer(),
            "model": Model(),
            "input_device": "cpu",
        }
        actual = {
            "input_ids": torch.tensor([[5, 6]], dtype=torch.long),
            "attention_mask": torch.tensor([[1, 1]], dtype=torch.long),
        }
        neutral = {
            "input_ids": torch.tensor([[7, 8]], dtype=torch.long),
            "attention_mask": torch.tensor([[1, 1]], dtype=torch.long),
        }
        details = _score_calibrated_choice_details(runtime, actual, neutral, ["A", "B"])
        self.assertGreater(details["choice_scores"]["A"], details["choice_scores"]["B"])
        self.assertEqual(details["choice"], "B")
        self.assertGreater(
            details["calibrated_choice_scores"]["B"],
            details["calibrated_choice_scores"]["A"],
        )
        self.assertEqual(
            details["choice_scoring_mode"],
            "content_free_calibrated_semantic_completion",
        )


    def test_calibrated_none_keeps_observed_schema(self):
        backend = SemanticBackend("NONE")
        result = parser(backend).propose_template_candidate(
            "Иван читает книгу.",
            PredicateCandidate("читает", "читать"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))


    def test_request_control_no_longer_relies_on_retired_purpose_object_shortcut(self):
        class RequestBackend(SemanticBackend):
            def generate(self, prompt, *, system="", override=None, role="generic"):
                if role == "perception_content_addressee":
                    self.calls.append((role, prompt, dict(override or {}), system))
                    return LLMResponse("CONTENT_ADDRESSEE", {})
                if role == "perception_frame_relation":
                    self.calls.append((role, prompt, dict(override or {}), system))
                    return LLMResponse("CONTENT_LINK", {})
                if role == "perception_control_subject":
                    self.calls.append((role, prompt, dict(override or {}), system))
                    return LLMResponse("SECOND", {})
                return super().generate(prompt, system=system, override=override, role=role)
        backend = RequestBackend("NONE")
        p = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0, morphology_backend="none",
            ),
            morphology=RequestMorphology(),
        )
        parsed = p.parse("Иван попросил Марию прочитать книгу.")
        parent, child = parsed.perception.assertions
        recipient = next(a for a in parent.actants if a.role == ActantRole.RECIPIENT)
        content = next(a for a in parent.actants if a.role == ActantRole.OBJECT)
        child_subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(content.candidate_ref, child.local_id)
        self.assertEqual(child_subject.entity_ref, recipient.entity_ref)
        self.assertFalse(any(trace.stage == "control_subject_grammar" for trace in parsed.traces))

    def test_request_diagnostic_persists_raw_baseline_and_calibrated_scores(self):
        backend = object.__new__(LocalLLMProcessBackend)
        backend._status_lock = Lock()
        backend._request_count = 11
        backend._request_diagnostics = deque(maxlen=50)
        backend._recent_log = deque(maxlen=200)
        backend._record_request(
            req_id="r-cal",
            role="perception_template_hidden_valency",
            prompt="p",
            system="s",
            response_text=_EVENT_RECIPIENT_COMPLETION,
            override={
                "choice_outputs": [_EVENT_RECIPIENT_COMPLETION, _EVENT_NONE_COMPLETION],
                "decision_margin_threshold": 0.10,
            },
            response_meta={
                "choice": _EVENT_RECIPIENT_COMPLETION,
                "choice_scores": {
                    _EVENT_RECIPIENT_COMPLETION: -0.40,
                    _EVENT_NONE_COMPLETION: -0.30,
                },
                "calibration_choice_scores": {
                    _EVENT_RECIPIENT_COMPLETION: -0.80,
                    _EVENT_NONE_COMPLETION: -0.35,
                },
                "calibrated_choice_scores": {
                    _EVENT_RECIPIENT_COMPLETION: 0.40,
                    _EVENT_NONE_COMPLETION: 0.05,
                },
                "raw_choice_margin": 0.10,
                "choice_margin": 0.35,
                "choice_scoring_mode": "content_free_calibrated_semantic_completion",
            },
        )
        record = backend.request_diagnostics()[0]
        self.assertEqual(record.raw_choice_margin, 0.10)
        self.assertEqual(record.choice_margin, 0.35)
        self.assertEqual(record.calibration_choice_scores[_EVENT_RECIPIENT_COMPLETION], -0.80)
        self.assertEqual(record.calibrated_choice_scores[_EVENT_RECIPIENT_COMPLETION], 0.40)
        self.assertEqual(
            record.choice_scoring_mode,
            "content_free_calibrated_semantic_completion",
        )
        self.assertTrue(record.decision_accepted)


if __name__ == "__main__":
    unittest.main()
