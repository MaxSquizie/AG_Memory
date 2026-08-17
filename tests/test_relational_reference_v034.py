from __future__ import annotations

from dataclasses import replace
import unittest

from ah.agent import InteractionContext
from ah.config import IgnitionSettings, PacemakerSettings, WorkspaceSettings, ContextSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import QueryGoalBuilder
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.integration.entity_resolver import AmbiguousEntityPlan, EntityResolver, ExistingEntity
from ah.model import ActantRole, Domain, Property
from ah.perception import ActantCandidate, PredicateCandidate, QueryCandidate, QueryMode
from ah.projection import ContextProjector


class RelationalReferenceV034Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.user = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Пользователь", "str")},
            meta={"identity_role": "USER"},
        )
        self.self_entity = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "АГент", "str")},
            meta={"identity_role": "SELF"},
        )
        self.friend = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "друг", "str")},
        )
        self.misha = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Миша", "str")},
        )
        exists_s = self.core.ensure_abstract_symbol("есть")
        self.exists_t = self.core.add_template(
            Domain.P,
            self.core.ref(exists_s.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.AUXILLIARY),
        )
        self.exists_n, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(self.exists_t.uid),
            {
                ActantRole.SUBJECT: self.core.ref(self.user.uid),
                ActantRole.OBJECT: self.core.ref(self.friend.uid),
                ActantRole.AUXILLIARY: self.core.ref(self.misha.uid),
            },
            weight=0.4,
        )
        call_s = self.core.ensure_abstract_symbol("звать")
        self.call_t = self.core.add_template(
            Domain.C,
            self.core.ref(call_s.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        self.context = InteractionContext(
            self_ref=self.core.ref(self.self_entity.uid),
            user_ref=self.core.ref(self.user.uid),
        )

    def friend_candidate(self) -> ActantCandidate:
        return ActantCandidate(
            role=ActantRole.OBJECT,
            mention="моего друга",
            normalized_hint="друг",
        )

    def query(self) -> QueryCandidate:
        return QueryCandidate(
            predicate=PredicateCandidate("зовут", normalized_hint="звать"),
            actants=(self.friend_candidate(),),
            requested_roles=(ActantRole.SUBJECT,),
            query_mode=QueryMode.FILL_ROLE,
        )

    def test_possessive_descriptor_resolves_through_existing_fact_without_merge(self) -> None:
        resolution = EntityResolver(self.core).resolve(
            self.friend_candidate(),
            self.context,
            first_person_ref=self.context.user_ref,
            second_person_ref=self.context.self_ref,
        )
        self.assertIsInstance(resolution, ExistingEntity)
        assert isinstance(resolution, ExistingEntity)
        self.assertEqual(resolution.ref.uid, self.misha.uid)
        self.assertEqual(tuple(ref.uid for ref in resolution.support_refs), (self.exists_n.uid,))

        # Canonical identities remain distinct exactly as USER -> ЕСТЬ(ДРУГ) -> МИША.
        self.assertNotEqual(self.friend.uid, self.misha.uid)
        node = self.core.store.get_hypernode(self.exists_n.uid)
        self.assertEqual(node.actants[ActantRole.OBJECT].uid, self.friend.uid)
        self.assertEqual(node.actants[ActantRole.AUXILLIARY].uid, self.misha.uid)

    def test_multiple_relational_referents_remain_ambiguous(self) -> None:
        petya = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Петя", "str")},
        )
        self.core.add_hypernode(
            Domain.P,
            self.core.ref(self.exists_t.uid),
            {
                ActantRole.SUBJECT: self.core.ref(self.user.uid),
                ActantRole.OBJECT: self.core.ref(self.friend.uid),
                ActantRole.AUXILLIARY: self.core.ref(petya.uid),
            },
            weight=0.4,
            deduplicate=False,
        )
        resolution = EntityResolver(self.core).resolve(
            self.friend_candidate(), self.context,
            first_person_ref=self.context.user_ref,
            second_person_ref=self.context.self_ref,
        )
        self.assertIsInstance(resolution, AmbiguousEntityPlan)
        assert isinstance(resolution, AmbiguousEntityPlan)
        self.assertEqual({ref.uid for ref in resolution.candidates}, {self.misha.uid, petya.uid})

    def test_query_builder_exposes_referent_and_support_fact_as_attention_anchors(self) -> None:
        built = QueryGoalBuilder(self.core).build(self.query(), self.context)
        self.assertIsNotNone(built.goal)
        self.assertEqual(
            tuple(ref.uid for ref in built.attention_refs),
            (self.misha.uid, self.exists_n.uid),
        )

    def test_query_recall_seed_makes_chain_visible_without_creating_zvat_fact(self) -> None:
        settings = replace(IgnitionSettings(), pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(self.core, settings, WorkspaceSettings(threshold=0.35))
        built = QueryGoalBuilder(self.core).build(self.query(), self.context)
        engine.apply_seed_requests(
            tuple(ActivationSeedRequest(ref, SeedReason.QUERY_RECALL) for ref in built.attention_refs)
        )
        engine.tick()
        workspace = engine.workspace_refs()
        ids = {ref.uid for ref in workspace}
        self.assertIn(self.misha.uid, ids)
        self.assertIn(self.exists_n.uid, ids)

        rendered = ContextProjector(
            self.core,
            ContextSettings(include_structural_uids=False),
        ).project("Как зовут моего друга?", workspace, ()).rendered
        self.assertIn("Миша", rendered)
        self.assertIn("друг", rendered)
        self.assertIn("есть", rendered)
        # Relational recall is attention, not a fabricated exact predicate fact.
        self.assertEqual(tuple(self.core.store.find_hypernodes_by_template(self.call_t.uid)), ())


if __name__ == "__main__":
    unittest.main()
