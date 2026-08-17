from __future__ import annotations

from dataclasses import replace
import unittest

from ah.config import (
    ActivationSettings,
    DecaySettings,
    IgnitionSettings,
    LifecycleSettings,
    PlasticitySettings,
    PacemakerSettings,
    SeedSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import ActantRole, Domain, Property


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
            pacemaker=PacemakerSettings(enabled=False),
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

    def test_default_mvp_decay_reaches_relative_floor_without_reemitting_it(self) -> None:
        predicate = self.core.ensure_abstract_symbol("читать")
        template = self.core.add_template(
            Domain.C,
            self.core.ref(predicate.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        subject = self._entity("retained-subject")
        obj = self._entity("retained-object")
        node, _ = self.core.add_hypernode(
            Domain.C,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: subject, ActantRole.OBJECT: obj},
            weight=0.4,
        )
        settings = replace(
            IgnitionSettings(),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(
            self.core,
            settings,
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(gc_enabled=False),
        )
        engine.seed(self.core.ref(node.uid), 0.65, reason=SeedReason.NEW_FACT)
        first = engine.tick()
        self.assertGreater(len(first.propagations), 0)
        # Initial N output reaches actants on the next causal tick. After that,
        # retained x/floor must not be emitted repeatedly.
        engine.tick()
        for _ in range(300):
            result = engine.tick()
        alpha = settings.decay.alpha
        self.assertAlmostEqual(
            self.core.store.runtime_state(node.uid).excitation, 0.65 * alpha, places=5
        )
        self.assertAlmostEqual(
            self.core.store.runtime_state(subject.uid).excitation,
            (0.65 * node.weight) * alpha,
            places=5,
        )
        self.assertAlmostEqual(self.core.store.runtime_state(node.uid).output, 0.0, places=8)
        self.assertAlmostEqual(self.core.store.runtime_state(subject.uid).output, 0.0, places=8)
        self.assertEqual(result.propagations, ())

    def test_default_floor_keeps_seeded_fact_active_between_prompts_then_ratchets_down(self) -> None:
        ref = self._entity("prompt-context")
        settings = replace(IgnitionSettings(), pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(self.core, settings, WorkspaceSettings(threshold=0.35))
        engine.seed(ref, 0.65, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        for _ in range(300):
            engine.tick()
        first_floor = self.core.store.runtime_state(ref.uid).excitation
        self.assertAlmostEqual(first_floor, 0.65 * settings.decay.alpha, places=5)
        self.assertIn(ref.uid, {item.uid for item in engine.workspace_refs()})

        # The next user prompt rebases the floor from current x. If the old context
        # receives no new semantic input, it can now fall below Workspace while
        # still retaining a non-zero readiness trace.
        engine.begin_prompt_epoch()
        for _ in range(300):
            engine.tick()
        second_floor = self.core.store.runtime_state(ref.uid).excitation
        self.assertAlmostEqual(second_floor, first_floor * settings.decay.alpha, places=5)
        self.assertNotIn(ref.uid, {item.uid for item in engine.workspace_refs()})
        self.assertGreater(second_floor, 0.0)

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

    def test_pacemaker_provenance_survives_link_propagation_without_learning(self) -> None:
        a = self._entity("pace-source")
        b = self._entity("pace-middle")
        c = self._entity("pace-target")
        first = self.core.add_link("ASSOC", a, b, 0.5)
        second = self.core.add_link("ASSOC", b, c, 0.5)
        quiet = replace(self.settings, pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(self.core, quiet, self.workspace)

        engine.seed(a, 0.5, reason=SeedReason.PACEMAKER)
        engine.tick()  # A pulse schedules B with pacemaker-only provenance.
        engine.tick()  # B activates from that propagated background wave.

        self.assertGreater(self.core.store.runtime_state(b.uid).excitation, 0.0)
        self.assertAlmostEqual(self.core.store.get_link(first.uid).weight, 0.5)
        self.assertAlmostEqual(self.core.store.get_link(second.uid).weight, 0.5)

    def test_pacemaker_provenance_prevents_downstream_n_lifecycle(self) -> None:
        pred_child = self.core.ensure_abstract_symbol("спать")
        t_child = self.core.add_template(Domain.C, self.core.ref(pred_child.uid), ())
        child, _ = self.core.add_hypernode(Domain.C, self.core.ref(t_child.uid), {}, weight=0.4)

        pred_parent = self.core.ensure_abstract_symbol("помнить")
        t_parent = self.core.add_template(
            Domain.C, self.core.ref(pred_parent.uid), (ActantRole.OBJECT,)
        )
        parent, _ = self.core.add_hypernode(
            Domain.C,
            self.core.ref(t_parent.uid),
            {ActantRole.OBJECT: self.core.ref(child.uid)},
            weight=0.5,
        )
        quiet = replace(self.settings, pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(self.core, quiet, self.workspace)
        engine.seed(self.core.ref(parent.uid), 0.6, reason=SeedReason.PACEMAKER)
        engine.tick()
        engine.tick()

        self.assertGreater(self.core.store.runtime_state(child.uid).excitation, 0.0)
        self.assertNotIn("lifecycle_state", self.core.store.get_hypernode(child.uid).meta)

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

class ConfigurableIgnitionFunctionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        entity = self.core.add_entity(
            Domain.C, properties={"name": Property("name", "configurable", "str")}
        )
        self.ref = self.core.ref(entity.uid)
        self.workspace = WorkspaceSettings(threshold=0.1)

    def test_saturating_additive_activation_is_selected_by_kind(self) -> None:
        settings = IgnitionSettings(
            activation=ActivationSettings(kind="saturating_additive", gain=1.0),
            decay=DecaySettings(alpha=0.0, midpoint_ticks=1000.0, steepness=0.01),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(self.core, settings, self.workspace)
        engine.seed(self.ref, 0.5, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        engine.seed(self.ref, 0.5, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        # x=0.5, z=0.5 -> 0.5 + 0.5*(1-0.5)=0.75 before common clamp.
        self.assertAlmostEqual(self.core.store.runtime_state(self.ref.uid).excitation, 0.75, places=5)

    def test_exponential_epoch_decay_uses_half_life(self) -> None:
        from ah.ignition.policies import DecayPolicy

        policy = DecayPolicy(
            DecaySettings(kind="exponential_epoch", alpha=0.0, half_life_ticks=10.0)
        )
        self.assertAlmostEqual(policy.multiplier(0), 1.0)
        self.assertAlmostEqual(policy.multiplier(10), 0.5, places=6)
        self.assertAlmostEqual(policy.multiplier(20), 0.25, places=6)

    def test_reconfigure_switches_activation_policy_without_resetting_state(self) -> None:
        initial = IgnitionSettings(
            activation=ActivationSettings(kind="additive_clamp", gain=1.0),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(self.core, initial, self.workspace)
        engine.seed(self.ref, 0.5, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        before = self.core.store.runtime_state(self.ref.uid).excitation
        self.assertAlmostEqual(before, 0.5)

        switched = replace(
            initial,
            activation=ActivationSettings(kind="saturating_additive", gain=1.0),
        )
        engine.reconfigure(switched, self.workspace, engine.lifecycle_settings)
        self.assertAlmostEqual(self.core.store.runtime_state(self.ref.uid).excitation, before)
        engine.seed(self.ref, 0.5, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        self.assertLess(self.core.store.runtime_state(self.ref.uid).excitation, 1.0)

    def test_weak_input_does_not_rebase_floating_floor(self) -> None:
        settings = IgnitionSettings(
            decay=DecaySettings(
                alpha=0.25,
                midpoint_ticks=4.0,
                steepness=1.0,
                reactivation_min_input=0.05,
            ),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(self.core, settings, self.workspace)
        engine.seed(self.ref, 0.8, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        for _ in range(80):
            engine.tick()
        state = self.core.store.runtime_state(self.ref.uid)
        self.assertAlmostEqual(state.excitation, 0.2, places=4)
        self.assertAlmostEqual(state.decay_origin_excitation, 0.8, places=6)

        engine.seed(self.ref, 0.02, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        state = self.core.store.runtime_state(self.ref.uid)
        self.assertAlmostEqual(state.decay_origin_excitation, 0.8, places=6)
        self.assertGreater(state.excitation, 0.2)
        for _ in range(80):
            engine.tick()
        self.assertAlmostEqual(self.core.store.runtime_state(self.ref.uid).excitation, 0.2, places=4)

    def test_strong_input_rebases_floating_floor(self) -> None:
        settings = IgnitionSettings(
            decay=DecaySettings(
                alpha=0.25,
                midpoint_ticks=4.0,
                steepness=1.0,
                reactivation_min_input=0.05,
            ),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(self.core, settings, self.workspace)
        engine.seed(self.ref, 0.8, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        for _ in range(80):
            engine.tick()
        engine.seed(self.ref, 0.30, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        state = self.core.store.runtime_state(self.ref.uid)
        self.assertAlmostEqual(state.decay_origin_excitation, state.excitation, places=6)
        new_origin = state.decay_origin_excitation
        for _ in range(100):
            engine.tick()
        self.assertAlmostEqual(
            self.core.store.runtime_state(self.ref.uid).excitation,
            new_origin * settings.decay.alpha,
            places=4,
        )

    def test_prompt_epoch_rebases_floor_from_current_x(self) -> None:
        settings = IgnitionSettings(
            decay=DecaySettings(alpha=0.25, midpoint_ticks=8.0, steepness=0.8),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(self.core, settings, self.workspace)
        engine.seed(self.ref, 0.8, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        for _ in range(5):
            engine.tick()
        current = self.core.store.runtime_state(self.ref.uid).excitation
        engine.begin_prompt_epoch()
        state = self.core.store.runtime_state(self.ref.uid)
        self.assertAlmostEqual(state.decay_origin_excitation, current, places=6)
        self.assertEqual(state.decay_age, 0)
        for _ in range(120):
            engine.tick()
        self.assertAlmostEqual(
            self.core.store.runtime_state(self.ref.uid).excitation,
            current * settings.decay.alpha,
            places=4,
        )

    def test_pacemaker_only_input_never_rebases_floor(self) -> None:
        settings = IgnitionSettings(
            decay=DecaySettings(alpha=0.25, midpoint_ticks=4.0, steepness=1.0),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(self.core, settings, self.workspace)
        engine.seed(self.ref, 0.8, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        for _ in range(80):
            engine.tick()
        self.assertAlmostEqual(self.core.store.runtime_state(self.ref.uid).excitation, 0.2, places=4)
        engine.seed(self.ref, 0.5, reason=SeedReason.PACEMAKER)
        engine.tick()
        self.assertAlmostEqual(
            self.core.store.runtime_state(self.ref.uid).decay_origin_excitation, 0.8, places=6
        )

    def test_hot_alpha_raise_does_not_create_excitation(self) -> None:
        settings = IgnitionSettings(
            decay=DecaySettings(alpha=0.10, midpoint_ticks=4.0, steepness=1.0),
            pacemaker=PacemakerSettings(enabled=False),
        )
        engine = IgnitionEngine(self.core, settings, self.workspace)
        engine.seed(self.ref, 0.8, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        for _ in range(80):
            engine.tick()
        before = self.core.store.runtime_state(self.ref.uid).excitation
        engine.reconfigure_decay(replace(settings.decay, alpha=0.80))
        engine.tick()
        after = self.core.store.runtime_state(self.ref.uid).excitation
        self.assertLessEqual(after, before + 1e-9)

