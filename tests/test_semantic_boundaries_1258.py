from pathlib import Path
import json
import unittest

from ah.agent import InteractionContext
from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings, _Span
from ah.perception.contracts import EvidenceSpan
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo, build_morphology


PROJECT = Path(__file__).resolve().parents[1]


class ScriptedBackend:
    def __init__(self, answers=None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
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


def make_parser(backend=None, morphology=None):
    return AdaptivePerceptionParser(
        backend or ScriptedBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology or build_morphology("pymorphy3"),
    )


class StructuralNarrowing1258Tests(unittest.TestCase):
    def test_transitive_postverbal_nom_acc_is_not_deterministic_subject(self):
        morph = Morphology({
            "получила": (MorphInfo("получить", "VERB", number="sing", gender="femn", mood="indc", transitivity="tran", grammemes=frozenset({"past", "tran"}), score=1.0),),
            "новость": (
                MorphInfo("новость", "NOUN", case="nomn", number="sing", gender="femn", score=0.7),
                MorphInfo("новость", "NOUN", case="accs", number="sing", gender="femn", score=0.3),
            ),
        })
        parser = make_parser(morphology=morph)
        text = "получила новость"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        predicate = parser._resolve_span(text, tokens, 1, 1)
        self.assertIsNone(parser._deterministic_subject_span(tokens, predicate, None))


    def test_intransitive_postverbal_nominative_remains_recoverable_subject(self):
        morph = Morphology({
            "шёл": (MorphInfo("идти", "VERB", number="sing", gender="masc", mood="indc", transitivity="intr", grammemes=frozenset({"past", "intr"}), score=1.0),),
            "дождь": (MorphInfo("дождь", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        })
        parser = make_parser(morphology=morph)
        text = "шёл дождь"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        predicate = parser._resolve_span(text, tokens, 1, 1)
        subject = parser._deterministic_subject_span(tokens, predicate, None)
        self.assertIsNotNone(subject)
        self.assertEqual(subject.text, "дождь")

    def test_pure_accusative_and_dative_do_not_assign_semantic_roles(self):
        morph = Morphology({
            "объект": (MorphInfo("объект", "NOUN", case="accs", score=1.0),),
            "адресату": (MorphInfo("адресат", "NOUN", case="datv", score=1.0),),
        })
        parser = make_parser(morphology=morph)
        obj_tokens = parser._source_tokens("объект")
        obj_span = parser._resolve_span("объект", obj_tokens, 1, 1)
        self.assertEqual(
            parser._deterministic_role_candidates(obj_tokens, None, PredicateCandidate("P"), obj_span),
            (),
        )
        rec_tokens = parser._source_tokens("адресату")
        rec_span = parser._resolve_span("адресату", rec_tokens, 1, 1)
        self.assertEqual(
            parser._deterministic_role_candidates(rec_tokens, None, PredicateCandidate("P"), rec_span),
            (),
        )

    def test_or_coordinated_nominals_share_direct_object_region(self):
        morph = Morphology({
            "иван": (MorphInfo("иван", "NOUN", case="nomn", number="sing", score=1.0),),
            "купил": (MorphInfo("купить", "VERB", number="sing", mood="indc", transitivity="tran", score=1.0),),
            "чай": (MorphInfo("чай", "NOUN", case="accs", number="sing", score=1.0),),
            "кофе": (MorphInfo("кофе", "NOUN", case="accs", number="sing", score=1.0),),
            "или": (MorphInfo("или", "CONJ", score=1.0),),
        })
        parser = make_parser(morphology=morph)
        text = "Иван купил чай или кофе."
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(parser.morphology).build(text)
        predicate = parser._resolve_span(text, tokens, 2, 2)
        coord = next(c for c in parser._candidate_graph.coordinations if c.operator.value == "OR")
        span = parser._resolve_span(text, tokens, coord.span.start_index, coord.span.end_index)
        roles = parser._deterministic_role_candidates(tokens, predicate, PredicateCandidate("купил", "купить"), span)
        self.assertEqual(roles, ())

    def test_dat_acc_syncretism_preserves_both_core_roles(self):
        morph = Morphology({
            "пальто": (
                MorphInfo("пальто", "NOUN", case="accs", score=0.5),
                MorphInfo("пальто", "NOUN", case="datv", score=0.5),
            )
        })
        parser = make_parser(morphology=morph)
        text = "пальто"
        tokens = parser._source_tokens(text)
        span = parser._resolve_span(text, tokens, 1, 1)
        roles = parser._deterministic_role_candidates(tokens, None, PredicateCandidate("P"), span)
        self.assertEqual(roles, ())

    def test_ambiguous_genitive_dative_nominal_is_not_absorbed_into_previous_np(self):
        parser = make_parser()
        text = "Сергей отправил письмо Марии."
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(parser.morphology).build(text)
        predicate = parser._resolve_span(text, tokens, 2, 2)
        subject = parser._resolve_span(text, tokens, 1, 1)
        candidates = parser._candidate_phrase_spans(text, tokens, predicate, [subject], requested_spans=())
        self.assertIn("письмо", [x.text for x in candidates])
        self.assertIn("Марии", [x.text for x in candidates])
        self.assertNotIn("письмо Марии", [x.text for x in candidates])

    def test_relative_antecedent_ignores_nonmaterial_noun_reading_of_preposition(self):
        morph = Morphology({
            "комната": (MorphInfo("комната", "NOUN", case="nomn", score=1.0),),
            "в": (
                MorphInfo("в", "PREP", score=0.999),
                MorphInfo("в", "NOUN", case="nomn", score=0.001),
            ),
        })
        parser = make_parser(morphology=morph)
        text = "Комната, где я живу"
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        parent_clause = parser._candidate_graph.clauses[0]
        spans = parser._raw_nominal_spans(
            text, tokens, parent_clause.span.start_index, parent_clause.span.end_index
        )
        self.assertEqual([span.text for span in spans], ["Комната"])

    def test_preposition_governed_relative_uses_generic_role_cue_with_full_pp(self):
        backend = ScriptedBackend({"perception_role_cue": ["PLACE"]})
        parser = make_parser(backend=backend)
        child = AssertionCandidate("A1", PredicateCandidate("вошёл", "войти"), (
            ActantCandidate(ActantRole.SUBJECT, mention="Пётр"),
        ))
        relative = _Span(3, 4, "в которую", EvidenceSpan("в которую", 9, 17))
        antecedent = _Span(1, 1, "Комната", EvidenceSpan("Комната", 0, 7))
        role = parser._choose_relative_role(
            "Комната, в которую вошёл Пётр", child, relative, antecedent, {ActantRole.SUBJECT}
        )
        self.assertEqual(role, ActantRole.LOCATION)
        self.assertIn("в которую", backend.calls[0][1])


class CompositionAndNormalization1258Tests(unittest.TestCase):
    def test_numeric_amount_fuses_only_into_semantically_resolved_duration(self):
        text = "Мария ждала два часа."
        amount = ActantCandidate(ActantRole.AMOUNT, mention="два", evidence=EvidenceSpan("два", 12, 15))
        duration = ActantCandidate(ActantRole.DURATION, mention="часа", normalized_hint="час", evidence=EvidenceSpan("часа", 16, 20))
        obj = ActantCandidate(ActantRole.OBJECT, mention="книги", normalized_hint="книга", evidence=EvidenceSpan("книги", 16, 21))
        fused = AdaptivePerceptionParser._fuse_quantified_duration_actants(text, [amount, duration])
        self.assertEqual([(x.role, x.mention) for x in fused], [(ActantRole.DURATION, "два часа")])
        untouched = AdaptivePerceptionParser._fuse_quantified_duration_actants(text, [amount, obj])
        self.assertEqual([(x.role, x.mention) for x in untouched], [(ActantRole.AMOUNT, "два"), (ActantRole.OBJECT, "книги")])

    def test_lexeme_ambiguity_uses_mirrored_comparative_ab_probes(self):
        backend = ScriptedBackend({"perception_lexeme_comparison": ["B", "A"]})
        parser = make_parser(backend=backend, morphology=Morphology({}))
        chosen = parser._resolve_binary_lexeme_hypotheses(
            text="TARGET context",
            target="TARGET",
            candidates=("alpha", "beta"),
            analyses=(
                MorphInfo("alpha", "VERB", number="sing", score=0.7),
                MorphInfo("beta", "VERB", number="sing", score=0.3),
            ),
            predicate_surface="TARGET",
        )
        self.assertEqual(chosen, "beta")
        self.assertEqual([c[0] for c in backend.calls], ["perception_lexeme_comparison"] * 2)
        self.assertIn("A LEMMA:\nalpha", backend.calls[0][1])
        self.assertIn("B LEMMA:\nbeta", backend.calls[0][1])
        self.assertIn("A LEMMA:\nbeta", backend.calls[1][1])
        self.assertIn("B LEMMA:\nalpha", backend.calls[1][1])

    def test_lexeme_position_bias_uses_literal_bounded_fallback(self):
        backend = ScriptedBackend({
            "perception_lexeme_comparison": ["B", "B"],
            "perception_lexeme_identity": ["beta"],
        })
        parser = make_parser(backend=backend, morphology=Morphology({}))
        chosen = parser._resolve_binary_lexeme_hypotheses(
            text="TARGET context",
            target="TARGET",
            candidates=("alpha", "beta"),
            analyses=(
                MorphInfo("alpha", "VERB", score=0.7),
                MorphInfo("beta", "VERB", score=0.3),
            ),
            predicate_surface="TARGET",
        )
        self.assertEqual(chosen, "beta")
        self.assertEqual(backend.calls[-1][0], "perception_lexeme_identity")
        self.assertNotIn("A LEMMA", backend.calls[-1][1])
        self.assertNotIn("B LEMMA", backend.calls[-1][1])

    def test_lexeme_hypotheses_fail_closed_when_literal_fallback_is_out_of_set(self):
        for answers in (("A", "A"), ("B", "B")):
            backend = ScriptedBackend({
                "perception_lexeme_comparison": list(answers),
                "perception_lexeme_identity": ["gamma", "gamma"],
            })
            parser = make_parser(backend=backend, morphology=Morphology({}))
            with self.assertRaises(AdaptiveParseError):
                parser._resolve_binary_lexeme_hypotheses(
                    text="TARGET context",
                    target="TARGET",
                    candidates=("alpha", "beta"),
                    analyses=(
                        MorphInfo("alpha", "VERB", score=0.7),
                        MorphInfo("beta", "VERB", score=0.3),
                    ),
                    predicate_surface="TARGET",
                )


class AnaphoricSubstantive1258Tests(unittest.TestCase):
    def test_substantivized_anaphor_is_nominal_subject_and_uses_local_source_choice(self):
        morph = Morphology({
            "сергей": (MorphInfo("сергей", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),),
            "дал": (MorphInfo("дать", "VERB", number="sing", gender="masc", mood="indc", transitivity="tran", grammemes=frozenset({"past", "tran"}), score=1.0),),
            "петру": (MorphInfo("пётр", "NOUN", case="datv", number="sing", gender="masc", animacy="anim", score=1.0),),
            "ключ": (MorphInfo("ключ", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=1.0),),
            "и": (MorphInfo("и", "CONJ", score=1.0),),
            "тот": (
                MorphInfo("тот", "ADJF", case="nomn", number="sing", gender="masc", grammemes=frozenset({"Anph", "Apro", "Subx"}), score=0.64),
                MorphInfo("тот", "ADJF", case="accs", number="sing", gender="masc", animacy="inan", grammemes=frozenset({"Anph", "Apro", "Subx"}), score=0.36),
            ),
            "открыл": (MorphInfo("открыть", "VERB", number="sing", gender="masc", mood="indc", transitivity="tran", grammemes=frozenset({"past", "tran"}), score=1.0),),
            "дверь": (MorphInfo("дверь", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
        })
        backend = ScriptedBackend({"perception_antecedent_choice": ["C2"]})
        parser = make_parser(backend=backend, morphology=morph)
        text = "Сергей дал Петру ключ, и тот открыл дверь."
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
        pred2 = parser._resolve_span(text, tokens, 8, 8)
        subject = parser._deterministic_subject_span(tokens, pred2, None)
        self.assertIsNotNone(subject)
        self.assertEqual(subject.text, "тот")

        by_id = {
            "A1": AssertionCandidate(
                "A1", PredicateCandidate("дал", "дать"),
                (
                    ActantCandidate(ActantRole.SUBJECT, mention="Сергей", normalized_hint="Сергей", entity_ref="E1", evidence=EvidenceSpan("Сергей", 0, 6)),
                    ActantCandidate(ActantRole.RECIPIENT, mention="Петру", normalized_hint="Пётр", entity_ref="E2", evidence=EvidenceSpan("Петру", 11, 16)),
                    ActantCandidate(ActantRole.OBJECT, mention="ключ", normalized_hint="ключ", entity_ref="E3", evidence=EvidenceSpan("ключ", 17, 21)),
                ),
                evidence=EvidenceSpan("Сергей дал Петру ключ", 0, 21),
            ),
            "A2": AssertionCandidate(
                "A2", PredicateCandidate("открыл", "открыть", evidence=EvidenceSpan("открыл", 29, 35)),
                (
                    ActantCandidate(ActantRole.SUBJECT, mention="тот", evidence=EvidenceSpan("тот", 25, 28)),
                    ActantCandidate(ActantRole.OBJECT, mention="дверь", normalized_hint="дверь", evidence=EvidenceSpan("дверь", 36, 41)),
                ),
                evidence=EvidenceSpan("тот открыл дверь", 25, 41),
            ),
        }
        parser._resolve_pronoun_coreferences(by_id)
        resolved = next(a for a in by_id["A2"].actants if a.role is ActantRole.SUBJECT)
        self.assertEqual(resolved.entity_ref, "E2")
        self.assertEqual(backend.calls[0][0], "perception_antecedent_choice")
        self.assertNotIn("E2", backend.calls[0][1])


class ConditionalAndDomain1258Tests(unittest.TestCase):
    def test_fronted_condition_absorbs_additive_top_level_consequent_sibling(self):
        morph = Morphology({
            "если": (MorphInfo("если", "CONJ", score=1.0),),
            "иван": (MorphInfo("иван", "NOUN", case="nomn", score=1.0),),
            "откроет": (MorphInfo("открыть", "VERB", number="sing", mood="indc", score=1.0),),
            "дверь": (MorphInfo("дверь", "NOUN", case="accs", score=1.0),),
            "мария": (MorphInfo("мария", "NOUN", case="nomn", score=1.0),),
            "войдёт": (MorphInfo("войти", "VERB", number="sing", mood="indc", score=1.0),),
            "и": (MorphInfo("и", "CONJ", score=1.0),),
            "пётр": (MorphInfo("пётр", "NOUN", case="nomn", score=1.0),),
            "выйдет": (MorphInfo("выйти", "VERB", number="sing", mood="indc", score=1.0),),
        })
        parser = make_parser(morphology=morph)
        text = "Если Иван откроет дверь, Мария войдёт и Пётр выйдет."
        tokens = parser._source_tokens(text)
        parser._candidate_graph = LinguisticCandidateBuilder(parser.morphology).build(text)
        assertions = [
            AssertionCandidate("A1", PredicateCandidate("откроет", "открыть"), ()),
            AssertionCandidate("A2", PredicateCandidate("войдёт", "войти"), ()),
            AssertionCandidate("A3", PredicateCandidate("выйдет", "выйти"), ()),
        ]
        spans = {
            "A1": parser._resolve_span(text, tokens, 3, 3),
            "A2": parser._resolve_span(text, tokens, 7, 7),
            "A3": parser._resolve_span(text, tokens, 10, 10),
        }
        conditionals = parser._derive_conditionals(assertions, spans)
        self.assertEqual(len(conditionals), 1)
        self.assertEqual(conditionals[0].antecedent_refs, ("A1",))
        self.assertEqual(conditionals[0].consequent_refs, ("A2", "A3"))

    def test_personalized_parent_propagates_domain_to_nested_candidate_ref(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        self_entity = core.add_entity(Domain.P, properties={"name": Property("name", "АГент", "str")}, uid="M_SELF")
        user_entity = core.add_entity(Domain.P, properties={"name": Property("name", "Пользователь", "str")}, uid="M_USER")
        context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
        service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2, 0.18))
        child = AssertionCandidate(
            "A2",
            PredicateCandidate("открыть", "открыть", template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT))),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Сергей"),
                ActantCandidate(ActantRole.OBJECT, mention="дверь"),
            ),
        )
        parent = AssertionCandidate(
            "A1",
            PredicateCandidate("попросить", "попросить", template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.RECIPIENT, ActantRole.OBJECT))),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Я"),
                ActantCandidate(ActantRole.RECIPIENT, mention="Сергей"),
                ActantCandidate(ActantRole.OBJECT, candidate_ref="A2"),
            ),
        )
        commit = service.integrate_external(PerceptionResult(source_text="Я попросил Сергея открыть дверь.", assertions=(parent, child)), context)
        domains = {item.local_id: item.domain for item in commit.assertions}
        self.assertEqual(domains, {"A2": Domain.P, "A1": Domain.P})

    def test_nonpersonal_parent_does_not_propagate_p_domain_to_nested_candidate_ref(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        self_entity = core.add_entity(Domain.P, properties={"name": Property("name", "АГент", "str")}, uid="M_SELF")
        user_entity = core.add_entity(Domain.P, properties={"name": Property("name", "Пользователь", "str")}, uid="M_USER")
        context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
        service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2, 0.18))
        child = AssertionCandidate(
            "A2",
            PredicateCandidate("открыть", "открыть", template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT))),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Сергей"),
                ActantCandidate(ActantRole.OBJECT, mention="дверь"),
            ),
        )
        parent = AssertionCandidate(
            "A1",
            PredicateCandidate("попросить", "попросить", template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.RECIPIENT, ActantRole.OBJECT))),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Мария"),
                ActantCandidate(ActantRole.RECIPIENT, mention="Сергей"),
                ActantCandidate(ActantRole.OBJECT, candidate_ref="A2"),
            ),
        )
        commit = service.integrate_external(PerceptionResult(source_text="Мария попросила Сергея открыть дверь.", assertions=(parent, child)), context)
        domains = {item.local_id: item.domain for item in commit.assertions}
        self.assertEqual(domains, {"A2": Domain.C, "A1": Domain.C})


class Oracle1258Tests(unittest.TestCase):
    def test_broad_oracle_v3_preserves_adverbial_denotations_without_touching_frozen40(self):
        broad = json.loads((PROJECT / "data/acceptance_oracle.json").read_text(encoding="utf-8"))
        frozen = json.loads((PROJECT / "data/acceptance_oracle_regression40.json").read_text(encoding="utf-8"))
        self.assertEqual(broad["corpus_id"], "broad200-v3")
        self.assertEqual([x["expect"] for x in broad["cases"][:40]], [x["expect"] for x in frozen["cases"]])
        self.assertEqual(broad["cases"][66]["expect"]["perception"]["assertions"][0]["roles"]["TIME"], "утром")
        self.assertEqual(broad["cases"][136]["expect"]["perception"]["assertions"][1]["roles"]["LOCATION"], "домой")
        self.assertEqual(broad["cases"][167]["expect"]["integration"]["query_outcomes"][0]["value"], "утром")


if __name__ == "__main__":
    unittest.main()
