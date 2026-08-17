from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.contracts import PredicateCandidate
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


class RelationContract1255Tests(unittest.TestCase):
    def test_tool_material_contrast_is_relational_and_mutually_exclusive(self):
        backend = ScriptedBackend({"perception_role_cue": ["INSTRUMENT"]})
        parser = make_parser(backend, Morphology({}))
        from ah.perception.adaptive_parser import _Span
        from ah.perception.contracts import EvidenceSpan

        span = _Span(1, 1, "TARGET_X", EvidenceSpan("TARGET_X", 0, 8))
        role = parser._classify_role(
            "PRED TARGET_X",
            PredicateCandidate("PRED"),
            span,
            set(),
            None,
            requested=False,
            allowed_roles={ActantRole.TOOL, ActantRole.MATERIAL},
        )
        self.assertEqual(role, ActantRole.TOOL)
        prompt = backend.calls[0][1]
        self.assertIn("whole sentence", prompt)
        self.assertIn("instrument or tool used", prompt)
        self.assertIn("rather than becoming material", prompt)
        self.assertIn("substance or material constituent", prompt)
        self.assertIn("not a separate implement", prompt)
        self.assertNotIn("ключ", prompt)
        self.assertNotIn("утром", prompt)

    def test_pure_adverb_only_excludes_nominal_tool_material_participant_roles(self):
        morph = Morphology({
            "pred": (MorphInfo("pred", "VERB", number="sing", mood="indc", score=1.0),),
            "target_x": (MorphInfo("target_x", "ADVB", score=1.0),),
        })
        parser = make_parser(ScriptedBackend({}), morph)
        text = "pred TARGET_X"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        predicate_span = parser._resolve_span(text, tokens, 1, 1)
        target_span = parser._resolve_span(text, tokens, 2, 2)
        allowed = set(parser._deterministic_role_candidates(
            tokens, predicate_span, PredicateCandidate("pred"), target_span
        ))
        self.assertIn(ActantRole.TIME, allowed)
        self.assertIn(ActantRole.LOCATION, allowed)
        self.assertIn(ActantRole.HOW_TO, allowed)
        for forbidden in (
            ActantRole.SUBJECT,
            ActantRole.OBJECT,
            ActantRole.RECIPIENT,
            ActantRole.SOURCE,
            ActantRole.TOOL,
            ActantRole.MATERIAL,
        ):
            self.assertNotIn(forbidden, allowed)


class LexicalMonotonicity1255Tests(unittest.TestCase):
    def test_contextually_selected_nominal_lemma_is_used_by_semantic_actant_text(self):
        morph = Morphology({
            "surface": (
                MorphInfo("alpha", "NOUN", case="datv", score=0.5),
                MorphInfo("beta", "NOUN", case="accs", score=0.5),
            )
        })
        backend = ScriptedBackend({"perception_lexeme_comparison": ["B", "A"]})
        parser = make_parser(backend, morph)
        text = "surface"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        span = parser._resolve_span(text, tokens, 1, 1)
        parser._contextualize_nominal_span(text, PredicateCandidate("PRED"), span, tokens)
        mention, normalized = parser._semantic_actant_text(span)
        self.assertEqual(mention, "surface")
        self.assertEqual(normalized, "beta")

    def test_nominal_lexeme_probe_shows_surface_morphology_for_each_candidate(self):
        morph = Morphology({
            "surface": (
                MorphInfo(
                    "alpha", "NOUN", case="datv", number="sing", gender="femn",
                    grammemes=frozenset({"Name"}), score=0.5,
                ),
                MorphInfo(
                    "beta", "NOUN", case="nomn", number="sing", gender="femn",
                    grammemes=frozenset({"Name", "Fixd"}), score=0.5,
                ),
            )
        })
        backend = ScriptedBackend({"perception_lexeme_comparison": ["A", "B"]})
        parser = make_parser(backend, morph)
        text = "surface"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        span = parser._resolve_span(text, tokens, 1, 1)
        parser._contextualize_nominal_span(text, PredicateCandidate("PRED"), span, tokens)
        first_prompt, second_prompt = backend.calls[0][1], backend.calls[1][1]
        self.assertIn("A LEMMA:\nalpha", first_prompt)
        self.assertIn("CASE=datv", first_prompt)
        self.assertIn("personal-name", first_prompt)
        self.assertIn("A LEMMA:\nbeta", second_prompt)
        self.assertIn("indeclinable", second_prompt)

    def test_predicate_lexeme_probe_shows_participle_vs_adjective_morphology(self):
        morph = Morphology({
            "surface": (
                MorphInfo(
                    "verb_lemma", "PRTS", number="sing", gender="femn",
                    grammemes=frozenset({"pssv", "past"}), score=0.5,
                ),
                MorphInfo(
                    "adjective_lemma", "ADJS", number="sing", gender="femn",
                    grammemes=frozenset({"Qual"}), score=0.5,
                ),
            )
        })
        backend = ScriptedBackend({"perception_lexeme_comparison": ["A", "B"]})
        parser = make_parser(backend, morph)
        text = "surface"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        parser._predicate_lemma(tokens, 1, 1, act_type="ASSERTION")
        prompts = [call[1] for call in backend.calls]
        self.assertTrue(any("passive" in prompt for prompt in prompts))
        self.assertTrue(any("qualitative" in prompt for prompt in prompts))


if __name__ == "__main__":
    unittest.main()
