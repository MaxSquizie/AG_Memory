from __future__ import annotations

import unittest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    ConditionalCandidate,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    TemplateCandidate,
)


class P0ArchitectureV022Tests(unittest.TestCase):
    def setUp(self):
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        me = self.core.add_entity(Domain.P, properties={"name": Property("name", "Агент", "str")}, uid="M_SELF")
        user = self.core.add_entity(Domain.P, properties={"name": Property("name", "Пользователь", "str")}, uid="M_USER")
        self.context = InteractionContext(self_ref=self.core.ref(me.uid), user_ref=self.core.ref(user.uid))
        self.service = IntegrationService(self.core, IntegrationConfig(0.4, 0.3, 0.2))

    @staticmethod
    def assertion(local_id, pred, roles, *, status=AssertionStatus.ASSERTED, actants=()):
        return AssertionCandidate(
            local_id=local_id,
            predicate=PredicateCandidate(pred, pred, template_candidate=TemplateCandidate(tuple(roles))),
            actants=tuple(actants),
            status=status,
        )

    def test_embedded_content_is_scoped_and_parent_references_it(self):
        buy = self.assertion(
            "BUY", "купить", (ActantRole.SUBJECT, ActantRole.OBJECT),
            status=AssertionStatus.EMBEDDED,
            actants=(
                ActantCandidate(ActantRole.SUBJECT, mention="Мария"),
                ActantCandidate(ActantRole.OBJECT, mention="билет"),
            ),
        )
        want = self.assertion(
            "WANT", "хотеть", (ActantRole.SUBJECT, ActantRole.OBJECT),
            actants=(
                ActantCandidate(ActantRole.SUBJECT, mention="Мария"),
                ActantCandidate(ActantRole.OBJECT, candidate_ref="BUY"),
            ),
        )
        commit = self.service.integrate_external(PerceptionResult("Мария хочет купить билет", assertions=(want, buy)), self.context)
        by_id = {item.local_id: item for item in commit.assertions}
        self.assertEqual(by_id["BUY"].semantic_scope, "EMBEDDED")
        buy_n = self.core.store.get_hypernode(by_id["BUY"].ref.uid)
        self.assertEqual(buy_n.meta.get("semantic_scope"), "EMBEDDED")
        want_n = self.core.store.get_hypernode(by_id["WANT"].ref.uid)
        self.assertEqual(want_n.actants[ActantRole.OBJECT], by_id["BUY"].ref)
        seeded = {seed.ref.uid for seed in commit.activation_seeds}
        self.assertNotIn(by_id["BUY"].ref.uid, seeded)
        self.assertIn(by_id["WANT"].ref.uid, seeded)

    def test_compound_embedded_or_materializes_g_or_as_one_object(self):
        a = self.assertion("A", "прийти", (ActantRole.SUBJECT,), status=AssertionStatus.EMBEDDED,
                           actants=(ActantCandidate(ActantRole.SUBJECT, mention="Иван"),))
        b = self.assertion("B", "позвонить", (ActantRole.SUBJECT,), status=AssertionStatus.EMBEDDED,
                           actants=(ActantCandidate(ActantRole.SUBJECT, mention="Мария"),))
        expr = PropositionExprCandidate(PropositionOperator.OR, members=(
            PropositionExprCandidate.ref_expr("A"), PropositionExprCandidate.ref_expr("B")
        ))
        think = self.assertion("T", "думать", (ActantRole.SUBJECT, ActantRole.OBJECT), actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="Пётр"),
            ActantCandidate(ActantRole.OBJECT, proposition=expr),
        ))
        commit = self.service.integrate_external(PerceptionResult("Пётр думает, что Иван придёт или Мария позвонит", assertions=(think, a, b)), self.context)
        by_id = {item.local_id: item for item in commit.assertions}
        think_n = self.core.store.get_hypernode(by_id["T"].ref.uid)
        object_ref = think_n.actants[ActantRole.OBJECT]
        self.assertEqual(object_ref.kind, RefKind.G)
        g = self.core.store.get_element_any_domain(object_ref.uid)
        self.assertEqual(g.function_id, "OR")
        self.assertEqual(set(g.operands), {by_id["A"].ref, by_id["B"].ref})

    def test_conditional_preserves_or_expression(self):
        a = self.assertion("A", "прийти", (ActantRole.SUBJECT,), status=AssertionStatus.CONDITIONAL,
                           actants=(ActantCandidate(ActantRole.SUBJECT, mention="Иван"),))
        b = self.assertion("B", "позвонить", (ActantRole.SUBJECT,), status=AssertionStatus.CONDITIONAL,
                           actants=(ActantCandidate(ActantRole.SUBJECT, mention="Мария"),))
        c = self.assertion("C", "уйти", (ActantRole.SUBJECT,), status=AssertionStatus.CONDITIONAL,
                           actants=(ActantCandidate(ActantRole.SUBJECT, mention="Пётр"),))
        antecedent = PropositionExprCandidate(PropositionOperator.OR, members=(
            PropositionExprCandidate.ref_expr("A"), PropositionExprCandidate.ref_expr("B")
        ))
        conditional = ConditionalCandidate(
            antecedent_refs=("A", "B"), consequent_refs=("C",),
            antecedent_expr=antecedent,
            consequent_expr=PropositionExprCandidate.ref_expr("C"),
        )
        commit = self.service.integrate_external(PerceptionResult("если A или B, C", assertions=(a,b,c), conditionals=(conditional,)), self.context)
        self.assertEqual(len(commit.conditionals), 1)
        if_g = self.core.store.get_element_any_domain(commit.conditionals[0].ref.uid)
        self.assertEqual(if_g.function_id, "IMPLIES")
        ant = self.core.store.get_element_any_domain(if_g.operands[0].uid)
        self.assertEqual(ant.function_id, "OR")

    def test_overlapping_wordforms_can_belong_to_multiple_symbols(self):
        a = self.core.add_abstract_symbol({"стоит", "стоить"})
        b = self.core.add_abstract_symbol({"стоит", "стоять"})
        matches = self.core.find_abstract_symbols({"стоит"})
        self.assertEqual({item.uid for item in matches}, {a.uid, b.uid})
        with self.assertRaises(ValueError):
            self.core.store.find_symbol_by_form("стоит")


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo


class _Morph:
    name = "test"
    def __init__(self, data): self.data = data
    def analyze_all(self, word): return self.data.get(word.casefold(), ())
    def analyze(self, word):
        values = self.analyze_all(word)
        return values[0] if values else None


class _NoProbeBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected probe {role}\n{prompt}")


class P0ParserBoundaryV022Tests(unittest.TestCase):
    def _settings(self, **kwargs):
        values = dict(
            prompt_dir=Path(__file__).resolve().parents[1] / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        )
        values.update(kwargs)
        return AdaptiveSettings(**values)

    def test_surface_subordinators_do_not_assign_ah_roles(self):
        morph = _Morph({
            "хочу": (MorphInfo("хотеть", "VERB", mood="indc", score=1.0),),
            "пришла": (MorphInfo("прийти", "VERB", mood="indc", score=1.0),),
            "живёт": (MorphInfo("жить", "VERB", mood="indc", score=1.0),),
            "помню": (MorphInfo("помнить", "VERB", mood="indc", score=1.0),),
            "мария": (MorphInfo("мария", "NOUN", case="nomn", score=1.0),),
            "чтобы": (MorphInfo("чтобы", "CONJ", score=1.0),),
            "где": (MorphInfo("где", "ADVB", score=1.0),),
            "когда": (MorphInfo("когда", "ADVB", score=1.0),),
        })
        for text in ("Хочу, чтобы Мария пришла", "Помню, когда Мария пришла", "Хочу, где Мария живёт"):
            graph = LinguisticCandidateBuilder(morph).build(text)
            subordinate = [c for c in graph.clauses if c.parent_clause_id is not None and not c.relative]
            self.assertTrue(subordinate, text)
            self.assertTrue(all(c.parent_role_hint is None for c in subordinate), text)

    def test_act_count_is_source_bounded_not_config_capped(self):
        words = {
            f"действует{i}": f"действовать{i}"
            for i in range(1, 21)
        }
        morph = _Morph({
            word: (MorphInfo(lemma, "VERB", mood="indc", score=1.0),)
            for word, lemma in words.items()
        })
        parser = AdaptivePerceptionParser(
            _NoProbeBackend(), self._settings(), morphology=morph
        )
        result = parser.parse(". ".join(words) + ".")
        self.assertEqual(len(result.perception.assertions), 20)
