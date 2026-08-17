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


def target_span(text="TARGET_X"):
    return _Span(1, 1, text, EvidenceSpan(text, 0, len(text)))


class SemanticPropertyRouter1256Tests(unittest.TestCase):
    def test_temporal_property_selects_only_temporal_subset_before_contrast(self):
        backend = ScriptedBackend({
            "perception_role_property": ["YES"],
            "perception_role_contrast": ["A"],
        })
        parser = make_parser(backend)
        role = parser._classify_role(
            "PRED TARGET_X",
            PredicateCandidate("PRED"),
            target_span(),
            set(),
            None,
            requested=False,
        )
        self.assertEqual(role, ActantRole.TIME)
        self.assertEqual(
            [call[0] for call in backend.calls],
            ["perception_role_property", "perception_role_contrast"],
        )
        property_prompt = backend.calls[0][1]
        self.assertIn("PROPERTY ID:\nTEMPORAL", property_prompt)
        self.assertIn("CHOICES:\nYES\nNO", property_prompt)
        self.assertNotIn("OPTION B INTERPRETATIONS", property_prompt)
        self.assertNotIn("instrument or tool", property_prompt)
        self.assertNotIn("receiver", property_prompt)
        self.assertNotIn("cause", property_prompt.casefold())
        contrast_prompt = backend.calls[1][1]
        self.assertIn("locates the event on a timeline", contrast_prompt)
        self.assertIn("elapsed temporal length", contrast_prompt)
        self.assertNotIn("instrument or tool", contrast_prompt)
        self.assertNotIn("receiver", contrast_prompt)

    def test_source_is_not_removed_by_unrelated_property_rejections(self):
        backend = ScriptedBackend({
            "perception_role_property": ["NO", "NO", "NO", "NO", "YES"],
            "perception_role_contrast": ["A"],
        })
        parser = make_parser(backend)
        role = parser._classify_role(
            "PRED TARGET_X",
            PredicateCandidate("PRED"),
            target_span(),
            set(),
            None,
            requested=False,
        )
        self.assertEqual(role, ActantRole.SOURCE)
        property_ids = [
            call[1].split("PROPERTY ID:\n", 1)[1].split("\n", 1)[0]
            for call in backend.calls
            if call[0] == "perception_role_property"
        ]
        self.assertEqual(
            property_ids,
            [
                "TEMPORAL",
                "NON_TEMPORAL_MEASURE",
                "CAUSE_OR_GOAL",
                "MEANS_MATERIAL_OR_MANNER",
                "PLACE_OR_TRANSFER_ENDPOINT",
            ],
        )
        contrast = backend.calls[-1][1]
        self.assertIn("origin from which", contrast)
        self.assertIn("where or to what place", contrast)
        self.assertIn("receiver", contrast)

    def test_material_is_selected_by_property_then_local_contrast_only(self):
        backend = ScriptedBackend({
            "perception_role_property": ["NO", "NO", "NO", "YES"],
            "perception_role_contrast": ["B", "B"],
        })
        parser = make_parser(backend)
        role = parser._classify_role(
            "PRED TARGET_X",
            PredicateCandidate("PRED"),
            target_span(),
            set(),
            None,
            requested=False,
        )
        self.assertEqual(role, ActantRole.MATERIAL)
        contrasts = [call[1] for call in backend.calls if call[0] == "perception_role_contrast"]
        self.assertEqual(len(contrasts), 2)
        self.assertIn("manner, procedure, or method", contrasts[0])
        self.assertIn("instrument or tool", contrasts[0])
        self.assertIn("substance or material", contrasts[0])
        self.assertIn("instrument or tool", contrasts[1])
        self.assertIn("substance or material", contrasts[1])
        self.assertNotIn("locates the event on a timeline", contrasts[1])
        self.assertNotIn("origin from which", contrasts[1])

    def test_pre_narrowed_subset_skips_membership_properties_and_never_expands(self):
        backend = ScriptedBackend({"perception_role_contrast": ["A"]})
        parser = make_parser(backend)
        role = parser._classify_role(
            "PRED TARGET_X",
            PredicateCandidate("PRED"),
            target_span(),
            set(),
            None,
            requested=False,
            allowed_roles={ActantRole.TOOL, ActantRole.MATERIAL},
        )
        self.assertEqual(role, ActantRole.TOOL)
        self.assertEqual([call[0] for call in backend.calls], ["perception_role_contrast"])
        prompt = backend.calls[0][1]
        self.assertNotIn("locates the event on a timeline", prompt)
        self.assertNotIn("subject", prompt.casefold())
        self.assertNotIn("receiver", prompt)

    def test_malformed_property_answer_fails_closed(self):
        backend = ScriptedBackend({"perception_role_property": ["MAYBE"]})
        parser = make_parser(backend)
        with self.assertRaisesRegex(Exception, "role_property expected exactly one of"):
            parser._classify_role(
                "PRED TARGET_X", PredicateCandidate("PRED"), target_span(), set(), None,
                requested=False,
            )

    def test_origin_prepositions_are_not_direct_source_assignments(self):
        source = (PROJECT / "src/ah/perception/adaptive_parser.py").read_text(encoding="utf-8")
        self.assertNotIn('words[0] in {"из", "от"}', source)
        self.assertNotIn('words[0] in {"от", "из"}', source)


class QuantifiedPhrase1256Tests(unittest.TestCase):
    def _fixture(self, backend):
        morph = Morphology({
            "pred": (MorphInfo("pred", "VERB", score=1.0),),
            "two": (MorphInfo("two", "NUMR", score=1.0),),
            "unit": (MorphInfo("unit", "NOUN", case="gent", score=1.0),),
        })
        parser = make_parser(backend, morph)
        text = "pred two unit"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        amount_span = parser._resolve_span(text, tokens, 2, 2)
        nominal_span = parser._resolve_span(text, tokens, 3, 3)
        actants = [
            parser._make_actant(ActantRole.AMOUNT, amount_span),
            parser._make_actant(ActantRole.OBJECT, nominal_span),
        ]
        return parser, text, tokens, amount_span, nominal_span, actants

    def test_counted_entity_keeps_amount_and_participant_without_unit_lexicon(self):
        backend = ScriptedBackend({"perception_quantified_phrase": ["A"]})
        parser, text, tokens, amount_span, nominal_span, actants = self._fixture(backend)
        result, spans = parser._normalize_quantified_measure_actants(
            text,
            tokens,
            PredicateCandidate("pred"),
            actants,
            [amount_span, nominal_span],
        )
        self.assertEqual([item.role for item in result], [ActantRole.AMOUNT, ActantRole.OBJECT])
        self.assertEqual([span.text for span in spans], ["two", "unit"])
        self.assertEqual([call[0] for call in backend.calls], ["perception_quantified_phrase"])

    def test_malformed_quantified_structure_answer_fails_closed(self):
        backend = ScriptedBackend({"perception_quantified_phrase": ["UNKNOWN"]})
        parser, text, tokens, amount_span, nominal_span, actants = self._fixture(backend)
        with self.assertRaisesRegex(Exception, "quantified_phrase expected exactly one of"):
            parser._normalize_quantified_measure_actants(
                text, tokens, PredicateCandidate("pred"), actants, [amount_span, nominal_span]
            )

    def test_event_measure_fuses_phrase_and_uses_generic_duration_amount_boundary(self):
        backend = ScriptedBackend({
            "perception_quantified_phrase": ["B"],
            "perception_role_property": ["YES"],
        })
        parser, text, tokens, amount_span, nominal_span, actants = self._fixture(backend)
        result, spans = parser._normalize_quantified_measure_actants(
            text,
            tokens,
            PredicateCandidate("pred"),
            actants,
            [amount_span, nominal_span],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].role, ActantRole.DURATION)
        self.assertEqual(result[0].mention, "two unit")
        self.assertEqual([span.text for span in spans], ["two unit"])
        self.assertEqual(
            [call[0] for call in backend.calls],
            ["perception_quantified_phrase", "perception_role_property"],
        )
        self.assertIn("PROPERTY ID:\nTEMPORAL", backend.calls[1][1])


if __name__ == "__main__":
    unittest.main()
