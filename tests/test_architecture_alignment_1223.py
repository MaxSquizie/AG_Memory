from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptivePerceptionParser, AdaptiveSettings,
    _EVENT_NONE_COMPLETION, _EVENT_RECIPIENT_COMPLETION,
)

from test_acceptance_regressions_1218 import AcceptanceMorphology

PROJECT = Path(__file__).resolve().parents[1]


class _Backend:
    def __init__(self, answers):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, override, system))
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected call: {role}\n{prompt}")
        return LLMResponse(str(values.pop(0)), {})


def _parser(backend):
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


class ArchitectureAlignment1223Tests(unittest.TestCase):


    def test_existing_description_role_needs_no_model_call(self):
        backend = _Backend({})
        result = _parser(backend).propose_template_candidate(
            "Иван остался дома.",
            PredicateCandidate("остался", "остаться"),
            (ActantRole.SUBJECT, ActantRole.LOCATION),
        )
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT, ActantRole.LOCATION))
        self.assertEqual(backend.calls, [])



if __name__ == "__main__":
    unittest.main()
