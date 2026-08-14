from __future__ import annotations

import unittest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import CandidateValidationError, IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Hypernode, Property, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
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
            ),
        )

    def _assertion(self, local_id: str, predicate: str, *actants: ActantCandidate):
        return AssertionCandidate(
            local_id=local_id,
            predicate=PredicateCandidate(predicate, predicate),
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
                    predicate=PredicateCandidate("спать", "спать"),
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


if __name__ == "__main__":
    unittest.main()
