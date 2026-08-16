from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import MorphInfo

from test_acceptance_regressions_1218 import AcceptanceMorphology, RequestMorphology

PROJECT = Path(__file__).resolve().parents[1]


class RecordingBackend:
    def __init__(self, answers=None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
        self.calls: list[tuple[str, str, dict | None]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, override))
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")
        return LLMResponse(str(values.pop(0)), {})


def make_parser(morphology, backend=None):
    return AdaptivePerceptionParser(
        backend or RecordingBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


class AgreementMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        key = word.casefold()
        if key == "пришли":
            return (
                MorphInfo("прислать", "VERB", number="sing", mood="impr", score=0.5),
                MorphInfo("прийти", "VERB", number="plur", mood="indc", score=0.5),
            )
        if key == "иван":
            return (MorphInfo("Иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),)
        if key == "мария":
            return (MorphInfo("Мария", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),)
        return super().analyze_all(word)




class ChainMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        key = word.casefold()
        values = {
            "взяла": (MorphInfo("взять", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
            "открыла": (MorphInfo("открыть", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
            "прочитала": (MorphInfo("прочитать", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
            "лиза": (MorphInfo("Лиза", "NOUN", case="nomn", number="sing", gender="femn", animacy="anim", score=1.0),),
            "книгу": (MorphInfo("книга", "NOUN", case="accs", number="sing", gender="femn", animacy="inan", score=1.0),),
            "её": (MorphInfo("она", "NPRO", case="accs", number="sing", gender="femn", score=1.0),),
        }
        if key in values:
            return values[key]
        return super().analyze_all(word)


class HomeMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        key = word.casefold()
        if key == "остался":
            return (MorphInfo("остаться", "VERB", number="sing", mood="indc", score=1.0),)
        if key == "дома":
            return (
                MorphInfo("дом", "NOUN", case="gent", number="sing", gender="masc", score=0.637),
                MorphInfo("дома", "ADVB", score=0.315),
            )
        if key == "иван":
            return (MorphInfo("Иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),)
        return super().analyze_all(word)


class DiscourseMorphology(AcceptanceMorphology):
    def analyze_all(self, word: str):
        key = word.casefold()
        values = {
            "сергей": (MorphInfo("Сергей", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),),
            "положил": (MorphInfo("положить", "VERB", number="sing", mood="indc", score=1.0),),
            "ключ": (MorphInfo("ключ", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=1.0),),
            "стол": (MorphInfo("стол", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=1.0),),
            "потом": (MorphInfo("потом", "ADVB", score=1.0),),
            "он": (MorphInfo("он", "NPRO", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),),
            "взял": (MorphInfo("взять", "VERB", number="sing", mood="indc", score=1.0),),
            "его": (MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", score=1.0),),
        }
        if key in values:
            return values[key]
        return super().analyze_all(word)


class AcceptanceRegressions1219(unittest.TestCase):
    def test_equal_score_predicate_homograph_uses_mood_and_subject_number(self):
        result = make_parser(AgreementMorphology()).parse("Иван и Мария пришли.").perception
        self.assertEqual(len(result.assertions), 1)
        self.assertEqual(result.assertions[0].predicate.normalized_hint, "прийти")

    def test_resolved_pronominal_object_is_inherited_across_coordinated_ellipsis(self):
        result = make_parser(
            ChainMorphology(), RecordingBackend({"perception_role_participant": ["OBJECT"]})
        ).parse("Лиза взяла книгу, открыла её и прочитала.").perception
        self.assertEqual(len(result.assertions), 3)
        take, opened, read = result.assertions
        source_object = next(a for a in opened.actants if a.role == ActantRole.OBJECT)
        read_object = next(a for a in read.actants if a.role == ActantRole.OBJECT)
        self.assertIsNotNone(source_object.entity_ref)
        self.assertEqual(read_object.entity_ref, source_object.entity_ref)
        self.assertIsNone(read_object.evidence)
        # Raw Perception no longer mistakes occurrence filling for a reusable T schema.
        self.assertIsNone(read.predicate.template_candidate)
        self.assertEqual(
            next(a.entity_ref for a in take.actants if a.role == ActantRole.OBJECT),
            read_object.entity_ref,
        )

    def test_request_content_and_controller_use_separate_semantic_decisions(self):
        backend = RecordingBackend({
            "perception_content_addressee": ["CONTENT_ADDRESSEE"],
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_control_subject": ["SECOND"],
        })
        parsed = make_parser(RequestMorphology(), backend).parse(
            "Иван попросил Марию прочитать книгу."
        )
        parent, child = parsed.perception.assertions
        recipient = next(a for a in parent.actants if a.role == ActantRole.RECIPIENT)
        content = next(a for a in parent.actants if a.role == ActantRole.OBJECT)
        subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(content.candidate_ref, child.local_id)
        self.assertEqual(subject.entity_ref, recipient.entity_ref)
        self.assertEqual(subject.normalized_hint, "Мария")
        self.assertEqual(
            [role for role, _p, _o in backend.calls],
            ["perception_frame_relation", "perception_content_addressee", "perception_control_subject"],
        )

    def test_copular_adverb_homograph_is_classified_only_within_descriptive_roles(self):
        backend = RecordingBackend({"perception_role_description": [2]})
        result = make_parser(HomeMorphology(), backend).parse("Иван остался дома.").perception
        assertion = result.assertions[0]
        location = next(a for a in assertion.actants if a.role == ActantRole.LOCATION)
        self.assertEqual(location.mention, "дома")
        self.assertFalse(any(a.role == ActantRole.OBJECT for a in assertion.actants))
        self.assertEqual(backend.calls, [])

    def test_discourse_coreference_uses_deterministic_cues_and_preserves_remaining_alternatives(self):
        backend = RecordingBackend({"perception_role_participant": ["OBJECT"]})
        result = make_parser(DiscourseMorphology(), backend).parse(
            "Сергей положил ключ на стол. Потом он взял его."
        ).perception
        self.assertEqual(len(result.assertions), 2)
        placed, took = result.assertions
        placed_subject = next(a for a in placed.actants if a.role == ActantRole.SUBJECT)
        took_subject = next(a for a in took.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(took_subject.entity_ref, placed_subject.entity_ref)
        placed_object = next(a for a in placed.actants if a.role == ActantRole.OBJECT)
        took_object = next(a for a in took.actants if a.role == ActantRole.OBJECT)
        self.assertEqual(took_object.entity_ref, placed_object.entity_ref)
        self.assertEqual(took.alternatives, ())
        self.assertEqual(backend.calls, [])

    def test_unmarked_cross_sentence_pronoun_remains_explicitly_ambiguous(self):
        class FeminineMorphology(AcceptanceMorphology):
            def analyze_all(self, word: str):
                key = word.casefold()
                values = {
                    "анна": (MorphInfo("Анна", "NOUN", case="nomn", number="sing", gender="femn", animacy="anim", score=1.0),),
                    "увидела": (MorphInfo("увидеть", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
                    "марию": (MorphInfo("Мария", "NOUN", case="accs", number="sing", gender="femn", animacy="anim", score=1.0),),
                    "она": (MorphInfo("она", "NPRO", case="nomn", number="sing", gender="femn", animacy="anim", score=1.0),),
                    "улыбнулась": (MorphInfo("улыбнуться", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
                }
                if key in values:
                    return values[key]
                return super().analyze_all(word)

        backend = RecordingBackend({"perception_role_participant": ["OBJECT"]})
        result = make_parser(FeminineMorphology(), backend).parse(
            "Анна увидела Марию. Она улыбнулась."
        ).perception
        self.assertEqual(len(result.assertions), 2)
        smile = result.assertions[1]
        self.assertEqual(len(smile.alternatives), 2)
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
