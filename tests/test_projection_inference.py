from __future__ import annotations

import unittest

from ah.config import ContextSettings, InferenceSettings, IntegrationSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    CauseEntailmentGoal,
    ExistsGoal,
    InferenceEngine,
    InferenceMaterializer,
    LogicalStatus,
    RelationGoal,
    RoleFillGoal,
)
from ah.model import ActantRole, Domain, Property, RefKind
from ah.projection import ContextProjector, SemanticProjector


class ProjectionInferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.context_settings = ContextSettings(
            max_tokens=4096,
            include_structural_uids=True,
            include_mt=False,
            max_dependency_depth=8,
            overflow_policy="error",
        )
        self.inference_settings = InferenceSettings(max_depth=6, max_expanded_states=100)

    def entity(self, domain: Domain, name: str, **props):
        properties = {"name": Property("name", name, "str")}
        for key, value in props.items():
            properties[key] = Property(key, value, type(value).__name__)
        obj = self.core.add_entity(domain, properties=properties)
        return self.core.ref(obj.uid)

    def test_active_entity_exposes_own_pr_dependency_does_not(self) -> None:
        ivan = self.entity(Domain.P, "Иван", age=32)
        book = self.entity(Domain.C, "Книга", pages=500)
        pred = self.core.ensure_abstract_symbol("читать")
        template = self.core.add_template(
            Domain.C,
            self.core.ref(pred.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        node, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: ivan, ActantRole.OBJECT: book},
            0.4,
        )
        projector = SemanticProjector(self.core, self.context_settings)
        n_text = projector.active_block(self.core.ref(node.uid)).semantic
        self.assertIn("Иван", n_text)
        self.assertIn("Книга", n_text)
        self.assertNotIn("pages=500", n_text)  # dependency Pr stays hidden

        ivan_text = projector.active_block(ivan).semantic
        self.assertIn("age=32", ivan_text)

    def test_agent_context_serializes_each_workspace_root_once_and_no_trace(self) -> None:
        a = self.entity(Domain.C, "A")
        b = self.entity(Domain.C, "B")
        self.core.add_link("IS-A", a, b, 0.4)
        outcome = InferenceEngine(self.core, self.inference_settings).solve(RelationGoal("IS-A", a, b))
        ctx = ContextProjector(self.core, self.context_settings).project(
            "Что известно?",
            (a, a, b),
            (outcome,),
        )
        self.assertEqual(len(ctx.workspace_blocks), 2)
        self.assertIn("# ACTIVE MEMORY", ctx.rendered)
        self.assertIn("# INFERENCE RESULTS", ctx.rendered)
        self.assertNotIn("GOAL_SATISFIED", ctx.rendered)
        self.assertNotIn("visited", ctx.rendered.lower())

    def test_role_fill_is_predicate_agnostic(self) -> None:
        masha = self.entity(Domain.P, "Маша")
        spb = self.entity(Domain.C, "Санкт-Петербург")
        pred = self.core.ensure_abstract_symbol("жить")
        template = self.core.add_template(
            Domain.C,
            self.core.ref(pred.uid),
            (ActantRole.SUBJECT, ActantRole.LOCATION),
        )
        node, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: masha, ActantRole.LOCATION: spb},
            0.4,
        )
        outcome = InferenceEngine(self.core, self.inference_settings).solve(
            RoleFillGoal(self.core.ref(template.uid), {ActantRole.SUBJECT: masha}, ActantRole.LOCATION)
        )
        self.assertIs(outcome.status, LogicalStatus.PROVED)
        self.assertEqual(outcome.conclusion.value, spb)
        self.assertEqual(outcome.conclusion.fact.uid, node.uid)
        self.assertEqual(outcome.conclusion_domain, Domain.P)



    def test_scoped_conditional_proposition_does_not_satisfy_exists_or_role_fill(self) -> None:
        masha = self.entity(Domain.C, "Маша")
        book = self.entity(Domain.C, "Книга")
        pred = self.core.ensure_abstract_symbol("читать")
        template = self.core.add_template(
            Domain.C, self.core.ref(pred.uid), (ActantRole.SUBJECT, ActantRole.OBJECT)
        )
        scoped, _ = self.core.add_hypernode(
            Domain.C,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: masha, ActantRole.OBJECT: book},
            0.4,
            meta={"semantic_scope": "CONDITIONAL"},
            count_occurrence=False,
        )
        engine = InferenceEngine(self.core, self.inference_settings)
        exists = engine.solve(
            ExistsGoal(self.core.ref(template.uid), {ActantRole.SUBJECT: masha, ActantRole.OBJECT: book})
        )
        fill = engine.solve(
            RoleFillGoal(self.core.ref(template.uid), {ActantRole.SUBJECT: masha}, ActantRole.OBJECT)
        )
        self.assertIs(exists.status, LogicalStatus.UNKNOWN)
        self.assertIs(fill.status, LogicalStatus.UNKNOWN)
        self.assertEqual(self.core.store.get_hypernode(scoped.uid).meta.get("semantic_scope"), "CONDITIONAL")

    def test_explicit_false_disproves_precise_exists_goal(self) -> None:
        masha = self.entity(Domain.P, "Маша")
        spb = self.entity(Domain.C, "Санкт-Петербург")
        pred = self.core.ensure_abstract_symbol("жить")
        template = self.core.add_template(
            Domain.C, self.core.ref(pred.uid), (ActantRole.SUBJECT, ActantRole.LOCATION)
        )
        node, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: masha, ActantRole.LOCATION: spb},
            0.4,
        )
        false_g, _ = self.core.ensure_function(Domain.P, "FALSE", (self.core.ref(node.uid),))
        out = InferenceEngine(self.core, self.inference_settings).solve(
            ExistsGoal(
                self.core.ref(template.uid),
                {ActantRole.SUBJECT: masha, ActantRole.LOCATION: spb},
            )
        )
        self.assertIs(out.status, LogicalStatus.DISPROVED)
        self.assertEqual(out.conclusion.ref.uid, false_g.uid)

    def test_false_of_one_completion_does_not_disprove_partial_exists(self) -> None:
        masha = self.entity(Domain.P, "Маша")
        spb = self.entity(Domain.C, "Санкт-Петербург")
        pred = self.core.ensure_abstract_symbol("жить")
        template = self.core.add_template(
            Domain.C, self.core.ref(pred.uid), (ActantRole.SUBJECT, ActantRole.LOCATION)
        )
        node, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: masha, ActantRole.LOCATION: spb},
            0.4,
        )
        self.core.ensure_function(Domain.P, "FALSE", (self.core.ref(node.uid),))
        out = InferenceEngine(self.core, self.inference_settings).solve(
            ExistsGoal(self.core.ref(template.uid), {ActantRole.SUBJECT: masha})
        )
        self.assertIs(out.status, LogicalStatus.UNKNOWN)

    def test_isa_transitivity_has_exact_trace_and_materializes_once(self) -> None:
        dog = self.entity(Domain.C, "DOG")
        mammal = self.entity(Domain.C, "MAMMAL")
        animal = self.entity(Domain.C, "ANIMAL")
        l1 = self.core.add_link("IS-A", dog, mammal, 0.4)
        l2 = self.core.add_link("IS-A", mammal, animal, 0.4)

        engine = InferenceEngine(self.core, self.inference_settings)
        outcome = engine.solve(RelationGoal("IS-A", dog, animal))
        self.assertIs(outcome.status, LogicalStatus.PROVED)
        self.assertEqual(
            tuple(ref.uid for ref in outcome.uid_trace),
            (dog.uid, l1.uid, mammal.uid, l2.uid, animal.uid),
        )
        self.assertEqual(outcome.conclusion_domain, Domain.C)

        materializer = InferenceMaterializer(self.core, IntegrationSettings())
        first = materializer.materialize(outcome)
        second = materializer.materialize(outcome)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.ref, second.ref)
        self.assertEqual(self.core.store.runtime_state(dog.uid).activation_event, False)
        with self.assertRaises(KeyError):
            self.core.store.runtime_state(first.ref.uid)  # L has no x/runtime state

    def test_materialization_domain_promotes_c_to_p(self) -> None:
        rex = self.entity(Domain.P, "REX")
        dog = self.entity(Domain.C, "DOG")
        animal = self.entity(Domain.C, "ANIMAL")
        self.core.add_link("IS-A", rex, dog, 0.4)
        self.core.add_link("IS-A", dog, animal, 0.4)
        outcome = InferenceEngine(self.core, self.inference_settings).solve(RelationGoal("IS-A", rex, animal))
        self.assertEqual(outcome.conclusion_domain, Domain.P)
        result = InferenceMaterializer(self.core, IntegrationSettings()).materialize(outcome)
        self.assertEqual(result.domain, Domain.P)
        self.assertTrue(result.created)

    def test_materialization_domain_promotes_to_h_if_history_is_used(self) -> None:
        h_event = self.entity(Domain.H, "EPISODE_FACT")
        c_middle = self.entity(Domain.C, "GENERAL_FACT")
        c_target = self.entity(Domain.C, "TARGET")
        self.core.add_link("FOLLOW", h_event, c_middle, 0.4)
        self.core.add_link("FOLLOW", c_middle, c_target, 0.4)
        outcome = InferenceEngine(self.core, self.inference_settings).solve(
            RelationGoal("FOLLOW", h_event, c_target)
        )
        self.assertEqual(outcome.conclusion_domain, Domain.H)

    def test_follow_is_transitive_but_cause_is_not_generic_transitive(self) -> None:
        a = self.entity(Domain.H, "A")
        b = self.entity(Domain.H, "B")
        c = self.entity(Domain.H, "C")
        self.core.add_link("FOLLOW", a, b, 0.4)
        self.core.add_link("FOLLOW", b, c, 0.4)
        self.assertIs(
            InferenceEngine(self.core, self.inference_settings).solve(RelationGoal("FOLLOW", a, c)).status,
            LogicalStatus.PROVED,
        )

        self.core.add_link("CAUSE", a, b, 0.4)
        self.core.add_link("CAUSE", b, c, 0.4)
        cause_path = InferenceEngine(self.core, self.inference_settings).solve(RelationGoal("CAUSE", a, c))
        self.assertIs(cause_path.status, LogicalStatus.UNKNOWN)

    def test_cause_mp_uses_workspace_only_for_priority_not_validity(self) -> None:
        a = self.entity(Domain.C, "A")
        b = self.entity(Domain.C, "B")
        c = self.entity(Domain.C, "C")
        l1 = self.core.add_link("CAUSE", a, c, 0.4)
        self.core.add_link("CAUSE", b, c, 0.4)
        engine = InferenceEngine(self.core, self.inference_settings)
        out = engine.solve(CauseEntailmentGoal(c), workspace_refs=(b,))
        self.assertIs(out.status, LogicalStatus.PROVED)
        self.assertEqual(out.uid_trace[0], b)
        self.assertEqual(out.uid_trace[-1], c)

    def test_link_is_not_workspace_capable_runtime_node(self) -> None:
        a = self.entity(Domain.C, "A")
        b = self.entity(Domain.C, "B")
        link = self.core.add_link("IS-A", a, b, 0.4)
        self.assertEqual(self.core.store.kind_of(link.uid), RefKind.L)
        with self.assertRaises(KeyError):
            self.core.store.runtime_state(link.uid)


if __name__ == "__main__":
    unittest.main()
