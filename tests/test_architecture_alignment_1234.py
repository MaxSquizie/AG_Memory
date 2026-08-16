from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import ActantCandidate, AssertionCandidate, EvidenceSpan, PerceptionResult, PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptivePerceptionParser,
    AdaptiveSettings,
    _EVENT_NONE_COMPLETION,
    _EVENT_RECIPIENT_COMPLETION,
    _EVENT_SOURCE_COMPLETION,
)

from test_acceptance_regressions_1218 import AcceptanceMorphology

PROJECT = Path(__file__).resolve().parents[1]


class SemanticBackend:
    def __init__(self, winner: str, margin: float = 0.8):
        self.winner = winner
        self.margin = margin
        self.calls: list[tuple[str, str, dict, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        ov = dict(override or {})
        self.calls.append((role, prompt, ov, system))
        if role != "perception_template_hidden_valency":
            raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")
        winner = self.winner
        if winner == "NO_RECIPIENT_SLOT" and "HAS_SOURCE_SLOT" in prompt:
            winner = "NO_SOURCE_SLOT"
        elif winner == "HAS_SOURCE_SLOT" and "HAS_RECIPIENT_SLOT" in prompt:
            winner = "NO_RECIPIENT_SLOT"
        return LLMResponse(winner, {"choice_margin": self.margin})


def parser(backend: SemanticBackend) -> AdaptivePerceptionParser:
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


class ArchitectureAlignment1234Tests(unittest.TestCase):
    def test_template_preflight_carries_only_textual_role_bindings(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2, 0.18))
        text = "Иван подарил книгу."
        result = PerceptionResult(
            text,
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate("подарил", "подарить"),
                    (
                        ActantCandidate(ActantRole.SUBJECT, mention="Иван", entity_ref=None),
                        ActantCandidate(ActantRole.OBJECT, mention="книгу", normalized_hint="книга"),
                    ),
                    evidence=EvidenceSpan(text, 0, len(text)),
                ),
            ),
        )
        request = service.template_requests(result)[0]
        self.assertEqual(request.source_context, text)
        self.assertEqual(
            request.role_bindings,
            ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        )
        flattened = repr(request.role_bindings)
        self.assertNotIn("M_", flattened)
        self.assertNotIn("N_", flattened)




    def test_generation_protocol_is_binary_and_slot_specific(self):
        instruction = (PROJECT / "prompts/perception" / "template_hidden_valency.txt").read_text(encoding="utf-8")
        self.assertIn("Choose exactly one label from CHOICES", instruction)
        self.assertIn("Known roles", instruction)
        self.assertNotIn("RECIPIENT,SOURCE", instruction)
        self.assertNotIn("AMBIGUOUS", instruction)



if __name__ == "__main__":
    unittest.main()
