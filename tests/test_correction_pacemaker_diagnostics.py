from __future__ import annotations

import unittest

from ah.config import (
    ActivationSettings,
    ContextSettings,
    DecaySettings,
    IgnitionSettings,
    PacemakerSettings,
    PlasticitySettings,
    SeedSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.diagnostics import GraphInspector, RuntimeDiagnostics
from ah.ignition import IgnitionClock, IgnitionEngine
from ah.integration.correction import SemanticCorrectionService
from ah.model import Domain, FunctionSymbol, Property


class CorrectionPacemakerDiagnosticsTests(unittest.TestCase):
    def _engine(self, core: AHCore, *, nu: float = 1.0, tick_interval: float = 0.05, pacemaker=True):
        settings = IgnitionSettings(
            tick_interval_seconds=tick_interval,
            nu=nu,
            x_max=1.0,
            activation=ActivationSettings(gain=1.0),
            decay=DecaySettings(alpha=0.05, midpoint_ticks=3.0, steepness=1.0),
            plasticity=PlasticitySettings(
                enabled=True,
                hypernode_confirmation_increment=0.05,
                hypernode_refutation_decrement=0.15,
            ),
            seeds=SeedSettings(correction=0.6, pacemaker=0.25),
            pacemaker=PacemakerSettings(enabled=pacemaker, target_policy="round_robin", include_symbols=False),
        )
        return IgnitionEngine(core, settings, WorkspaceSettings(threshold=0.2))

    def test_false_preserves_old_n_and_refutation_runs_through_hn(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        s = core.add_abstract_symbol({"быть"})
        t = core.add_template(Domain.C, core.ref(s.uid), ())
        n, _ = core.add_hypernode(Domain.C, core.ref(t.uid), {}, 0.5)
        target = core.ref(n.uid)
        engine = self._engine(core, pacemaker=False)

        commit = SemanticCorrectionService(core).refute(target)
        engine.apply_seed_requests(commit.activation_seeds)
        engine.apply_refutation_requests(commit.refutations)
        engine.tick()

        self.assertTrue(core.store.has_uid(target.uid))
        false_obj = core.store.get_element_any_domain(commit.false_ref.uid)
        self.assertIsInstance(false_obj, FunctionSymbol)
        self.assertEqual(false_obj.function_id, "FALSE")
        self.assertEqual(false_obj.operands, (target,))
        self.assertAlmostEqual(core.store.get_hypernode(target.uid).weight, 0.35)
        self.assertGreater(core.store.runtime_state(commit.false_ref.uid).excitation, 0.0)

    def test_refutation_overrides_same_tick_confirmation(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        s = core.add_abstract_symbol({"быть"})
        t = core.add_template(Domain.C, core.ref(s.uid), ())
        n, _ = core.add_hypernode(Domain.C, core.ref(t.uid), {}, 0.5)
        target = core.ref(n.uid)
        engine = self._engine(core, pacemaker=False)

        # A duplicate/confirmation and an explicit refutation arriving in the same
        # cognitive tick must not partly cancel each other. FALSE wins for h_N.
        from ah.integration.contracts import ActivationSeedRequest, RefutationRequest, SeedReason
        engine.apply_seed_requests((ActivationSeedRequest(target, SeedReason.REACTIVATED_FACT),))
        engine.apply_refutation_requests((RefutationRequest(target),))
        engine.tick()

        self.assertAlmostEqual(core.store.get_hypernode(target.uid).weight, 0.35)

    def test_pacemaker_frequency_uses_tick_clock(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        entity = core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        # nu=2Hz on 0.1s tick -> one pulse every 5 ticks.
        engine = self._engine(core, nu=2.0, tick_interval=0.1, pacemaker=True)
        for _ in range(4):
            engine.tick()
        self.assertEqual(core.store.runtime_state(entity.uid).excitation, 0.0)
        engine.tick()
        self.assertGreater(core.store.runtime_state(entity.uid).excitation, 0.0)


    def test_background_clock_advances_engine_ticks(self) -> None:
        import time
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = self._engine(core, pacemaker=False)
        clock = IgnitionClock(engine, 0.005)
        clock.start()
        try:
            time.sleep(0.03)
        finally:
            clock.stop()
        self.assertGreaterEqual(engine.tick_index, 2)
        self.assertFalse(clock.running)

    def test_graph_diagnostics_are_read_only_and_gui_ready(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        a = core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        core.add_link("ASSOC", core.ref(a.uid), core.ref(b.uid), 0.3)
        engine = self._engine(core, pacemaker=False)
        engine.seed(core.ref(a.uid), 0.5)
        engine.tick()
        before = tuple(core.store.all_uids())

        inspector = GraphInspector(core, engine)
        snapshot = inspector.snapshot()
        payload = inspector.to_json()
        dot = inspector.to_dot()
        summary = RuntimeDiagnostics(core, engine).summary()

        self.assertEqual(before, tuple(core.store.all_uids()))
        self.assertEqual(len(snapshot.links), 1)
        self.assertIn(a.uid, payload)
        self.assertIn("digraph AH", dot)
        self.assertEqual(summary.links, 1)


if __name__ == "__main__":
    unittest.main()
