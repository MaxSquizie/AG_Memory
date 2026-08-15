from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception import CompositionOperator
from ah.perception.adaptive_parser import AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class AcceptanceMorphology:
    name = "acceptance-test"
    DATA = {
        "кто": ("кто", "NPRO", "nomn"), "что": ("что", "NPRO", "accs"), "кому": ("кто", "NPRO", "datv"),
        "иван": ("Иван", "NOUN", "nomn"), "иваном": ("Иван", "NOUN", "ablt"),
        "мария": ("Мария", "NOUN", "nomn"), "марии": ("Мария", "NOUN", "datv"), "марию": ("Мария", "NOUN", "accs"),
        "анна": ("Анна", "NOUN", "nomn"), "пётр": ("Пётр", "NOUN", "nomn"), "петра": ("Пётр", "NOUN", "accs"),
        "лиза": ("Лиза", "NOUN", "nomn"), "она": ("она", "NPRO", "nomn"), "его": ("он", "NPRO", "accs"),
        "книга": ("книга", "NOUN", "nomn"), "книгу": ("книга", "NOUN", "accs"), "чай": ("чай", "NOUN", "accs"),
        "документы": ("документ", "NOUN", "accs"), "работу": ("работа", "NOUN", "accs"), "отзыв": ("отзыв", "NOUN", "accs"),
        "журнал": ("журнал", "NOUN", "accs"), "журналом": ("журнал", "NOUN", "ablt"), "биноклем": ("бинокль", "NOUN", "ablt"), "столе": ("стол", "NOUN", "loct"),
        "хлеб": ("хлеб", "NOUN", "accs"), "молоко": ("молоко", "NOUN", "accs"), "письмо": ("письмо", "NOUN", "accs"),
        "человек": ("Человек", "NOUN", "nomn"), "который": ("который", "ADJF", "nomn"), "комнату": ("комната", "NOUN", "accs"), "стул": ("стул", "NOUN", "accs"),
        "я": ("я", "NPRO", "nomn"), "рядом": ("рядом", "ADVB", None),
        "советы": ("совет", "NOUN", "accs"), "текст": ("текст", "NOUN", "accs"),
        "подарил": ("подарить", "VERB", None), "любит": ("любить", "VERB", None), "читает": ("читать", "VERB", None),
        "написал": ("написать", "VERB", None), "отправил": ("отправить", "VERB", None), "положил": ("положить", "VERB", None),
        "вошёл": ("войти", "VERB", None), "сел": ("сесть", "VERB", None),
        "написана": ("написать", "PRTS", None), "прочитала": ("прочитать", "VERB", None), "написала": ("написать", "VERB", None),
        "придёт": ("прийти", "VERB", None), "принесёт": ("принести", "VERB", None), "начнёт": ("начать", "VERB", None),
        "купил": ("купить", "VERB", None), "лежит": ("лежать", "VERB", None), "попросил": ("попросить", "VERB", None),
        "прочитать": ("прочитать", "INFN", None), "сказала": ("сказать", "VERB", None), "победила": ("победить", "VERB", None),
        "увидел": ("увидеть", "VERB", None),
        "если": ("если", "CONJ", None), "и": ("и", "CONJ", None), "а": ("а", "CONJ", None), "что": ("что", "CONJ", None),
        "после": ("после", "PREP", None), "перед": ("перед", "PREP", None), "того": ("тот", "NPRO", "gent"), "тем": ("тот", "NPRO", "ablt"),
        "как": ("как", "CONJ", None), "на": ("на", "PREP", None), "с": ("с", "PREP", None), "не": ("не", "PRCL", None),
        "которую": ("который", "ADJF", "accs"),
    }

    # Context-sensitive homograph needed for the question-word tests.
    def analyze(self, word: str):
        key = word.casefold()
        if key == "что":
            return MorphInfo("что", "NPRO", case="accs", score=1.0)
        item = self.DATA.get(key)
        if item is None:
            return None
        lemma, pos, case = item
        return MorphInfo(lemma, pos, case=case, score=1.0)

    def analyze_all(self, word: str):
        info = self.analyze(word)
        return () if info is None else (info,)


class Backend:
    def __init__(self, answers=None):
        self.answers = {k: list(v) for k, v in (answers or {}).items()}
        self.roles = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.roles.append(role)
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")
        return LLMResponse(str(values.pop(0)), {})


def parser(backend=None):
    return AdaptivePerceptionParser(
        backend or Backend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=AcceptanceMorphology(),
    )


class AcceptanceRegressions1218(unittest.TestCase):
    def test_wh_questions_are_queries_and_placeholders_are_not_actants(self):
        cases = [
            ("Кто подарил Марии книгу?", ActantRole.SUBJECT),
            ("Что Иван подарил Марии?", ActantRole.OBJECT),
            ("Кому Иван подарил книгу?", ActantRole.RECIPIENT),
            ("Кто любит чай?", ActantRole.SUBJECT),
        ]
        for text, requested in cases:
            with self.subTest(text=text):
                result = parser().parse(text).perception
                self.assertEqual(result.assertions, ())
                self.assertEqual(len(result.queries), 1)
                query = result.queries[0]
                self.assertEqual(query.requested_role, requested)
                self.assertNotIn(text.split()[0].rstrip("?"), [a.mention for a in query.actants])

    def test_passive_participle_inverts_agent_and_patient(self):
        result = parser().parse("Книга написана Иваном.").perception
        assertion = result.assertions[0]
        roles = {a.role: a.normalized_hint for a in assertion.actants}
        self.assertEqual(roles[ActantRole.SUBJECT], "Иван")
        self.assertEqual(roles[ActantRole.OBJECT].casefold(), "книга")

    def test_fronted_compound_temporal_connector_is_not_an_actant(self):
        result = parser().parse("После того как Мария прочитала книгу, она написала отзыв.").perception
        self.assertEqual(len(result.assertions), 2)
        mentions = [a.mention for n in result.assertions for a in n.actants if a.mention]
        self.assertFalse(any(m.casefold().startswith("после") for m in mentions))
        self.assertEqual(len(result.relations), 1)
        self.assertEqual(result.relations[0].relation_id, "FOLLOW")
        self.assertEqual((result.relations[0].source_ref, result.relations[0].target_ref), ("A1", "A2"))

    def test_compound_conditional_scope_contains_both_antecedents(self):
        result = parser().parse("Если Иван придёт и Мария принесёт документы, Пётр начнёт работу.").perception
        self.assertEqual(len(result.assertions), 3)
        self.assertEqual(len(result.conditionals), 1)
        condition = result.conditionals[0]
        self.assertEqual(condition.antecedent_refs, ("A1", "A2"))
        self.assertEqual(condition.consequent_refs, ("A3",))

    def test_relative_clause_does_not_leak_its_subject_to_matrix_clause(self):
        result = parser().parse("Книга, которую Иван купил, лежит на столе.").perception
        self.assertEqual(len(result.assertions), 2)
        buy, lie = result.assertions
        buy_roles = {a.role: a.normalized_hint for a in buy.actants if a.mention}
        lie_roles = {a.role: a.normalized_hint for a in lie.actants if a.mention}
        self.assertEqual(buy_roles[ActantRole.SUBJECT], "Иван")
        self.assertEqual(buy_roles[ActantRole.OBJECT].casefold(), "книга")
        self.assertEqual(lie_roles[ActantRole.SUBJECT].casefold(), "книга")

    def test_contrastive_negation_expands_to_false_and_positive_frames(self):
        result = parser().parse("Иван читает не книгу, а журнал.").perception
        self.assertEqual(len(result.assertions), 2)
        negative, positive = result.assertions
        self.assertTrue(negative.negated)
        self.assertFalse(positive.negated)
        self.assertEqual(next(a.normalized_hint for a in negative.actants if a.role == ActantRole.OBJECT), "книга")
        self.assertEqual(next(a.normalized_hint for a in positive.actants if a.role == ActantRole.OBJECT), "журнал")

    def test_unclear_prepositional_attachment_fails_explicitly(self):
        backend = Backend()
        with self.assertRaises(AdaptiveParseError):
            parser(backend).parse("Иван увидел Петра с биноклем.")
        self.assertEqual(backend.roles, [])

    def test_ambiguous_embedded_pronoun_can_fail_explicitly(self):
        backend = Backend()
        with self.assertRaises(AdaptiveParseError):
            parser(backend).parse("Анна сказала Марии, что она победила.")
        self.assertEqual(backend.roles, [])


if __name__ == "__main__":
    unittest.main()

class LexicalIdentityRegressions1218(unittest.TestCase):
    def test_text_sensory_reuses_one_symbol_across_inflected_forms(self):
        from ah.core import AHCore, SequentialUidGenerator
        from ah.perception import TextSensoryService

        core = AHCore(uid_generator=SequentialUidGenerator())
        sensory = TextSensoryService(core, AcceptanceMorphology())
        first = sensory.process("Мария")
        second = sensory.process("Марии")
        third = sensory.process("Марию")
        self.assertEqual(first.symbol_refs[0].uid, second.symbol_refs[0].uid)
        self.assertEqual(first.symbol_refs[0].uid, third.symbol_refs[0].uid)
        symbol = core.store.get_symbol(first.symbol_refs[0].uid)
        self.assertEqual(symbol.forms, frozenset({"Мария", "Марии", "Марию"}))

    def test_entity_resolver_uses_normalized_hint_before_surface_case_form(self):
        from ah.agent import InteractionContext
        from ah.core import AHCore, SequentialUidGenerator
        from ah.integration.entity_resolver import EntityResolver, ExistingEntity, NewEntityPlan
        from ah.model import Domain, Property
        from ah.perception import ActantCandidate

        core = AHCore(uid_generator=SequentialUidGenerator())
        resolver = EntityResolver(core)
        first = resolver.resolve(
            ActantCandidate(ActantRole.SUBJECT, mention="Мария", normalized_hint="Мария"),
            InteractionContext(),
        )
        self.assertIsInstance(first, NewEntityPlan)
        entity = core.add_entity(Domain.C, {"name": Property("name", first.name, "str")})
        second = resolver.resolve(
            ActantCandidate(ActantRole.RECIPIENT, mention="Марии", normalized_hint="Мария"),
            InteractionContext(),
        )
        self.assertIsInstance(second, ExistingEntity)
        self.assertEqual(second.ref.uid, entity.uid)

class StructuralRegressions1218(unittest.TestCase):
    def test_coordinated_postverbal_nominals_are_object_when_subject_is_explicit(self):
        result = parser().parse("Иван купил хлеб и молоко.").perception
        assertion = result.assertions[0]
        obj = next(a for a in assertion.actants if a.role == ActantRole.OBJECT)
        self.assertIsNotNone(obj.composition)
        self.assertEqual(obj.composition.operator, CompositionOperator.AND)

    def test_pronoun_and_dative_are_separate_send_actants(self):
        result = parser().parse("Иван написал письмо и отправил его Марии.").perception
        self.assertEqual(len(result.assertions), 2)
        send = result.assertions[1]
        roles = {a.role: a for a in send.actants}
        self.assertEqual(roles[ActantRole.OBJECT].entity_ref, result.assertions[0].actants[1].entity_ref)
        self.assertEqual(roles[ActantRole.RECIPIENT].normalized_hint, "Мария")
        self.assertNotIn("его Марии", [a.mention for a in send.actants])

    def test_relational_spatial_phrase_is_one_location(self):
        result = parser().parse("Я положил книгу рядом с журналом.").perception
        assertion = result.assertions[0]
        locations = [a for a in assertion.actants if a.role == ActantRole.LOCATION]
        self.assertEqual(len(locations), 1)
        self.assertEqual(locations[0].normalized_hint, "журнал")
        self.assertEqual(locations[0].evidence.text, "рядом с журналом")

    def test_nominative_relative_pronoun_binds_subject_without_llm(self):
        result = parser().parse("Человек, который вошёл в комнату, сел на стул.").perception
        self.assertEqual(len(result.assertions), 2)
        enter, sit = result.assertions
        self.assertEqual(next(a.normalized_hint or a.mention for a in enter.actants if a.role == ActantRole.SUBJECT), "Человек")
        self.assertEqual(next(a.normalized_hint or a.mention for a in sit.actants if a.role == ActantRole.SUBJECT), "Человек")

    def test_control_subject_is_selected_only_after_nested_frame_is_known(self):
        backend = Backend({
            "perception_frame_relation": [1],  # PURPOSE is first free nested-situation role
            "perception_control_subject": [2],  # Maria, not matrix subject Ivan
        })
        result = parser(backend).parse("Иван попросил Марию прочитать книгу.").perception
        self.assertEqual(len(result.assertions), 2)
        parent, child = result.assertions
        self.assertTrue(any(a.candidate_ref == child.local_id for a in parent.actants))
        subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(subject.normalized_hint, "Мария")

    def test_causal_control_keeps_matrix_cause_and_selects_embedded_controller(self):
        class GenderedMorphology(AcceptanceMorphology):
            def analyze(self, word: str):
                key = word.casefold()
                if key == "открыл":
                    return MorphInfo("открыть", "VERB", score=1.0)
                if key == "дверь":
                    return MorphInfo("дверь", "NOUN", case="accs", gender="femn", score=1.0)
                if key == "попросила":
                    return MorphInfo("попросить", "VERB", gender="femn", score=1.0)
                if key == "войти":
                    return MorphInfo("войти", "INFN", score=1.0)
                info = super().analyze(word)
                if info is None:
                    return None
                if key == "иван":
                    return MorphInfo(info.normal_form, info.pos, case=info.case, gender="masc", score=1.0)
                if key == "мария":
                    return MorphInfo(info.normal_form, info.pos, case=info.case, gender="femn", score=1.0)
                if key == "его":
                    return MorphInfo(info.normal_form, info.pos, case=info.case, gender="masc", score=1.0)
                return info

            def analyze_all(self, word: str):
                info = self.analyze(word)
                return () if info is None else (info,)

        backend = Backend({
            "perception_frame_relation": [1],  # PURPOSE after REQUEST already has OBJECT
            "perception_control_subject": [2],  # object pronoun=Ivan, not Maria
        })
        p = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=GenderedMorphology(),
        )
        result = p.parse("Иван открыл дверь, потому что Мария попросила его войти.").perception
        self.assertEqual(len(result.assertions), 3)
        opened, requested, entered = result.assertions
        self.assertTrue(any(a.role == ActantRole.CAUSE and a.candidate_ref == requested.local_id for a in opened.actants))
        request_object = next(a for a in requested.actants if a.role == ActantRole.OBJECT)
        enter_subject = next(a for a in entered.actants if a.role == ActantRole.SUBJECT)
        self.assertIsNotNone(request_object.entity_ref)
        self.assertEqual(enter_subject.entity_ref, request_object.entity_ref)
        self.assertEqual(result.relations[0].relation_id, "CAUSE")
        self.assertEqual((result.relations[0].source_ref, result.relations[0].target_ref), (requested.local_id, opened.local_id))

    def test_turn_local_entity_ref_uses_named_anchor_even_when_child_integrates_first(self):
        from ah.agent import InteractionContext
        from ah.core import AHCore, SequentialUidGenerator
        from ah.integration import IntegrationConfig, IntegrationService
        from ah.model import Domain, Property
        from ah.perception import ActantCandidate, AssertionCandidate, PerceptionResult, PredicateCandidate, TemplateCandidate

        core = AHCore(uid_generator=SequentialUidGenerator())
        user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
        self_entity = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
        context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
        service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.02))
        child = AssertionCandidate(
            "A2",
            PredicateCandidate("победила", "победить", template_candidate=TemplateCandidate((ActantRole.SUBJECT,))),
            (ActantCandidate(ActantRole.SUBJECT, mention="она", normalized_hint="она", entity_ref="E1"),),
        )
        parent = AssertionCandidate(
            "A1",
            PredicateCandidate("сказала", "сказать", template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT))),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Анна", normalized_hint="Анна", entity_ref="E1"),
                ActantCandidate(ActantRole.OBJECT, candidate_ref="A2"),
            ),
        )
        service.integrate_external(PerceptionResult("Анна сказала, что она победила.", (parent, child)), context)
        annas = core.store.find_entities_by_name("Анна", Domain.C)
        pronouns = core.store.find_entities_by_name("она", Domain.C)
        self.assertEqual(len(annas), 1)
        self.assertEqual(pronouns, ())
        child_node = next(
            n for n in core.store.all_elements()
            if getattr(n, "template", None) is not None
            and core.store.get_symbol(core.store.get_template(n.template.uid).predicate.uid).forms & {"победить", "победила"}
        )
        self.assertEqual(child_node.actants[ActantRole.SUBJECT].uid, annas[0].uid)

    def test_sensory_and_predicate_template_share_one_lexical_symbol(self):
        from ah.core import AHCore, SequentialUidGenerator
        from ah.integration.template_resolver import TemplateResolver
        from ah.model import Domain
        from ah.perception import PredicateCandidate, TemplateCandidate, TextSensoryService

        core = AHCore(uid_generator=SequentialUidGenerator())
        sensory = TextSensoryService(core, AcceptanceMorphology())
        sensed = sensory.process("подарил").symbol_refs[0]
        resolved = TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(
                "подарил", "подарить",
                template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.assertEqual(resolved.template.predicate.uid, sensed.uid)
        self.assertEqual(core.store.get_symbol(sensed.uid).forms, frozenset({"подарить", "подарил"}))
