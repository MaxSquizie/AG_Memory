from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import (
    AdaptivePerceptionParser,
    AdaptiveSettings,
    _Span,
)
from ah.perception.contracts import EvidenceSpan, PredicateCandidate
from ah.perception.morphology import MorphInfo


PROJECT = Path(__file__).resolve().parents[1]


class ScriptedBackend:
    def __init__(self, answers):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, dict(override or {})))
        queue = self.answers.get(role)
        if not queue:
            raise AssertionError(f"unexpected probe {role}\n{prompt}")
        return LLMResponse(queue.pop(0), {})


class NoMorphology:
    name = "none"

    def analyze_all(self, word):
        return ()

    def analyze(self, word):
        return None


def make_parser(backend, morphology=None):
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology or NoMorphology(),
    )


def target_span(text="TARGET_X"):
    return _Span(1, 1, text, EvidenceSpan(text, 0, len(text)))


class GenericBinaryRoleRouter1253Tests(unittest.TestCase):
    def test_tool_is_resolved_by_generic_semantic_axes_without_lexical_rule(self):
        backend = ScriptedBackend({"perception_role_cue": ["INSTRUMENT"]})
        parser = make_parser(backend)
        role = parser._classify_role(
            "PRED TARGET_X", PredicateCandidate("PRED"), target_span(), set(), None,
            requested=False,
        )
        self.assertEqual(role, ActantRole.TOOL)
        self.assertTrue(all(len(call[2].get("choice_outputs", [])) == 0 for call in backend.calls))
        self.assertTrue(all("return_choice_scores" not in call[2] for call in backend.calls))
        self.assertTrue(all("decision_margin_threshold" not in call[2] for call in backend.calls))

    def test_time_is_resolved_by_generic_semantic_axes_without_time_word_list(self):
        backend = ScriptedBackend({"perception_role_cue": ["TIME_POINT"]})
        parser = make_parser(backend)
        role = parser._classify_role(
            "PRED TARGET_X", PredicateCandidate("PRED"), target_span(), set(), None,
            requested=False,
        )
        self.assertEqual(role, ActantRole.TIME)

    def test_preexisting_allowed_role_subset_can_only_shrink(self):
        backend = ScriptedBackend({"perception_role_cue": ["CONSTITUENT_MATERIAL"]})
        parser = make_parser(backend)
        role = parser._classify_role(
            "PRED TARGET_X", PredicateCandidate("PRED"), target_span(), set(), None,
            requested=False,
            allowed_roles={ActantRole.TOOL, ActantRole.MATERIAL},
        )
        self.assertEqual(role, ActantRole.MATERIAL)
        self.assertEqual([call[0] for call in backend.calls], ["perception_role_cue"])
        prompt = backend.calls[0][1]
        self.assertNotIn("SUBJECT", prompt)
        self.assertNotIn("RECIPIENT", prompt)
        self.assertNotIn("TIME:", prompt)

    def test_production_source_contains_no_broad200_lexical_repairs(self):
        source = (PROJECT / "src/ah/perception/adaptive_parser.py").read_text(encoding="utf-8")
        for forbidden in (
            "_TEMPORAL_ADVERBS",
            "_DURATION_UNIT_LEMMAS",
            "_duration_unit_lemma",
            "_span_is_numeric_duration",
            'word == "чем"',
            'prep in {"от", "из"}',
            "утром",
            "вечером",
            "вазу",
            "Анне",
            "ключом",
            "из дерева",
        ):
            self.assertNotIn(forbidden, source, forbidden)


class FormalSyntacticConstraints1253Tests(unittest.TestCase):
    def test_finite_number_disagreement_is_valid_negative_subject_evidence(self):
        class Morphology:
            name = "test"

            def analyze_all(self, word):
                return {
                    "отправили": (
                        MorphInfo("отправить", "VERB", number="plur", mood="indc", score=1.0),
                    ),
                    "письмо": (
                        MorphInfo("письмо", "NOUN", case="nomn", number="sing", gender="neut", score=0.5),
                        MorphInfo("письмо", "NOUN", case="accs", number="sing", gender="neut", score=0.5),
                    ),
                }.get(word.casefold(), ())

            def analyze(self, word):
                values = self.analyze_all(word)
                return values[0] if values else None

        parser = make_parser(ScriptedBackend({}), Morphology())
        tokens = parser._source_tokens("отправили письмо")
        predicate = parser._resolve_span("отправили письмо", tokens, 1, 1)
        self.assertFalse(parser._subject_agrees_with_predicate(tokens[1], predicate, tokens))

    def test_governing_preposition_is_preserved_as_evidence_not_mapped_by_table(self):
        class Morphology:
            name = "test"

            def analyze_all(self, word):
                return {
                    "от": (MorphInfo("от", "PREP", score=1.0),),
                    "кого": (MorphInfo("кто", "NPRO", case="gent", animacy="anim", score=1.0),),
                }.get(word.casefold(), ())

            def analyze(self, word):
                values = self.analyze_all(word)
                return values[0] if values else None

        backend = ScriptedBackend({"perception_role_cue": ["ORIGIN"]})
        parser = make_parser(backend, Morphology())
        text = "От кого пришло сообщение?"
        tokens = parser._source_tokens(text)
        role, span = parser._requested_query_role(text, tokens, PredicateCandidate("пришло", "прийти"))
        self.assertEqual(role, ActantRole.SOURCE)
        self.assertIsNotNone(span)
        self.assertEqual(span.text, "От кого")
        self.assertIn("От кого", backend.calls[0][1])
        # The semantic result came from the generic participant router, not from a
        # hardcoded preposition->SOURCE branch.
        self.assertEqual(
            [call[0] for call in backend.calls],
            ["perception_role_cue"],
        )


if __name__ == "__main__":
    unittest.main()
