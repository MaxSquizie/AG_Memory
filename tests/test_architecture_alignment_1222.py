from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.errors import CandidateValidationError
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    SituationRelationCandidate,
    TemplateCandidate,
    TextSensoryService,
)
from ah.perception.adaptive_parser import (
    AdaptivePerceptionParser, AdaptiveSettings, _EVENT_RECIPIENT_COMPLETION,
)
from ah.perception.morphology import MorphInfo, stable_normal_form

from test_acceptance_regressions_1218 import AcceptanceMorphology
from test_acceptance_regressions_1219 import DiscourseMorphology, HomeMorphology, RecordingBackend, make_parser

PROJECT = Path(__file__).resolve().parents[1]


class _TemplateBackend:
    def __init__(self):
        self.answers = {
            "perception_template_hidden_valency": [_EVENT_RECIPIENT_COMPLETION],
        }
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, override))
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected call {role}\n{prompt}")
        return LLMResponse(str(values.pop(0)), {})


class _PyotrMorphology:
    name = "fake"

    def analyze_all(self, word: str):
        if word.casefold() == "петру":
            return (
                MorphInfo("пётр", "NOUN", case="datv", number="sing", gender="masc", animacy="anim", score=0.666666),
                MorphInfo("петра", "NOUN", case="accs", number="sing", gender="femn", animacy="anim", score=0.333333),
            )
        if word.casefold() == "пётр":
            return (MorphInfo("пётр", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),)
        return ()

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class ArchitectureAlignment1222Tests(unittest.TestCase):

    def test_directional_follow_removes_redundant_time_candidate_ref(self):
        class Morph(AcceptanceMorphology):
            def analyze_all(self, word: str):
                values = {
                    "мария": (MorphInfo("Мария", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
                    "прочитала": (MorphInfo("прочитать", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
                    "книгу": (MorphInfo("книга", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
                    "написала": (MorphInfo("написать", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
                    "отзыв": (MorphInfo("отзыв", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
                }
                return values.get(word.casefold(), super().analyze_all(word))

        result = make_parser(Morph()).parse(
            "После того как Мария прочитала книгу, она написала отзыв."
        ).perception
        self.assertEqual(len(result.relations), 1)
        self.assertEqual(result.relations[0].canonical_relation_id, "FOLLOW")
        self.assertFalse(any(
            a.role == ActantRole.TIME and a.candidate_ref is not None
            for assertion in result.assertions for a in assertion.actants
        ))

    def test_cause_link_is_not_duplicated_as_nested_cause_actant(self):
        parent = AssertionCandidate(
            "A1",
            PredicateCandidate("остался", "остаться"),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                ActantCandidate(ActantRole.CAUSE, candidate_ref="A2"),
            ),
        )
        child = AssertionCandidate(
            "A2",
            PredicateCandidate("шёл", "идти"),
            (ActantCandidate(ActantRole.SUBJECT, mention="дождь"),),
        )
        relation = SituationRelationCandidate("CAUSE", "A2", "A1")
        normalized = AdaptivePerceptionParser._strip_structural_relation_actants(
            [parent, child], (relation,)
        )
        self.assertFalse(any(
            a.role == ActantRole.CAUSE and a.candidate_ref is not None
            for assertion in normalized for a in assertion.actants
        ))

    def test_integration_rejects_duplicate_inter_situation_cause_encoding(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
        self_m = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
        from ah.agent import InteractionContext
        context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_m.uid))
        service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.02))
        template = TemplateCandidate((ActantRole.SUBJECT, ActantRole.CAUSE))
        result = PerceptionResult(
            "A because B",
            assertions=(
                AssertionCandidate(
                    "A1", PredicateCandidate("A", "a", template_candidate=template),
                    (ActantCandidate(ActantRole.SUBJECT, mention="x"), ActantCandidate(ActantRole.CAUSE, candidate_ref="A2")),
                ),
                AssertionCandidate(
                    "A2", PredicateCandidate("B", "b", template_candidate=TemplateCandidate((ActantRole.SUBJECT,))),
                    (ActantCandidate(ActantRole.SUBJECT, mention="y"),),
                ),
            ),
            relations=(SituationRelationCandidate("CAUSE", "A2", "A1"),),
        )
        with self.assertRaisesRegex(CandidateValidationError, "represented once as L"):
            service.integrate_external(result, context)

    def test_equal_score_lexical_homonym_remains_unresolved(self):
        analyses = (
            MorphInfo("прислать", "VERB", number="sing", mood="impr", score=0.5),
            MorphInfo("прийти", "VERB", number="plur", mood="indc", score=0.5),
        )
        self.assertIsNone(stable_normal_form(analyses, poses={"VERB"}))

    def test_dominant_proper_name_parse_unifies_pyotr_dative_lexical_symbol(self):
        morph = _PyotrMorphology()
        self.assertEqual(stable_normal_form(morph.analyze_all("Петру"), poses={"NOUN"}), "пётр")
        core = AHCore(uid_generator=SequentialUidGenerator())
        sensory = TextSensoryService(core, morph)
        first = sensory.process("Пётр")
        second = sensory.process("Петру")
        self.assertEqual(first.symbol_refs[0], second.symbol_refs[0])
        symbol = core.store.get_symbol(first.symbol_refs[0].uid)
        self.assertIn("Пётр", symbol.forms)
        self.assertIn("Петру", symbol.forms)

    def test_explicit_discourse_continuation_resolves_same_role_coreference_without_llm(self):
        result = make_parser(
            DiscourseMorphology(),
            RecordingBackend({"perception_role_participant": ["OBJECT"]}),
        ).parse("Сергей положил ключ на стол. Потом он взял его.").perception
        placed, took = result.assertions
        self.assertEqual(took.alternatives, ())
        for role in (ActantRole.SUBJECT, ActantRole.OBJECT):
            prior = next(a for a in placed.actants if a.role == role)
            current = next(a for a in took.actants if a.role == role)
            self.assertEqual(current.entity_ref, prior.entity_ref)
        self.assertTrue(any(
            relation.canonical_relation_id == "FOLLOW"
            and relation.source_ref == placed.local_id
            and relation.target_ref == took.local_id
            for relation in result.relations
        ))
        self.assertFalse(any(
            actant.role == ActantRole.TIME
            and (actant.lookup_text or "").casefold() == "потом"
            for actant in took.actants
        ))

    def test_spatial_adverb_is_location_without_semantic_llm_guess(self):
        backend = RecordingBackend()
        result = make_parser(HomeMorphology(), backend).parse("Иван остался дома.").perception
        self.assertTrue(any(a.role == ActantRole.LOCATION for a in result.assertions[0].actants))
        self.assertFalse(any(a.role == ActantRole.STATE for a in result.assertions[0].actants))
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
