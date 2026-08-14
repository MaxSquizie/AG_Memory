from __future__ import annotations

from dataclasses import replace
import unittest

from ah.config import (
    ActivationSettings,
    DecaySettings,
    IgnitionSettings,
    PlasticitySettings,
    PacemakerSettings,
    SeedSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import Domain, Property


class IgnitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.settings = IgnitionSettings(
            x_max=1.0,
            activation=ActivationSettings(gain=1.0, epsilon=1e-9),
            decay=DecaySettings(alpha=0.05, midpoint_ticks=3.0, steepness=1.0),
            plasticity=PlasticitySettings(
                enabled=True,
                link_hebb_increment=0.1,
                link_async_decrement=0.01,
                link_weight_floor=0.02,
                hypernode_confirmation_increment=0.05,
            ),
            seeds=SeedSettings(new_fact=0.6, reactivated_fact=0.5, experience=0.4, sensory_symbol=0.3),
        )
        self.workspace = WorkspaceSettings(threshold=0.4)
        self.engine = IgnitionEngine(self.core, self.settings, self.workspace)

    def _entity(self, name: str):
        e = self.core.add_entity(Domain.C, properties={"name": Property("name", name, "str")})
        return self.core.ref(e.uid)

    def test_first_excitation_tick_has_no_decay(self) -> None:
        a = self._entity("A")
        self.engine.seed(a, 0.6)
        first = self.engine.tick()
        self.assertAlmostEqual(self.core.store.runtime_state(a.uid).excitation, 0.6)
        self.assertIn(a.uid, {r.uid for r in first.activation_events})
        second = self.engine.tick()
        self.assertLess(self.core.store.runtime_state(a.uid).excitation, 0.6)
        self.assertNotIn(a.uid, {r.uid for r in second.activation_events})

    def test_signal_crosses_at_most_one_link_per_tick(self) -> None:
        a = self._entity("A")
        b = self._entity("B")
        c = self._entity("C")
        self.core.add_link("ASSOC", a, b, 1.0)
        self.core.add_link("ASSOC", b, c, 1.0)
        self.engine.seed(a, 0.6)

        self.engine.tick()
        self.assertEqual(self.core.store.runtime_state(b.uid).excitation, 0.0)
        self.assertEqual(self.core.store.runtime_state(c.uid).excitation, 0.0)

        self.engine.tick()
        self.assertGreater(self.core.store.runtime_state(b.uid).excitation, 0.0)
        self.assertEqual(self.core.store.runtime_state(c.uid).excitation, 0.0)

        self.engine.tick()
        self.assertGreater(self.core.store.runtime_state(c.uid).excitation, 0.0)

    def test_workspace_is_exact_x_above_threshold(self) -> None:
        a = self._entity("A")
        b = self._entity("B")
        self.engine.seed(a, 0.5)
        self.engine.seed(b, 0.4)
        result = self.engine.tick()
        uids = {r.uid for r in result.workspace}
        self.assertIn(a.uid, uids)
        self.assertNotIn(b.uid, uids)  # strict x > t

    def test_same_tick_activation_strengthens_link(self) -> None:
        a = self._entity("A")
        b = self._entity("B")
        link = self.core.add_link("ASSOC", a, b, 0.5)
        self.engine.seed(a, 0.5)
        self.engine.seed(b, 0.5)
        self.engine.tick()
        self.assertAlmostEqual(self.core.store.get_link(link.uid).weight, 0.6)


    def test_reactivation_strength_is_measured_before_clamp(self) -> None:
        a = self._entity("A")
        self.engine.seed(a, 0.95)
        self.engine.tick()
        # Advance into decay, then inject a large stimulus that would saturate x_max.
        self.engine.tick()
        before = self.core.store.runtime_state(a.uid)
        self.assertLess(before.excitation, 0.95)
        self.engine.seed(a, 1.0)
        self.engine.tick()
        after = self.core.store.runtime_state(a.uid)
        self.assertAlmostEqual(after.excitation, 1.0)
        self.assertEqual(after.decay_age, 0)


    def test_inactivity_never_decays_link_weight(self) -> None:
        a = self._entity("idle-A")
        b = self._entity("idle-B")
        link = self.core.add_link("ASSOC", a, b, 0.5)
        quiet = replace(self.settings, pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(self.core, quiet, self.workspace)
        for _ in range(30):
            engine.tick()
        self.assertAlmostEqual(self.core.store.get_link(link.uid).weight, 0.5)

    def test_n_excitation_decay_does_not_decay_n_weight(self) -> None:
        predicate = self.core.ensure_abstract_symbol("помнить")
        template = self.core.add_template(Domain.C, self.core.ref(predicate.uid), ())
        node, _ = self.core.add_hypernode(Domain.C, self.core.ref(template.uid), {}, weight=0.4)
        quiet = replace(self.settings, pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(self.core, quiet, self.workspace)
        ref = self.core.ref(node.uid)
        engine.seed(ref, 0.8, reason=SeedReason.NEW_FACT)
        engine.tick()
        first_x = self.core.store.runtime_state(ref.uid).excitation
        for _ in range(8):
            engine.tick()
        self.assertLess(self.core.store.runtime_state(ref.uid).excitation, first_x)
        self.assertAlmostEqual(self.core.store.get_hypernode(ref.uid).weight, 0.4)

    def test_single_association_event_causes_weak_link_depression(self) -> None:
        a = self._entity("async-A")
        b = self._entity("async-B")
        link = self.core.add_link("ASSOC", a, b, 0.5)
        quiet = replace(self.settings, pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(self.core, quiet, self.workspace)
        engine.seed(a, 0.5, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        self.assertAlmostEqual(self.core.store.get_link(link.uid).weight, 0.49)

    def test_pacemaker_only_event_does_not_drive_associative_depression(self) -> None:
        a = self._entity("pace-A")
        b = self._entity("pace-B")
        link = self.core.add_link("ASSOC", a, b, 0.5)
        paced = replace(
            self.settings,
            tick_interval_seconds=0.05,
            nu=20.0,
            seeds=replace(self.settings.seeds, pacemaker=0.5),
            pacemaker=PacemakerSettings(
                enabled=True,
                target_policy="round_robin",
                include_symbols=False,
                domains=("C",),
            ),
        )
        engine = IgnitionEngine(self.core, paced, self.workspace)
        engine.tick()
        self.assertAlmostEqual(self.core.store.get_link(link.uid).weight, 0.5)

    def test_duplicate_fact_seed_strengthens_n_through_h_not_dedup_directly(self) -> None:
        predicate = self.core.ensure_abstract_symbol("спать")
        template = self.core.add_template(Domain.C, self.core.ref(predicate.uid), ())
        node, _ = self.core.add_hypernode(Domain.C, self.core.ref(template.uid), {}, weight=0.4)
        ref = self.core.ref(node.uid)
        self.engine.apply_seed_requests((ActivationSeedRequest(ref, SeedReason.REACTIVATED_FACT),))
        self.engine.tick()
        self.assertAlmostEqual(self.core.store.get_hypernode(ref.uid).weight, 0.45)


if __name__ == "__main__":
    unittest.main()
