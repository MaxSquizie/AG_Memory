from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import (
    AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings,
    _EVENT_NONE_COMPLETION, _EVENT_RECIPIENT_COMPLETION,
)
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class SequenceBackend:
    def __init__(self, answers=None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
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
            return LLMResponse(text, {"choice_margin": margin})
        return LLMResponse(str(item), {})


class HomographAgreementMorphology:
    name = "homograph-agreement"

    def analyze_all(self, word: str):
        values = {
            "иван": (
                MorphInfo("Иван", "NOUN", case="nomn", number="sing", score=1.0),
            ),
            "мария": (
                MorphInfo("Мария", "NOUN", case="nomn", number="sing", score=1.0),
            ),
            "и": (MorphInfo("и", "CONJ", score=1.0),),
            "пришли": (
                MorphInfo(
                    "прислать", "VERB", number="sing", mood="impr",
                    transitivity="tran", score=0.5,
                ),
                MorphInfo(
                    "прийти", "VERB", number="plur", mood="indc",
                    transitivity="intr", score=0.5,
                ),
            ),
            "ушли": (
                MorphInfo(
                    "уйти", "VERB", number="plur", mood="indc",
                    transitivity="intr", score=0.667,
                ),
                MorphInfo(
                    "услать", "VERB", number="sing", mood="impr",
                    transitivity="tran", score=0.333,
                ),
            ),
        }
        return values.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class TransitiveMorphology:
    name = "transitive"

    def analyze_all(self, word: str):
        values = {
            "подарил": (
                MorphInfo("подарить", "VERB", number="sing", mood="indc", transitivity="tran", score=1.0),
            ),
            "читает": (
                MorphInfo("читать", "VERB", number="sing", mood="indc", transitivity="tran", score=1.0),
            ),
        }
        return values.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def parser(backend, morphology):
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=8, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


class ArchitectureAlignment1232Tests(unittest.TestCase):
    def test_calibrated_semantic_low_margin_is_rejected(self):
        backend = SequenceBackend({
            "perception_template_hidden_valency": [
                ("AMBIGUOUS", 0.01),
            ],
        })
        with self.assertRaises(AdaptiveParseError) as raised:
            parser(backend, TransitiveMorphology()).propose_template_candidate(
                "Иван подарил книгу.",
                PredicateCandidate("подарил", "подарить"),
                (ActantRole.SUBJECT, ActantRole.OBJECT),
            )
        self.assertIn("invalid binary protocol answer", str(raised.exception))
        self.assertEqual(len(backend.calls), 1)
        role, _prompt, override = backend.calls[0]
        self.assertEqual(role, "perception_template_hidden_valency")
        self.assertNotIn("choice_calibration_prompt", override)
        self.assertNotIn("choice_outputs", override)

    def test_calibrated_none_adds_no_directional_role(self):
        backend = SequenceBackend({
            "perception_template_hidden_valency": [
                (_EVENT_NONE_COMPLETION, 0.8),
                ("NO_SOURCE_SLOT", 0.8),
            ],
        })
        result = parser(backend, TransitiveMorphology()).propose_template_candidate(
            "Иван читает книгу.",
            PredicateCandidate("читает", "читать"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT, ActantRole.OBJECT))
        self.assertEqual(len(backend.calls), 2)

    def test_calibrated_recipient_maps_to_one_recipient(self):
        backend = SequenceBackend({
            "perception_template_hidden_valency": [
                (_EVENT_RECIPIENT_COMPLETION, 0.8),
            ],
        })
        result = parser(backend, TransitiveMorphology()).propose_template_candidate(
            "Иван подарил книгу.",
            PredicateCandidate("подарил", "подарить"),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.assertEqual(
            result.candidate.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        self.assertEqual(len(backend.calls), 1)
        self.assertNotIn("choice_outputs", backend.calls[0][2])

    def test_template_reuses_already_resolved_predicate_lexeme_before_transitivity(self):
        backend = SequenceBackend()
        p = parser(backend, HomographAgreementMorphology())
        for surface, lemma in (("пришли", "прийти"), ("ушли", "уйти")):
            with self.subTest(surface=surface):
                result = p.propose_template_candidate(
                    "Иван и Мария пришли и ушли.",
                    PredicateCandidate(surface, lemma),
                    (ActantRole.SUBJECT,),
                )
                self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT,))
                self.assertTrue(any(
                    trace.stage == "template_predicate_lexeme_filter"
                    for trace in result.traces
                ))
        self.assertEqual(backend.calls, [])

    def test_subject_number_filter_removes_incompatible_homograph_when_lexeme_is_not_unique(self):
        class SameLexemeMorphology(HomographAgreementMorphology):
            def analyze_all(self, word: str):
                if word.casefold() == "ушли":
                    return (
                        MorphInfo(
                            "уйти", "VERB", number="plur", mood="indc",
                            transitivity="intr", score=0.5,
                        ),
                        MorphInfo(
                            "уйти", "VERB", number="sing", mood="impr",
                            transitivity="tran", score=0.5,
                        ),
                    )
                return super().analyze_all(word)

        backend = SequenceBackend()
        result = parser(backend, SameLexemeMorphology()).propose_template_candidate(
            "Иван и Мария ушли.",
            PredicateCandidate("ушли", "уйти"),
            (ActantRole.SUBJECT,),
        )
        self.assertEqual(result.candidate.roles, (ActantRole.SUBJECT,))
        self.assertEqual(backend.calls, [])
        self.assertTrue(any(
            trace.stage == "template_predicate_morphology_filter"
            and "NUMBER=plur" in (trace.normalized_answer or "")
            for trace in result.traces
        ))


if __name__ == "__main__":
    unittest.main()
