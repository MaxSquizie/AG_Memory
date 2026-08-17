from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ah.config import (
    ContextSettings,
    IgnitionSettings,
    InferenceSettings,
    LifecycleSettings,
    PacemakerSettings,
    PersistenceSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.ignition import IgnitionEngine, LifecycleStage
from ah.inference import InferenceEngine, LogicalStatus, RelationGoal
from ah.integration.contracts import SeedReason
from ah.model import ActantRole, Domain, Property
from ah.projection import ContextProjector


class MvpMemorySmokeTests(unittest.TestCase):
    """Fast no-LLM gate for the memory mechanics used in the MVP demo."""

    def test_memory_runtime_end_to_end_without_llm(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        ivan = core.add_entity(
            Domain.C, properties={"name": Property("name", "Иван", "str")}
        )
        book = core.add_entity(
            Domain.C, properties={"name": Property("name", "книга", "str")}
        )
        person = core.add_entity(
            Domain.C, properties={"name": Property("name", "человек", "str")}
        )
        animal = core.add_entity(
            Domain.C, properties={"name": Property("name", "живое", "str")}
        )

        predicate = core.ensure_abstract_symbol("читать")
        template = core.add_template(
            Domain.C,
            core.ref(predicate.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        fact, _ = core.add_hypernode(
            Domain.C,
            core.ref(template.uid),
            {
                ActantRole.SUBJECT: core.ref(ivan.uid),
                ActantRole.OBJECT: core.ref(book.uid),
            },
            weight=0.4,
        )
        fact_ref = core.ref(fact.uid)

        # A small deterministic lifecycle makes this smoke fast while preserving
        # the exact production state machine.
        ignition_settings = replace(
            IgnitionSettings(), pacemaker=PacemakerSettings(enabled=False)
        )
        lifecycle_settings = LifecycleSettings(
            initial_lifetime_ticks=100,
            reinforced_lifetime_ticks=100,
            min_spacing_1_ticks=2,
            min_spacing_2_ticks=3,
        )
        engine = IgnitionEngine(
            core,
            ignition_settings,
            WorkspaceSettings(threshold=0.1),
            lifecycle_settings,
        )

        # NEW fact: fresh tick has no immediate decay and N is a Workspace root.
        engine.seed(fact_ref, 0.65, reason=SeedReason.NEW_FACT)
        first = engine.tick()
        self.assertIn(fact_ref.uid, {ref.uid for ref in first.workspace})
        self.assertEqual(
            core.store.get_hypernode(fact_ref.uid).meta["lifecycle_state"],
            LifecycleStage.NEW.value,
        )

        # Causal propagation is synchronous: actants receive N output next tick.
        self.assertEqual(core.store.runtime_state(ivan.uid).excitation, 0.0)
        engine.tick()
        self.assertGreater(core.store.runtime_state(ivan.uid).excitation, 0.0)
        self.assertGreater(core.store.runtime_state(book.uid).excitation, 0.0)

        # A real repeated observation drives both h_N and spaced lifecycle.
        weight_before = core.store.get_hypernode(fact_ref.uid).weight
        engine.seed(fact_ref, 0.55, reason=SeedReason.REACTIVATED_FACT)
        engine.tick()
        self.assertGreater(core.store.get_hypernode(fact_ref.uid).weight, weight_before)
        self.assertEqual(
            core.store.get_hypernode(fact_ref.uid).meta["lifecycle_state"],
            LifecycleStage.REINFORCED.value,
        )

        # Rule-driven symbolic inference is independent of Workspace truth.
        link1 = core.add_link("IS-A", core.ref(ivan.uid), core.ref(person.uid), 0.4)
        link2 = core.add_link("IS-A", core.ref(person.uid), core.ref(animal.uid), 0.4)
        outcome = InferenceEngine(core, InferenceSettings(max_depth=6)).solve(
            RelationGoal("IS-A", core.ref(ivan.uid), core.ref(animal.uid)),
            engine.workspace_refs(),
        )
        self.assertIs(outcome.status, LogicalStatus.PROVED)
        self.assertIn(link1.uid, {ref.uid for ref in outcome.uid_trace})
        self.assertIn(link2.uid, {ref.uid for ref in outcome.uid_trace})

        # Projection exposes semantics, never excitation/weights/debug trace.
        ctx = ContextProjector(
            core,
            ContextSettings(include_structural_uids=True, max_tokens=8192),
        ).project("Что ты помнишь?", engine.workspace_refs(), (outcome,))
        self.assertIn("# ACTIVE MEMORY", ctx.rendered)
        self.assertIn("# INFERENCE RESULTS", ctx.rendered)
        self.assertNotIn("excitation", ctx.rendered.casefold())
        self.assertNotIn("GOAL_SATISFIED", ctx.rendered)

        # Canonical + runtime state survive an exact persistence roundtrip.
        with TemporaryDirectory() as td:
            store = JsonPersistence(
                Path(td) / "memory.json",
                PersistenceSettings(
                    enabled=True,
                    load_on_start=True,
                    autosave_every_ticks=1,
                    save_runtime_state=True,
                    save_pending_impulses=True,
                ),
            )
            store.save(core, ignition=engine)
            loaded = store.load()
            self.assertTrue(loaded.core.store.has_uid(fact_ref.uid))
            self.assertIsNotNone(loaded.ignition_snapshot)
            self.assertEqual(loaded.ignition_snapshot.tick_index, engine.tick_index)


if __name__ == "__main__":
    unittest.main()
