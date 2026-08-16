from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptiveParseError,
    AdaptivePerceptionParser,
    AdaptiveSettings,
    _TEMPLATE_HIDDEN_VALENCY_LABELS,
)

from test_acceptance_regressions_1218 import AcceptanceMorphology

PROJECT = Path(__file__).resolve().parents[1]


class GenerationBackend:
    def __init__(self, answer: str):
        self.answer = answer
        self.calls: list[tuple[str, str, dict, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov, system))
        if role != "perception_template_hidden_valency":
            raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")
        return LLMResponse(self.answer, {})


def parser(backend: GenerationBackend) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=12, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=AcceptanceMorphology(),
    )


class ArchitectureAlignment1235Tests(unittest.TestCase):
    def test_hidden_valency_uses_one_normal_generation_without_choice_scoring(self):
        backend = GenerationBackend("RECIPIENT")
        result = parser(backend).propose_template_candidate(
            "Иван подарил книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
            ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        )
        self.assertEqual(
            result.candidate.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(len(backend.calls), 1)
        role, prompt, override, system = backend.calls[0]
        self.assertEqual(role, "perception_template_hidden_valency")
        self.assertNotIn("choice_outputs", override)
        self.assertNotIn("return_choice_scores", override)
        self.assertNotIn("choice_calibration_prompt", override)
        self.assertEqual(override["temperature"], 0.0)
        self.assertLessEqual(override["max_new_tokens"], 8)
        self.assertIn("SOURCE TEXT:\nИван подарил книгу.", prompt)
        self.assertIn("SUBJECT: Иван", prompt)
        self.assertIn("OBJECT: книга", prompt)
        for label in _TEMPLATE_HIDDEN_VALENCY_LABELS:
            self.assertIn(label, system)

    def test_none_keeps_only_known_roles(self):
        backend = GenerationBackend("NONE")
        result = parser(backend).propose_template_candidate(
            "Иван читает книгу.",
            PredicateCandidate("читает", "читать"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))

    def test_source_and_recipient_source_are_mapped_deterministically(self):
        cases = (
            ("SOURCE", (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.SOURCE)),
            (
                "RECIPIENT,SOURCE",
                (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT, ActantRole.SOURCE),
            ),
        )
        for answer, expected in cases:
            with self.subTest(answer=answer):
                backend = GenerationBackend(answer)
                result = parser(backend).propose_template_candidate(
                    "Иван обработал объект.",
                    PredicateCandidate("обработал", "обработать"),
                    (ActantRole.SUBJECT, ActantRole.OBJECT),
                )
                self.assertEqual(result.candidate.roles, expected)

    def test_ambiguous_answer_fails_closed_before_template_creation(self):
        backend = GenerationBackend("AMBIGUOUS")
        with self.assertRaises(AdaptiveParseError) as raised:
            parser(backend).propose_template_candidate(
                "Иван подарил книгу.",
                PredicateCandidate("подарил", "подарить"),
                (ActantRole.SUBJECT, ActantRole.OBJECT),
            )
        self.assertIn("ambiguous hidden directional participant", str(raised.exception))
        self.assertTrue(any(
            trace.stage == "template_hidden_valency"
            and trace.normalized_answer == "AMBIGUOUS"
            for trace in raised.exception.traces
        ))

    def test_explanatory_or_unknown_output_is_protocol_error(self):
        for answer in ("RECIPIENT\nbecause someone receives it", "RECEIVER"):
            with self.subTest(answer=answer):
                backend = GenerationBackend(answer)
                with self.assertRaises(AdaptiveParseError) as raised:
                    parser(backend).propose_template_candidate(
                        "Иван подарил книгу.",
                        PredicateCandidate("подарил", "подарить"),
                        (ActantRole.SUBJECT, ActantRole.OBJECT),
                    )
                self.assertIn("invalid protocol answer", str(raised.exception))

    def test_observed_directional_role_disables_hidden_valency_generation(self):
        backend = GenerationBackend("SOURCE")
        result = parser(backend).propose_template_candidate(
            "Иван подарил Марии книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(
            result.candidate.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
