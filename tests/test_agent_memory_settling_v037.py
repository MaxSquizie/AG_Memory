from __future__ import annotations

from pathlib import Path
import unittest

from ah.config import (
    ContextSettings,
    IgnitionSettings,
    LifecycleSettings,
    WorkspaceSettings,
    load_config,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.integration.contracts import SeedReason
from ah.model import ActantRole, Domain, Property
from ah.projection import ContextProjector


class AgentMemorySettlingV037Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())

    def _entity(self, domain: Domain, name: str, **meta):
        obj = self.core.add_entity(
            domain,
            {"name": Property("name", name, "str")},
            meta=meta,
        )
        return self.core.ref(obj.uid)

    def test_three_turn_local_ticks_are_enough_for_s_t_n_recall(self) -> None:
        subject = self._entity(Domain.P, "Пользователь", identity_role="USER")
        obj = self._entity(Domain.P, "друг")
        aux = self._entity(Domain.P, "Миша")
        symbol = self.core.ensure_abstract_symbol("есть")
        template = self.core.add_template(
            Domain.P,
            self.core.ref(symbol.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.AUXILLIARY),
        )
        node, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(template.uid),
            {
                ActantRole.SUBJECT: subject,
                ActantRole.OBJECT: obj,
                ActantRole.AUXILLIARY: aux,
            },
            0.4,
        )
        engine = IgnitionEngine(
            self.core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(gc_enabled=False),
        )
        engine.seed(self.core.ref(symbol.uid), 0.95, reason=SeedReason.RESOLVED_SYMBOL)

        first = engine.tick(include_pacemaker=False)
        self.assertEqual(self.core.store.runtime_state(node.uid).excitation, 0.0)
        self.assertTrue(any(p.target.uid == template.uid for p in first.propagations))

        second = engine.tick(include_pacemaker=False)
        self.assertEqual(self.core.store.runtime_state(node.uid).excitation, 0.0)
        self.assertTrue(any(p.target.uid == node.uid for p in second.propagations))

        engine.tick(include_pacemaker=False)
        self.assertGreater(self.core.store.runtime_state(node.uid).excitation, 0.35)
        self.assertIn(node.uid, {ref.uid for ref in engine.workspace_refs()})

    def test_turn_local_settling_does_not_advance_pacemaker(self) -> None:
        entity = self._entity(Domain.P, "X")
        engine = IgnitionEngine(
            self.core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(gc_enabled=False),
        )
        before = engine.pacemaker.snapshot()
        engine.seed(entity, 0.5)
        engine.tick(include_pacemaker=False)
        after = engine.pacemaker.snapshot()
        self.assertEqual(after.phase, before.phase)
        self.assertEqual(after.pulse_count, before.pulse_count)
        self.assertEqual(after.cursor, before.cursor)

    def test_default_orchestrator_settles_three_hops_before_projection(self) -> None:
        cfg = load_config(Path(__file__).parents[1] / "config" / "default.toml")
        self.assertEqual(cfg.orchestrator.ticks_after_input, 3)
        self.assertEqual(cfg.ignition.tick_interval_seconds, 1.0)

    def test_model_visible_memory_hides_graph_scaffolding_and_uses_source_wording(self) -> None:
        user = self._entity(Domain.P, "Пользователь", identity_role="USER")
        friend = self._entity(Domain.P, "друг")
        misha = self._entity(Domain.P, "Миша")
        pred = self.core.ensure_abstract_symbol("есть")
        fact_t = self.core.add_template(
            Domain.P,
            self.core.ref(pred.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.AUXILLIARY),
        )
        fact, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(fact_t.uid),
            {
                ActantRole.SUBJECT: user,
                ActantRole.OBJECT: friend,
                ActantRole.AUXILLIARY: misha,
            },
            0.4,
        )

        speech = self.core.ensure_abstract_symbol("высказать")
        speech_t = self.core.add_template(
            Domain.H,
            self.core.ref(speech.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        event, _ = self.core.add_hypernode(
            Domain.H,
            self.core.ref(speech_t.uid),
            {ActantRole.SUBJECT: user, ActantRole.OBJECT: self.core.ref(fact.uid)},
            0.3,
            properties={"text": Property("text", "У меня есть друг Миша", "str")},
            meta={"event_instance": True, "dedup_exempt": True},
        )

        context = ContextProjector(
            self.core,
            ContextSettings(include_structural_uids=True, max_tokens=8192),
        ).project(
            "Как зовут моего друга?",
            (
                self.core.ref(pred.uid),
                self.core.ref(fact_t.uid),
                self.core.ref(fact.uid),
                friend,
                misha,
                self.core.ref(event.uid),
                user,
            ),
            (),
        )

        self.assertIn('Пользователь ранее сказал: «У меня есть друг Миша»', context.rendered)
        self.assertNotIn("predicate=", context.rendered)
        self.assertNotIn("SUBJECT=", context.rendered)
        self.assertNotIn("[S_", context.rendered)
        self.assertNotIn("[T_", context.rendered)
        self.assertNotIn("[M_", context.rendered)
        self.assertNotIn(pred.uid, context.rendered)
        # Same utterance must not be duplicated as an H event and an N source quote.
        self.assertEqual(context.rendered.count("У меня есть друг Миша"), 1)

    def test_current_input_h_event_is_not_duplicated_into_active_memory(self) -> None:
        user = self._entity(Domain.P, "Пользователь", identity_role="USER")
        speech = self.core.ensure_abstract_symbol("высказать")
        speech_t = self.core.add_template(
            Domain.H,
            self.core.ref(speech.uid),
            (ActantRole.SUBJECT,),
        )
        event, _ = self.core.add_hypernode(
            Domain.H,
            self.core.ref(speech_t.uid),
            {ActantRole.SUBJECT: user},
            0.3,
            properties={"text": Property("text", "Дарова", "str")},
            meta={"event_instance": True, "dedup_exempt": True},
        )
        content_pred = self.core.ensure_abstract_symbol("дарова")
        content_t = self.core.add_template(Domain.C, self.core.ref(content_pred.uid), ())
        content, _ = self.core.add_hypernode(Domain.C, self.core.ref(content_t.uid), {}, 0.4)
        # Make the current H event point to the semantic content as a real turn does.
        self.core.store._replace_hypernode(
            Domain.H,
            type(event)(
                uid=event.uid, template=event.template,
                actants={ActantRole.SUBJECT: user, ActantRole.OBJECT: self.core.ref(content.uid)},
                weight=event.weight, properties=event.properties, meta=event.meta,
            ),
        )
        context = ContextProjector(self.core, ContextSettings()).project(
            "Дарова", (self.core.ref(event.uid), self.core.ref(content.uid)), ()
        )
        self.assertEqual(context.rendered.count("Дарова"), 1)
        self.assertNotIn("# ACTIVE MEMORY", context.rendered)


if __name__ == "__main__":
    unittest.main()
