from __future__ import annotations

import unittest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.entity_resolver import AmbiguousEntityPlan, EntityResolver, EquivalentLiteralPlan
from ah.model import ActantRole, Domain, Property
from ah.perception import ActantCandidate, AssertionCandidate, PerceptionResult, PredicateCandidate, TemplateCandidate


class LiteralIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.user = self.core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
        self.self_entity = self.core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")})
        self.context = InteractionContext(user_ref=self.core.ref(self.user.uid), self_ref=self.core.ref(self.self_entity.uid))
        self.service = IntegrationService(self.core, IntegrationConfig(0.4, 0.3, 0.2))

    def _amount_assertion(self, mention: str) -> PerceptionResult:
        return PerceptionResult(
            source_text=f"Цена {mention}",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "стоить",
                        "стоить",
                        template_candidate=TemplateCandidate((ActantRole.AMOUNT,)),
                    ),
                    (ActantCandidate(ActantRole.AMOUNT, mention=mention),),
                ),
            ),
        )

    def test_duplicate_bare_numeric_entities_are_equivalent_not_ambiguous(self) -> None:
        self.core.add_entity(Domain.C, {"name": Property("name", "5", "str")})
        self.core.add_entity(Domain.P, {"name": Property("name", "5", "str")})

        resolution = EntityResolver(self.core).resolve(
            ActantCandidate(ActantRole.AMOUNT, mention="5"), self.context
        )

        self.assertIsInstance(resolution, EquivalentLiteralPlan)
        self.assertEqual(resolution.literal_kind, "NUMBER")
        self.assertEqual(resolution.literal_value, "5")

    def test_integration_collapses_numeric_duplicates_and_never_asks_user_to_choose(self) -> None:
        first = self.core.add_entity(Domain.C, {"name": Property("name", "5", "str")})
        second = self.core.add_entity(Domain.P, {"name": Property("name", "5", "str")})

        commit = self.service.integrate_external(self._amount_assertion("5"), self.context)

        self.assertFalse(commit.clarification_required)
        self.assertEqual(commit.clarifications, ())
        matches = [
            element
            for domain in Domain
            for element in self.core.store.find_entities_by_name("5", domain)
        ]
        self.assertEqual(len(matches), 1)
        literal = matches[0]
        self.assertEqual(self.core.store.domain_of(literal.uid), Domain.C)
        self.assertEqual(literal.meta.get("literal_kind"), "NUMBER")
        self.assertEqual(literal.meta.get("literal_value"), "5")
        self.assertTrue(self.core.store.has_uid(first.uid))
        self.assertFalse(self.core.store.has_uid(second.uid))

    def test_decimal_spellings_share_one_literal_identity(self) -> None:
        self.service.integrate_external(self._amount_assertion("5.0"), self.context)
        self.service.integrate_external(self._amount_assertion("5,00"), self.context)

        numeric = [
            element
            for domain in Domain
            for element in self.core.store.elements(domain)
            if getattr(element, "meta", {}).get("literal_kind") == "NUMBER" and getattr(element, "meta", {}).get("literal_value") == "5"
        ]
        self.assertEqual(len(numeric), 1)

    def test_same_surface_named_objects_remain_genuinely_ambiguous(self) -> None:
        self.core.add_entity(Domain.C, {
            "name": Property("name", "Пять", "str"),
            "serial": Property("serial", "A", "str"),
        })
        self.core.add_entity(Domain.C, {
            "name": Property("name", "Пять", "str"),
            "serial": Property("serial", "B", "str"),
        })

        resolution = EntityResolver(self.core).resolve(
            ActantCandidate(ActantRole.OBJECT, mention="Пять"), self.context
        )
        self.assertIsInstance(resolution, AmbiguousEntityPlan)


if __name__ == "__main__":
    unittest.main()

from ah.inference import SemanticGoalCompiler, QueryGoalBuilder
from ah.perception import ActRelationCandidate, QueryCandidate, QueryMode


def _direct_query(local_id: str, subject: str, state: str) -> QueryCandidate:
    return QueryCandidate(
        predicate=PredicateCandidate(
            "это",
            "be",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        ),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention=subject),
            ActantCandidate(ActantRole.STATE, mention=state),
        ),
        requested_roles=(),
        query_mode=QueryMode.EXISTS,
        local_id=local_id,
    )


def test_direct_query_repairs_existing_numeric_literal_collision_before_goal_build():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    core.add_entity(Domain.C, {"name": Property("name", "5", "str")})
    core.add_entity(Domain.P, {"name": Property("name", "5", "str")})
    query = QueryCandidate(
        predicate=PredicateCandidate(
            "купить",
            "купить",
            template_candidate=TemplateCandidate((ActantRole.AMOUNT,)),
        ),
        actants=(ActantCandidate(ActantRole.AMOUNT, mention="5"),),
        requested_roles=(),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    perception = PerceptionResult(source_text="Что можно купить на 5 златых?", queries=(query,))

    commit = service.integrate_external(perception, context)
    build = QueryGoalBuilder(core).build(commit.unresolved_queries[0], context)

    assert build.goal is not None
    matches = [
        entity
        for domain in Domain
        for entity in core.store.find_entities_by_name("5", domain)
    ]
    assert len(matches) == 1
    assert matches[0].meta.get("literal_value") == "5"


def test_relation_endpoint_uses_single_active_same_name_referent_without_guessing():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    generic = core.add_entity(Domain.C, {"name": Property("name", "Крипл", "str")})
    personal = core.add_entity(Domain.P, {"name": Property("name", "Крипл", "str")})
    ai = core.add_entity(Domain.C, {"name": Property("name", "ИИ", "str")})
    query = _direct_query("Q1", "Крипл", "ИИ")
    perception = PerceptionResult(
        source_text="Крипл - это ИИ?",
        queries=(query,),
        act_relations=(
            ActRelationCandidate("IS-A", "Q1", ActantRole.SUBJECT, ActantRole.STATE),
        ),
    )
    commit = service.integrate_external(perception, context)
    compiler = SemanticGoalCompiler(core, QueryGoalBuilder(core))

    unresolved = compiler.build(commit, context, perception)
    assert unresolved[0].goal is None
    assert unresolved[0].diagnostics == ("semantic:relation_endpoint_ambiguous:SUBJECT:2",)

    resolved = compiler.build(
        commit,
        context,
        perception,
        attention_refs=(core.ref(personal.uid),),
    )
    assert resolved[0].goal is not None
    target = resolved[0].goal.goal.target
    assert target.source == core.ref(personal.uid)
    assert target.target == core.ref(ai.uid)
    assert target.source != core.ref(generic.uid)


def test_literal_collapse_rewrites_existing_fact_incidence_instead_of_losing_memory():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    canonical = core.add_entity(Domain.C, {"name": Property("name", "5", "str")})
    duplicate = core.add_entity(Domain.P, {"name": Property("name", "5", "str")})
    sword = core.add_entity(Domain.C, {"name": Property("name", "меч", "str")})
    symbol = core.add_abstract_symbol({"стоить"})
    template = core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.OBJECT, ActantRole.AMOUNT)
    )
    fact, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.OBJECT: core.ref(sword.uid), ActantRole.AMOUNT: core.ref(duplicate.uid)},
        0.4,
    )

    service.integrate_external(
        PerceptionResult(
            source_text="Цена 5",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "стоить", "стоить",
                        template_candidate=TemplateCandidate((ActantRole.AMOUNT,)),
                    ),
                    (ActantCandidate(ActantRole.AMOUNT, mention="5"),),
                ),
            ),
        ),
        context,
    )

    assert not core.store.has_uid(duplicate.uid)
    rewritten = core.store.get_hypernode(fact.uid)
    assert rewritten.actants[ActantRole.AMOUNT] == core.ref(canonical.uid)


def test_literal_collapse_removes_stale_ambiguous_group_when_it_becomes_singleton():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")})
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    first = core.add_entity(Domain.C, {"name": Property("name", "5", "str")})
    second = core.add_entity(Domain.P, {"name": Property("name", "5", "str")})
    group = core.add_group(
        Domain.C,
        (core.ref(first.uid), core.ref(second.uid)),
        meta={"TYPE": "AMBIGUOUS_REFERENCE", "mention": "5"},
    )
    context.pending_clarification_refs.append(core.ref(group.uid))

    service.integrate_external(
        PerceptionResult(
            source_text="Цена 5",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "стоить", "стоить",
                        template_candidate=TemplateCandidate((ActantRole.AMOUNT,)),
                    ),
                    (ActantCandidate(ActantRole.AMOUNT, mention="5"),),
                ),
            ),
        ),
        context,
    )

    assert not core.store.has_uid(second.uid)
    assert not core.store.has_uid(group.uid)
