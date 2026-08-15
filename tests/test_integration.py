from __future__ import annotations

import unittest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import CandidateValidationError, IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Hypernode, Property, RefKind
from ah.perception import (
    ActantCandidate,
    ActantCompositionCandidate,
    CompositionMemberCandidate,
    CompositionOperator,
    AssertionCandidate,
    AssertionStatus,
    ConditionalCandidate,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
    SituationRelationCandidate,
)


class IntegrationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.self_entity = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Агент", "str")},
            uid="M_SELF",
        )
        self.user_entity = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Пользователь", "str")},
            uid="M_USER",
        )
        self.context = InteractionContext(
            self_ref=self.core.ref(self.self_entity.uid),
            user_ref=self.core.ref(self.user_entity.uid),
        )
        self.service = IntegrationService(
            self.core,
            IntegrationConfig(
                initial_hypernode_weight=0.4,
                experience_hypernode_weight=0.3,
                follow_link_weight=0.2,
                cause_link_weight=0.18,
            ),
        )

    def _assertion(self, local_id: str, predicate: str, *actants: ActantCandidate):
        roles = tuple(dict.fromkeys(actant.role for actant in actants))
        return AssertionCandidate(
            local_id=local_id,
            predicate=PredicateCandidate(
                predicate,
                predicate,
                template_candidate=TemplateCandidate(roles),
            ),
            actants=tuple(actants),
        )

    def test_external_general_fact_goes_to_c_and_creates_h_experience(self) -> None:
        result = PerceptionResult(
            source_text="Яблоко имеет цвет красный",
            assertions=(
                self._assertion(
                    "A1",
                    "иметь цвет",
                    ActantCandidate(ActantRole.SUBJECT, mention="яблоко"),
                    ActantCandidate(ActantRole.STATE, mention="красный"),
                ),
            ),
        )

        commit = self.service.integrate_external(result, self.context)

        self.assertEqual(commit.assertions[0].domain, Domain.C)
        self.assertEqual(self.core.store.domain_of(commit.assertions[0].ref.uid), Domain.C)
        self.assertEqual(self.core.store.domain_of(commit.experience_ref.uid), Domain.H)
        self.assertEqual(self.context.last_experience_ref, commit.experience_ref)
        self.assertEqual(len(commit.activation_seeds), 2)

    def test_external_fact_with_known_p_entity_routes_to_p(self) -> None:
        masha = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Маша", "str")},
        )
        result = PerceptionResult(
            source_text="Маша читает книгу",
            assertions=(
                self._assertion(
                    "A1",
                    "читать",
                    ActantCandidate(ActantRole.SUBJECT, mention="Маша"),
                    ActantCandidate(ActantRole.OBJECT, mention="книга"),
                ),
            ),
        )

        commit = self.service.integrate_external(result, self.context)
        node = self.core.store.get_hypernode(commit.assertions[0].ref.uid)

        self.assertEqual(commit.assertions[0].domain, Domain.P)
        self.assertEqual(node.actants[ActantRole.SUBJECT].uid, masha.uid)
        book_ref = node.actants[ActantRole.OBJECT]
        self.assertEqual(self.core.store.domain_of(book_ref.uid), Domain.P)

    def test_duplicate_semantic_fact_reuses_n_but_each_turn_gets_new_h_event_and_follow(self) -> None:
        result = PerceptionResult(
            source_text="Кошка спит",
            assertions=(
                self._assertion(
                    "A1",
                    "спать",
                    ActantCandidate(ActantRole.SUBJECT, mention="кошка"),
                ),
            ),
        )

        first = self.service.integrate_external(result, self.context)
        second = self.service.integrate_external(result, self.context)

        self.assertEqual(first.assertions[0].ref.uid, second.assertions[0].ref.uid)
        self.assertFalse(second.assertions[0].created)
        self.assertNotEqual(first.experience_ref.uid, second.experience_ref.uid)
        follow = self.core.store.outgoing_links(first.experience_ref.uid, "FOLLOW")
        self.assertEqual(len(follow), 1)
        self.assertEqual(follow[0].target.uid, second.experience_ref.uid)

        semantic = self.core.store.get_hypernode(second.assertions[0].ref.uid)
        self.assertEqual(semantic.meta["occurrence_count"], 2)
        self.assertEqual(semantic.weight, 0.4)


    def test_explicit_negation_materializes_false_without_confirming_positive_n(self) -> None:
        positive = PerceptionResult(
            source_text="Кошка спит",
            assertions=(
                self._assertion(
                    "A1",
                    "спать",
                    ActantCandidate(ActantRole.SUBJECT, mention="кошка"),
                ),
            ),
        )
        first = self.service.integrate_external(positive, self.context)
        positive_ref = first.assertions[0].ref
        before = self.core.store.get_hypernode(positive_ref.uid)
        self.assertEqual(before.meta["occurrence_count"], 1)

        negated = PerceptionResult(
            source_text="Кошка не спит",
            assertions=(
                AssertionCandidate(
                    local_id="A2",
                    predicate=PredicateCandidate(
                        "спать", "спать",
                        template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                    ),
                    actants=(ActantCandidate(ActantRole.SUBJECT, mention="кошка"),),
                    negated=True,
                ),
            ),
        )
        commit = self.service.integrate_external(negated, self.context)
        false_ref = commit.assertions[0].ref
        self.assertEqual(false_ref.kind, RefKind.G)
        false_g = self.core.store.get_element_any_domain(false_ref.uid)
        self.assertEqual(false_g.function_id, "FALSE")
        self.assertEqual(false_g.operands, (positive_ref,))
        self.assertEqual(self.core.store.get_hypernode(positive_ref.uid).meta["occurrence_count"], 1)
        self.assertEqual(tuple(r.target.uid for r in commit.refutations), (positive_ref.uid,))

    def test_nested_candidate_ref_becomes_nested_n_actant(self) -> None:
        result = PerceptionResult(
            source_text="Маша переехала в Париж, Иван это сказал",
            assertions=(
                self._assertion(
                    "MOVE",
                    "переехать",
                    ActantCandidate(ActantRole.SUBJECT, mention="Маша"),
                    ActantCandidate(ActantRole.LOCATION, mention="Париж"),
                ),
                self._assertion(
                    "SAY",
                    "сказать",
                    ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                    ActantCandidate(ActantRole.OBJECT, candidate_ref="MOVE"),
                ),
            ),
        )

        commit = self.service.integrate_external(result, self.context)
        by_id = {a.local_id: a for a in commit.assertions}
        say = self.core.store.get_hypernode(by_id["SAY"].ref.uid)

        self.assertEqual(say.actants[ActantRole.OBJECT].kind, RefKind.N)
        self.assertEqual(say.actants[ActantRole.OBJECT].uid, by_id["MOVE"].ref.uid)

    def test_ambiguity_is_reified_as_k_and_requests_clarification(self) -> None:
        self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Иван", "str")},
        )
        self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Иван", "str")},
        )
        result = PerceptionResult(
            source_text="Иван спит",
            assertions=(
                self._assertion(
                    "A1",
                    "спать",
                    ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                ),
            ),
        )

        commit = self.service.integrate_external(result, self.context)
        node = self.core.store.get_hypernode(commit.assertions[0].ref.uid)
        subject = self.core.store.get_element_any_domain(node.actants[ActantRole.SUBJECT].uid)

        self.assertTrue(commit.clarification_required)
        self.assertEqual(node.actants[ActantRole.SUBJECT].kind, RefKind.K)
        self.assertEqual(subject.meta["TYPE"], "AMBIGUOUS_REFERENCE")

    def test_agent_response_integrates_semantics_to_h_only(self) -> None:
        result = PerceptionResult(
            source_text="Я вижу единорога",
            assertions=(
                self._assertion(
                    "A1",
                    "видеть",
                    ActantCandidate(ActantRole.SUBJECT, mention="я"),
                    ActantCandidate(ActantRole.OBJECT, mention="единорог"),
                ),
            ),
        )

        commit = self.service.integrate_to_h(result, self.context)
        node = self.core.store.get_hypernode(commit.assertions[0].ref.uid)

        self.assertEqual(commit.assertions[0].domain, Domain.H)
        self.assertEqual(node.actants[ActantRole.SUBJECT].uid, self.self_entity.uid)
        unicorn = node.actants[ActantRole.OBJECT]
        self.assertEqual(self.core.store.domain_of(unicorn.uid), Domain.H)
        self.assertFalse(any(
            isinstance(e, Hypernode) and e.uid == commit.assertions[0].ref.uid
            for e in self.core.store.elements(Domain.C)
        ))
        self.assertFalse(any(
            isinstance(e, Hypernode) and e.uid == commit.assertions[0].ref.uid
            for e in self.core.store.elements(Domain.P)
        ))

    def test_user_first_person_resolves_to_user_and_routes_p(self) -> None:
        result = PerceptionResult(
            source_text="Я люблю чай",
            assertions=(
                self._assertion(
                    "A1",
                    "любить",
                    ActantCandidate(ActantRole.SUBJECT, mention="я"),
                    ActantCandidate(ActantRole.OBJECT, mention="чай"),
                ),
            ),
        )

        commit = self.service.integrate_external(result, self.context)
        node = self.core.store.get_hypernode(commit.assertions[0].ref.uid)

        self.assertEqual(commit.assertions[0].domain, Domain.P)
        self.assertEqual(node.actants[ActantRole.SUBJECT].uid, self.user_entity.uid)

    def test_invalid_candidate_dependency_rolls_back_everything(self) -> None:
        before_c = len(self.core.store.elements(Domain.C))
        before_h = len(self.core.store.elements(Domain.H))
        result = PerceptionResult(
            source_text="сломанный кандидат",
            assertions=(
                self._assertion(
                    "A1",
                    "сказать",
                    ActantCandidate(ActantRole.OBJECT, candidate_ref="MISSING"),
                ),
            ),
        )

        with self.assertRaises(CandidateValidationError):
            self.service.integrate_external(result, self.context)

        self.assertEqual(len(self.core.store.elements(Domain.C)), before_c)
        self.assertEqual(len(self.core.store.elements(Domain.H)), before_h)
        self.assertIsNone(self.context.last_experience_ref)

    def test_local_entity_coreference_reuses_exact_same_m_and_follow_relation_becomes_l(self) -> None:
        result = PerceptionResult(
            source_text="Я прочитал текст, который Лиза написала позже",
            assertions=(
                self._assertion(
                    "A1",
                    "read",
                    ActantCandidate(ActantRole.SUBJECT, mention="я"),
                    ActantCandidate(ActantRole.OBJECT, mention="текст", entity_ref="E1"),
                ),
                self._assertion(
                    "A2",
                    "write",
                    ActantCandidate(ActantRole.SUBJECT, mention="Лиза"),
                    ActantCandidate(ActantRole.OBJECT, mention="текст", entity_ref="E1"),
                ),
            ),
            relations=(
                SituationRelationCandidate("FOLLOW", "A1", "A2"),
            ),
        )

        commit = self.service.integrate_external(result, self.context)
        by_id = {item.local_id: item for item in commit.assertions}
        first = self.core.store.get_hypernode(by_id["A1"].ref.uid)
        second = self.core.store.get_hypernode(by_id["A2"].ref.uid)
        self.assertEqual(first.actants[ActantRole.OBJECT], second.actants[ActantRole.OBJECT])

        self.assertEqual(len(commit.relations), 1)
        relation = commit.relations[0]
        self.assertEqual(relation.relation_id, "FOLLOW")
        self.assertEqual(relation.source.uid, by_id["A1"].ref.uid)
        self.assertEqual(relation.target.uid, by_id["A2"].ref.uid)
        stored = self.core.store.find_link("FOLLOW", relation.source.uid, relation.target.uid)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.uid, relation.ref.uid)

    def test_cause_situation_relation_materializes_canonical_cause_link(self) -> None:
        result = PerceptionResult(
            source_text="Лиза написала текст потому, что получила советы",
            assertions=(
                self._assertion(
                    "A1",
                    "write",
                    ActantCandidate(ActantRole.SUBJECT, mention="Лиза"),
                    ActantCandidate(ActantRole.OBJECT, mention="текст"),
                    ActantCandidate(ActantRole.CAUSE, candidate_ref="A2"),
                ),
                self._assertion(
                    "A2",
                    "receive",
                    ActantCandidate(ActantRole.SUBJECT, mention="Лиза"),
                    ActantCandidate(ActantRole.OBJECT, mention="советы"),
                ),
            ),
            relations=(SituationRelationCandidate("CAUSE", "A2", "A1"),),
        )

        commit = self.service.integrate_external(result, self.context)
        by_id = {item.local_id: item for item in commit.assertions}
        self.assertEqual(len(commit.relations), 1)
        relation = commit.relations[0]
        self.assertEqual(relation.relation_id, "CAUSE")
        self.assertEqual(relation.source.uid, by_id["A2"].ref.uid)
        self.assertEqual(relation.target.uid, by_id["A1"].ref.uid)
        stored = self.core.store.find_link("CAUSE", relation.source.uid, relation.target.uid)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.uid, relation.ref.uid)
        self.assertAlmostEqual(stored.weight, 0.18)



    def test_conditional_components_are_not_committed_as_world_facts(self) -> None:
        before_c_n = sum(isinstance(e, Hypernode) for e in self.core.store.elements(Domain.C))
        before_p_n = sum(isinstance(e, Hypernode) for e in self.core.store.elements(Domain.P))
        before_c_m = sum(e.__class__.__name__ == "SemanticEntity" for e in self.core.store.elements(Domain.C))
        before_p_m = sum(e.__class__.__name__ == "SemanticEntity" for e in self.core.store.elements(Domain.P))
        result = PerceptionResult(
            source_text="Если Лиза получит советы, она напишет текст.",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate("получит", "receive"),
                    (
                        ActantCandidate(ActantRole.SUBJECT, mention="Лиза", entity_ref="E1"),
                        ActantCandidate(ActantRole.OBJECT, mention="советы"),
                    ),
                    status=AssertionStatus.CONDITIONAL,
                ),
                AssertionCandidate(
                    "A2",
                    PredicateCandidate("напишет", "write"),
                    (
                        ActantCandidate(ActantRole.SUBJECT, mention="она", entity_ref="E1"),
                        ActantCandidate(ActantRole.OBJECT, mention="текст"),
                    ),
                    status=AssertionStatus.CONDITIONAL,
                ),
            ),
            conditionals=(ConditionalCandidate(("A1",), ("A2",)),),
        )

        commit = self.service.integrate_external(result, self.context)
        self.assertEqual(commit.assertions, ())
        self.assertEqual(commit.relations, ())
        self.assertEqual(sum(isinstance(e, Hypernode) for e in self.core.store.elements(Domain.C)), before_c_n)
        self.assertEqual(sum(isinstance(e, Hypernode) for e in self.core.store.elements(Domain.P)), before_p_n)
        self.assertEqual(sum(e.__class__.__name__ == "SemanticEntity" for e in self.core.store.elements(Domain.C)), before_c_m)
        self.assertEqual(sum(e.__class__.__name__ == "SemanticEntity" for e in self.core.store.elements(Domain.P)), before_p_m)
        self.assertEqual(self.core.store.domain_of(commit.experience_ref.uid), Domain.H)
        self.assertEqual(len(commit.activation_seeds), 1)

    def test_actant_coordination_materializes_canonical_or_function(self) -> None:
        result = PerceptionResult(
            source_text="Яблоки бывают зелёные или красные",
            assertions=(
                self._assertion(
                    "A1",
                    "be",
                    ActantCandidate(ActantRole.SUBJECT, mention="Яблоки"),
                    ActantCandidate(
                        ActantRole.STATE,
                        mention="зелёные или красные",
                        composition=ActantCompositionCandidate(
                            CompositionOperator.OR,
                            (
                                CompositionMemberCandidate("зелёные"),
                                CompositionMemberCandidate("красные"),
                            ),
                        ),
                    ),
                ),
            ),
        )
        commit = self.service.integrate_external(result, self.context)
        function = self.core.store.get_element_any_domain(commit.assertions[0].ref.uid)
        self.assertEqual(function.function_id, "OR")
        self.assertEqual(len(function.operands), 2)
        states = set()
        subjects = set()
        for ref in function.operands:
            node = self.core.store.get_hypernode(ref.uid)
            subjects.add(self.core.store.get_element_any_domain(node.actants[ActantRole.SUBJECT].uid).properties["name"].value)
            states.add(self.core.store.get_element_any_domain(node.actants[ActantRole.STATE].uid).properties["name"].value)
        self.assertEqual(subjects, {"Яблоки"})
        self.assertEqual(states, {"зелёные", "красные"})



if __name__ == "__main__":
    unittest.main()

class TemplateBoundaryTests(unittest.TestCase):
    def test_unknown_template_cannot_be_created_without_template_candidate(self) -> None:
        from ah.integration import TemplateResolutionError
        from ah.integration.template_resolver import TemplateResolver

        core = AHCore(uid_generator=SequentialUidGenerator())
        with self.assertRaises(TemplateResolutionError):
            TemplateResolver(core, Domain.C).resolve(
                PredicateCandidate("читает", "read"),
                (ActantRole.SUBJECT, ActantRole.OBJECT),
            )
        self.assertIsNone(core.store.find_symbol_by_form("read"))

    def test_template_schema_is_separate_from_concrete_n_filling(self) -> None:
        from ah.integration.template_resolver import TemplateResolver

        core = AHCore(uid_generator=SequentialUidGenerator())
        predicate = PredicateCandidate(
            "читает",
            "read",
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME)
            ),
        )
        resolution = TemplateResolver(core, Domain.C).resolve(
            predicate,
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.assertTrue(resolution.created)
        self.assertEqual(
            resolution.template.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME),
        )

        subject = core.add_entity(Domain.C, properties={"name": Property("name", "Иван", "str")})
        obj = core.add_entity(Domain.C, properties={"name": Property("name", "книга", "str")})
        node, _ = core.add_hypernode(
            Domain.C,
            core.ref(resolution.template.uid),
            {
                ActantRole.SUBJECT: core.ref(subject.uid),
                ActantRole.OBJECT: core.ref(obj.uid),
            },
            weight=0.4,
        )
        self.assertEqual(set(node.actants), {ActantRole.SUBJECT, ActantRole.OBJECT})
        self.assertIn(ActantRole.TIME, resolution.template.roles)

    def test_template_candidate_must_cover_every_filled_role(self) -> None:
        from ah.integration import TemplateResolutionError
        from ah.integration.template_resolver import TemplateResolver

        core = AHCore(uid_generator=SequentialUidGenerator())
        predicate = PredicateCandidate(
            "читает",
            "read",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        )
        with self.assertRaises(TemplateResolutionError):
            TemplateResolver(core, Domain.C).resolve(
                predicate,
                (ActantRole.SUBJECT, ActantRole.OBJECT),
            )

    def test_existing_canonical_template_can_be_reused_without_new_candidate(self) -> None:
        from ah.integration.template_resolver import TemplateResolver

        core = AHCore(uid_generator=SequentialUidGenerator())
        created = TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(
                "читает",
                "read",
                template_candidate=TemplateCandidate(
                    (ActantRole.SUBJECT, ActantRole.OBJECT)
                ),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        reused = TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate("читает", "read"),
            (ActantRole.SUBJECT,),
        )
        self.assertFalse(reused.created)
        self.assertEqual(reused.template.uid, created.template.uid)

    def test_fill_role_query_requires_requested_role_in_canonical_template(self) -> None:
        from ah.inference import QueryGoalBuilder
        from ah.integration.template_resolver import TemplateResolver
        from ah.perception import QueryCandidate, QueryMode

        core = AHCore(uid_generator=SequentialUidGenerator())
        TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(
                "читает",
                "read",
                template_candidate=TemplateCandidate(
                    (ActantRole.SUBJECT, ActantRole.OBJECT)
                ),
            ),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        query = QueryCandidate(
            predicate=PredicateCandidate("читает", "read"),
            actants=(ActantCandidate(ActantRole.SUBJECT, mention="Иван"),),
            requested_role=ActantRole.TIME,
            query_mode=QueryMode.FILL_ROLE,
        )
        built = QueryGoalBuilder(core).build(query, InteractionContext())
        self.assertIsNone(built.goal)
        self.assertEqual(built.diagnostics, ("template_not_unique",))
