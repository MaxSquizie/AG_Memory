from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class SequenceBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        # Any LLM call is a contract violation for deterministic lexeme resolution.
        self.calls.append((role, prompt, dict(override or {})))
        raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")


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


def parser(backend, morphology) -> AdaptivePerceptionParser:
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
    """v0.12.39 contract: predicate lexeme resolution is deterministic and bounded.

    One-shot calibrated hidden-valency generation was removed from the production
    template path (see test_architecture_alignment_1235).  The still-live behavior
    here is verb-number homograph disambiguation in ``_predicate_lemma``: a plural
    subject selects the plural-compatible reading without any LLM call, and an
    equally compatible same-lexeme pair resolves to that shared lexeme.
    """

    def test_plural_subject_selects_compatible_verb_homograph_without_llm(self):
        backend = SequenceBackend()
        p = parser(backend, HomographAgreementMorphology())
        tokens = p._source_tokens("Иван и Мария пришли и ушли.")
        for surface, lemma in (("пришли", "прийти"), ("ушли", "уйти")):
            with self.subTest(surface=surface):
                index = next(t.index for t in tokens if t.text == surface)
                self.assertEqual(
                    p._predicate_lemma(tokens, index, index, act_type="ASSERTION"),
                    lemma,
                )
        self.assertEqual(backend.calls, [])

    def test_same_lexeme_homograph_pair_resolves_to_shared_lemma(self):
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
        p = parser(backend, SameLexemeMorphology())
        tokens = p._source_tokens("Иван и Мария ушли.")
        index = next(t.index for t in tokens if t.text == "ушли")
        self.assertEqual(
            p._predicate_lemma(tokens, index, index, act_type="ASSERTION"),
            "уйти",
        )
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
