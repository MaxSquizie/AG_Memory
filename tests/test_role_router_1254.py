from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings, _Span
from ah.perception.contracts import EvidenceSpan, PredicateCandidate
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
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


class Morphology:
    name = "test"

    def __init__(self, data):
        self.data = data

    def analyze_all(self, word):
        return self.data.get(word.casefold(), ())

    def analyze(self, word):
        values = self.analyze_all(word)
        return values[0] if values else None


def make_parser(backend, morphology):
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


class NeutralRoleProtocol1254Tests(unittest.TestCase):
    def test_router_uses_one_exact_runtime_cue_without_choice_scoring(self):
        backend = ScriptedBackend({"perception_role_cue": ["INSTRUMENT"]})
        parser = make_parser(backend, Morphology({}))
        target = _Span(1, 1, "TARGET_X", EvidenceSpan("TARGET_X", 0, 8))
        role = parser._classify_role(
            "PRED TARGET_X", PredicateCandidate("PRED"), target, set(), None,
            requested=False,
        )
        self.assertEqual(role, ActantRole.TOOL)
        self.assertEqual(len(backend.calls), 1)
        call_role, prompt, override = backend.calls[0]
        self.assertEqual(call_role, "perception_role_cue")
        self.assertIn("INSTRUMENT:", prompt)
        self.assertIn("TIME_POINT:", prompt)
        self.assertIn("CHOICES:", prompt)
        self.assertNotIn("choice_outputs", override)
        self.assertNotIn("return_choice_scores", override)
        self.assertNotIn("decision_margin_threshold", override)

    def test_pre_narrowed_candidate_set_is_rendered_without_reintroducing_other_roles(self):
        backend = ScriptedBackend({"perception_role_cue": ["CONSTITUENT_MATERIAL"]})
        parser = make_parser(backend, Morphology({}))
        target = _Span(1, 1, "TARGET_X", EvidenceSpan("TARGET_X", 0, 8))
        role = parser._classify_role(
            "PRED TARGET_X", PredicateCandidate("PRED"), target, set(), None,
            requested=False, allowed_roles={ActantRole.TOOL, ActantRole.MATERIAL},
        )
        self.assertEqual(role, ActantRole.MATERIAL)
        prompt = backend.calls[0][1]
        self.assertIn("INSTRUMENT:", prompt)
        self.assertIn("CONSTITUENT_MATERIAL:", prompt)
        for forbidden in ("ACTOR_OR_EXPERIENCER:", "RECEIVER_OR_ADDRESSEE:", "TIME_POINT:", "INTENDED_GOAL:"):
            self.assertNotIn(forbidden, prompt)


class ContextualLexeme1254Tests(unittest.TestCase):
    def test_nominal_homonymy_is_resolved_by_symmetric_binary_hypotheses(self):
        morph = Morphology({
            "surface": (
                MorphInfo("alpha", "NOUN", case="datv", score=0.6),
                MorphInfo("beta", "NOUN", case="accs", score=0.4),
            )
        })
        backend = ScriptedBackend({"perception_lexeme_comparison": ["B", "A"]})
        parser = make_parser(backend, morph)
        text = "PRED surface"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        span = parser._resolve_span(text, tokens, 2, 2)
        parser._contextualize_nominal_span(text, PredicateCandidate("PRED"), span, tokens)
        remaining = parser._material_morph_analyses(tokens[1])
        self.assertEqual({item.normal_form for item in remaining if item.pos == "NOUN"}, {"beta"})
        self.assertEqual([call[0] for call in backend.calls], ["perception_lexeme_comparison", "perception_lexeme_comparison"])
        self.assertIn("A LEMMA:\nalpha", backend.calls[0][1])
        self.assertIn("A LEMMA:\nbeta", backend.calls[1][1])

    def test_predicate_homonymy_uses_same_symmetric_lexical_boundary(self):
        morph = Morphology({
            "surface": (
                MorphInfo("alpha", "VERB", number="sing", mood="indc", score=0.5),
                MorphInfo("beta", "VERB", number="sing", mood="indc", score=0.5),
            )
        })
        backend = ScriptedBackend({"perception_lexeme_comparison": ["B", "A"]})
        parser = make_parser(backend, morph)
        text = "surface"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        lemma = parser._predicate_lemma(tokens, 1, 1, act_type="ASSERTION")
        self.assertEqual(lemma, "beta")
        self.assertEqual([call[0] for call in backend.calls], ["perception_lexeme_comparison", "perception_lexeme_comparison"])
        self.assertIn("TARGET:\nsurface", backend.calls[0][1])

    def test_predicate_morphology_score_does_not_replace_contextual_lexeme_choice(self):
        morph = Morphology({
            "surface": (
                MorphInfo("alpha", "VERB", number="sing", mood="indc", score=0.7),
                MorphInfo("beta", "VERB", number="sing", mood="indc", score=0.3),
            )
        })
        backend = ScriptedBackend({"perception_lexeme_comparison": ["B", "A"]})
        parser = make_parser(backend, morph)
        text = "surface"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        lemma = parser._predicate_lemma(tokens, 1, 1, act_type="ASSERTION")
        self.assertEqual(lemma, "beta")
        self.assertEqual([call[0] for call in backend.calls], ["perception_lexeme_comparison", "perception_lexeme_comparison"])

    def test_nonbinary_nominal_lexical_ambiguity_fails_closed(self):
        morph = Morphology({
            "surface": tuple(
                MorphInfo(value, "NOUN", case="nomn", score=1 / 3)
                for value in ("alpha", "beta", "gamma")
            )
        })
        parser = make_parser(ScriptedBackend({}), morph)
        text = "PRED surface"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        span = parser._resolve_span(text, tokens, 2, 2)
        with self.assertRaisesRegex(Exception, "nominal lexical ambiguity is not binary"):
            parser._contextualize_nominal_span(text, PredicateCandidate("PRED"), span, tokens)



if __name__ == "__main__":
    unittest.main()
