from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings, _Span
from ah.perception.contracts import ActantCandidate, AssertionCandidate, EvidenceSpan, PredicateCandidate
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

    def __init__(self, data=None):
        self.data = data or {}

    def analyze_all(self, word):
        return self.data.get(word.casefold(), ())

    def analyze(self, word):
        values = self.analyze_all(word)
        return values[0] if values else None


def make_parser(backend, morphology=None):
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology or Morphology(),
    )


class RuntimeRoleCue1257Tests(unittest.TestCase):
    def test_one_semantic_cue_maps_to_canonical_role_without_choice_scoring(self):
        backend = ScriptedBackend({"perception_role_cue": ["INSTRUMENT"]})
        parser = make_parser(backend)
        span = _Span(1, 1, "TARGET_X", EvidenceSpan("TARGET_X", 0, 8))
        role = parser._classify_role(
            "PRED TARGET_X", PredicateCandidate("PRED"), span, set(), None,
            requested=False,
        )
        self.assertEqual(role, ActantRole.TOOL)
        self.assertEqual(len(backend.calls), 1)
        call_role, prompt, override = backend.calls[0]
        self.assertEqual(call_role, "perception_role_cue")
        self.assertIn("INSTRUMENT:", prompt)
        self.assertIn("CONSTITUENT_MATERIAL:", prompt)
        self.assertNotIn("choice_outputs", override)
        self.assertNotIn("return_choice_scores", override)
        self.assertNotIn("decision_margin_threshold", override)

    def test_pre_narrowed_set_is_the_complete_model_search_space(self):
        backend = ScriptedBackend({"perception_role_cue": ["ORIGIN"]})
        parser = make_parser(backend)
        span = _Span(1, 1, "TARGET_X", EvidenceSpan("TARGET_X", 0, 8))
        role = parser._classify_role(
            "PRED TARGET_X", PredicateCandidate("PRED"), span, set(), None,
            requested=False,
            allowed_roles={ActantRole.SOURCE, ActantRole.MATERIAL},
        )
        self.assertEqual(role, ActantRole.SOURCE)
        prompt = backend.calls[0][1]
        self.assertIn("ORIGIN:", prompt)
        self.assertIn("CONSTITUENT_MATERIAL:", prompt)
        self.assertNotIn("INSTRUMENT:", prompt)
        self.assertNotIn("TIME_POINT:", prompt)
        self.assertNotIn("ACTOR_OR_EXPERIENCER:", prompt)

    def test_malformed_role_cue_fails_closed(self):
        backend = ScriptedBackend({"perception_role_cue": ["SOMETHING_ELSE"]})
        parser = make_parser(backend)
        span = _Span(1, 1, "TARGET_X", EvidenceSpan("TARGET_X", 0, 8))
        with self.assertRaisesRegex(Exception, "role_cue expected exactly one of"):
            parser._classify_role(
                "PRED TARGET_X", PredicateCandidate("PRED"), span, set(), None,
                requested=False,
                allowed_roles={ActantRole.TOOL, ActantRole.MATERIAL},
            )


class PronounPersonCompatibility1257Tests(unittest.TestCase):
    def test_third_person_anaphor_does_not_create_speaker_coreference_alternative(self):
        morph = Morphology({
            "мне": (MorphInfo("я", "NPRO", case="datv", number="sing", grammemes=frozenset({"1per"}), score=1.0),),
            "дали": (MorphInfo("дать", "VERB", number="plur", mood="indc", score=1.0),),
            "книгу": (MorphInfo("книга", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
            "я": (MorphInfo("я", "NPRO", case="nomn", number="sing", grammemes=frozenset({"1per"}), score=1.0),),
            "открыл": (MorphInfo("открыть", "VERB", number="sing", mood="indc", score=1.0),),
            "её": (MorphInfo("она", "NPRO", case="accs", number="sing", gender="femn", grammemes=frozenset({"3per"}), score=1.0),),
        })
        parser = make_parser(ScriptedBackend({}), morph)
        text = "Мне дали книгу. Я открыл её."
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        by_id = {
            "A1": AssertionCandidate(
                "A1", PredicateCandidate("дали", "дать", evidence=EvidenceSpan("дали", 4, 8)),
                (
                    ActantCandidate(ActantRole.RECIPIENT, mention="Мне", normalized_hint="я", entity_ref="E1", evidence=EvidenceSpan("Мне", 0, 3)),
                    ActantCandidate(ActantRole.OBJECT, mention="книгу", normalized_hint="книга", entity_ref="E2", evidence=EvidenceSpan("книгу", 9, 14)),
                ),
            ),
            "A2": AssertionCandidate(
                "A2", PredicateCandidate("открыл", "открыть", evidence=EvidenceSpan("открыл", 18, 24)),
                (
                    ActantCandidate(ActantRole.SUBJECT, mention="Я", normalized_hint="я", entity_ref="E3", evidence=EvidenceSpan("Я", 16, 17)),
                    ActantCandidate(ActantRole.OBJECT, mention="её", normalized_hint="она", evidence=EvidenceSpan("её", 25, 27)),
                ),
            ),
        }
        parser._resolve_pronoun_coreferences(by_id)
        resolved = by_id["A2"]
        obj = next(item for item in resolved.actants if item.role is ActantRole.OBJECT)
        self.assertEqual(obj.entity_ref, "E2")
        self.assertEqual(resolved.alternatives, ())


if __name__ == "__main__":
    unittest.main()
