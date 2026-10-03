from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.diagnostics.hidden_valency_diagnostic import _choices_for, _semantic_label

from test_acceptance_regressions_1218 import AcceptanceMorphology


class NoCallBackend:
    """Any LLM call is a contract violation for the production template path."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls += 1
        raise AssertionError(f"production template path must not call the LLM (role={role})")


PROJECT = Path(__file__).resolve().parents[1]


def parser(backend: NoCallBackend) -> AdaptivePerceptionParser:
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
    """v0.12.39 contract: production template creation never predicts hidden roles.

    ``propose_template_candidate`` returns only the explicit semantic roles already
    extracted by Perception and makes zero LLM calls; one-shot hidden-valency
    generation was removed from the canonical schema path and lives only in the
    standalone capability diagnostic (order-swap, AH-unchanged).
    """

    def test_propose_template_candidate_makes_no_llm_call(self):
        backend = NoCallBackend()
        result = parser(backend).propose_template_candidate(
            "Иван подарил книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
            ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        )
        self.assertEqual(backend.calls, 0)
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))

    def test_only_explicit_roles_are_returned_in_canonical_order(self):
        backend = NoCallBackend()
        result = parser(backend).propose_template_candidate(
            "Иван подарил Марии книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.OBJECT, ActantRole.RECIPIENT, ActantRole.SUBJECT),
        )
        self.assertEqual(backend.calls, 0)
        # Roles are re-emitted in the canonical ActantRole declaration order.
        self.assertEqual(
            result.candidate.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )

    def test_no_explicit_roles_yields_empty_candidate(self):
        backend = NoCallBackend()
        result = parser(backend).propose_template_candidate(
            "Иван читает.",
            PredicateCandidate("читает", "читать"),
            (ActantRole.SUBJECT,),
        )
        self.assertEqual(backend.calls, 0)
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT,))

    def test_diagnostic_choices_are_role_specific_and_closed(self):
        self.assertEqual(
            _choices_for(ActantRole.RECIPIENT),
            ("HAS_RECIPIENT_SLOT", "NO_RECIPIENT_SLOT"),
        )
        self.assertEqual(
            _choices_for(ActantRole.SOURCE),
            ("HAS_SOURCE_SLOT", "NO_SOURCE_SLOT"),
        )
        with self.assertRaises(ValueError):
            _choices_for(ActantRole.OBJECT)

    def test_diagnostic_semantic_label_is_exact_or_recovers_only_orphan_think_close(self):
        choices = ("HAS_RECIPIENT_SLOT", "NO_RECIPIENT_SLOT")
        self.assertEqual(_semantic_label("HAS_RECIPIENT_SLOT", choices), ("HAS_RECIPIENT_SLOT", "EXACT"))
        # A trailing orphan Qwen think-close wrapper is the only tolerated recovery.
        self.assertEqual(
            _semantic_label("NO_RECIPIENT_SLOT\n</think>", choices),
            ("NO_RECIPIENT_SLOT", "RECOVERED_ORPHAN_THINK_CLOSE"),
        )

    def test_diagnostic_semantic_label_rejects_explanations_and_unknowns(self):
        choices = ("HAS_SOURCE_SLOT", "NO_SOURCE_SLOT")
        self.assertEqual(_semantic_label("because it receives it", choices), (None, "MALFORMED"))
        self.assertEqual(_semantic_label("RECEIVER", choices), (None, "MALFORMED"))


if __name__ == "__main__":
    unittest.main()
