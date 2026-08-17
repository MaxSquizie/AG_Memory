from __future__ import annotations

from dataclasses import replace
import unittest

from ah.config import IgnitionSettings, PacemakerSettings, WorkspaceSettings, ContextSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.integration.contracts import SeedReason
from ah.model import ActantRole, Domain, Property
from ah.projection import SemanticProjector


class LexicalRecallV032Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        settings = replace(IgnitionSettings(), pacemaker=PacemakerSettings(enabled=False))
        self.engine = IgnitionEngine(self.core, settings, WorkspaceSettings(threshold=0.35))

    def test_resolved_symbol_spreads_s_to_t_to_asserted_n(self) -> None:
        symbol = self.core.ensure_abstract_symbol("произойти")
        template = self.core.add_template(
            Domain.C,
            self.core.ref(symbol.uid),
            (ActantRole.SUBJECT,),
        )
        subject = self.core.add_entity(
            Domain.C,
            properties={"name": Property("name", "событие", "str")},
        )
        node, _ = self.core.add_hypernode(
            Domain.C,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: self.core.ref(subject.uid)},
            weight=0.4,
        )

        self.engine.seed(self.core.ref(symbol.uid), 0.95, reason=SeedReason.RESOLVED_SYMBOL)
        first = self.engine.tick()
        self.assertAlmostEqual(self.core.store.runtime_state(symbol.uid).excitation, 0.95)
        self.assertEqual(self.core.store.runtime_state(template.uid).excitation, 0.0)
        self.assertTrue(any(p.source.uid == symbol.uid and p.target.uid == template.uid for p in first.propagations))

        second = self.engine.tick()
        self.assertGreater(self.core.store.runtime_state(template.uid).excitation, 0.9)
        self.assertEqual(self.core.store.runtime_state(node.uid).excitation, 0.0)
        self.assertTrue(any(p.source.uid == template.uid and p.target.uid == node.uid for p in second.propagations))

        self.engine.tick()
        n_x = self.core.store.runtime_state(node.uid).excitation
        self.assertAlmostEqual(n_x, 0.95 * 0.4, places=6)
        self.assertGreater(n_x, 0.35)
        self.assertIn(node.uid, {ref.uid for ref in self.engine.workspace_refs()})

    def test_scoped_n_is_not_promoted_to_standalone_lexical_recall_root(self) -> None:
        symbol = self.core.ensure_abstract_symbol("купить")
        template = self.core.add_template(Domain.C, self.core.ref(symbol.uid), ())
        asserted, _ = self.core.add_hypernode(
            Domain.C,
            self.core.ref(template.uid),
            {},
            weight=0.4,
        )
        embedded, _ = self.core.add_hypernode(
            Domain.C,
            self.core.ref(template.uid),
            {},
            weight=0.4,
            meta={"semantic_scope": "EMBEDDED"},
            deduplicate=False,
        )

        self.engine.seed(self.core.ref(symbol.uid), 0.95, reason=SeedReason.RESOLVED_SYMBOL)
        self.engine.tick()
        self.engine.tick()
        self.engine.tick()
        self.assertGreater(self.core.store.runtime_state(asserted.uid).excitation, 0.35)
        self.assertEqual(self.core.store.runtime_state(embedded.uid).excitation, 0.0)

    def test_template_hypernode_index_survives_rebuild(self) -> None:
        symbol = self.core.ensure_abstract_symbol("помнить")
        template = self.core.add_template(Domain.C, self.core.ref(symbol.uid), ())
        node, _ = self.core.add_hypernode(Domain.C, self.core.ref(template.uid), {}, weight=0.4)
        self.core.store.rebuild_indexes()
        self.assertEqual(
            tuple(item.uid for item in self.core.store.find_hypernodes_by_template(template.uid)),
            (node.uid,),
        )

    def test_active_h_event_projection_starts_with_actual_utterance(self) -> None:
        utter = self.core.ensure_abstract_symbol("высказать")
        template = self.core.add_template(
            Domain.H,
            self.core.ref(utter.uid),
            (ActantRole.SUBJECT,),
        )
        user = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Пользователь", "str")},
            meta={"identity_role": "USER"},
        )
        event, _ = self.core.add_hypernode(
            Domain.H,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: self.core.ref(user.uid)},
            weight=0.3,
            properties={"text": Property("text", "Что произошло в 1956 году?", "str")},
            meta={"event_instance": True},
            deduplicate=False,
        )
        projector = SemanticProjector(
            self.core,
            ContextSettings(include_structural_uids=False),
        )
        semantic = projector.active_block(self.core.ref(event.uid)).semantic
        self.assertEqual(semantic, "реплика пользователя: Что произошло в 1956 году?")
        # Dependency mode stays compact so FOLLOW/group dependencies do not dump
        # full raw dialogue into every nested projection.
        self.assertNotIn("Что произошло", projector.dependency_text(self.core.ref(event.uid)))


if __name__ == "__main__":
    unittest.main()

class LexicalRecallEdgeV032Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        settings = replace(IgnitionSettings(), pacemaker=PacemakerSettings(enabled=False))
        self.engine = IgnitionEngine(self.core, settings, WorkspaceSettings(threshold=0.35))

    def test_resolved_mention_propagates_full_new_packet_even_when_s_is_already_high(self) -> None:
        symbol = self.core.ensure_abstract_symbol("помнить")
        template = self.core.add_template(Domain.C, self.core.ref(symbol.uid), ())
        node, _ = self.core.add_hypernode(Domain.C, self.core.ref(template.uid), {}, weight=0.4)

        # Pre-semantic surface recognition already makes S hot.
        self.engine.seed(self.core.ref(symbol.uid), 0.85, reason=SeedReason.SENSORY_SYMBOL)
        self.engine.tick()
        self.assertGreater(self.core.store.runtime_state(symbol.uid).excitation, 0.8)

        # The later canonical RESOLVED_SYMBOL mention is a *new external packet*.
        # Storage x may saturate, but propagation must not collapse to only the
        # remaining headroom (roughly 0.15).
        self.engine.seed(self.core.ref(symbol.uid), 0.95, reason=SeedReason.RESOLVED_SYMBOL)
        resolved_tick = self.engine.tick()
        event = next(
            p
            for p in resolved_tick.propagations
            if p.source.uid == symbol.uid and p.target.uid == template.uid
        )
        self.assertAlmostEqual(event.amount, 0.95, places=6)

        self.engine.tick()  # T receives the resolved packet and emits it toward N.
        self.engine.tick()  # N receives T.output * N.w.
        self.assertGreater(self.core.store.runtime_state(node.uid).excitation, 0.35)

    def test_lexical_recall_wakes_false_wrapper_not_refuted_positive_n(self) -> None:
        symbol = self.core.ensure_abstract_symbol("быть")
        template = self.core.add_template(Domain.C, self.core.ref(symbol.uid), ())
        node, _ = self.core.add_hypernode(Domain.C, self.core.ref(template.uid), {}, weight=0.4)
        false_g, _ = self.core.ensure_function(Domain.C, "FALSE", (self.core.ref(node.uid),))

        self.engine.seed(self.core.ref(symbol.uid), 0.95, reason=SeedReason.RESOLVED_SYMBOL)
        self.engine.tick()
        self.engine.tick()
        self.engine.tick()

        self.assertEqual(self.core.store.runtime_state(node.uid).excitation, 0.0)
        self.assertGreater(self.core.store.runtime_state(false_g.uid).excitation, 0.35)

    def test_function_parent_index_survives_rebuild(self) -> None:
        symbol = self.core.ensure_abstract_symbol("быть")
        template = self.core.add_template(Domain.C, self.core.ref(symbol.uid), ())
        node, _ = self.core.add_hypernode(Domain.C, self.core.ref(template.uid), {}, weight=0.4)
        false_g, _ = self.core.ensure_function(Domain.C, "FALSE", (self.core.ref(node.uid),))
        self.core.store.rebuild_indexes()
        self.assertEqual(
            tuple(item.uid for item in self.core.store.function_parents(node.uid)),
            (false_g.uid,),
        )
