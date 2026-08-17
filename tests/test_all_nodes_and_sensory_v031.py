from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ah.config import IgnitionSettings, PacemakerSettings, PersistenceSettings, WorkspaceSettings, LifecycleSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.diagnostics import GraphInspector
from ah.ignition import IgnitionEngine
from ah.integration import ActivationSeedRequest, SeedReason
from ah.model import ActantRole, Domain, Property


PROJECT = Path(__file__).resolve().parents[1]
MAIN = PROJECT / "src/ah/gui/main_window.py"
VIEWER = PROJECT / "src/ah/gui/all_nodes_viewer.py"
CONFIG = PROJECT / "config/default.toml"


class AllNodesAndSensoryV031Tests(unittest.TestCase):
    def test_store_creation_sequence_is_stable_and_persisted(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        s = core.add_abstract_symbol({"читать"})
        m = core.add_entity(Domain.C, {"name": Property("name", "Иван", "str")})
        t = core.add_template(Domain.C, core.ref(s.uid), (ActantRole.SUBJECT,))
        n, _ = core.add_hypernode(Domain.C, core.ref(t.uid), {ActantRole.SUBJECT: core.ref(m.uid)}, 0.4)
        before = {uid: core.store.creation_sequence(uid) for uid in core.store.all_uids()}
        self.assertEqual(sorted(before.values()), list(range(1, len(before) + 1)))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ah.json"
            persistence = JsonPersistence(path, PersistenceSettings(enabled=True, save_runtime_state=True))
            persistence.save(core)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["store_metadata"]["creation_sequence"], before)
            loaded = persistence.load().core
            after = {uid: loaded.store.creation_sequence(uid) for uid in loaded.store.all_uids()}
            self.assertEqual(after, before)

        self.assertLess(before[s.uid], before[m.uid])
        self.assertLess(before[m.uid], before[t.uid])
        self.assertLess(before[t.uid], before[n.uid])

    def test_graph_snapshot_exposes_creation_sequence_and_first_excitation(self) -> None:
        core = AHCore()
        s = core.add_abstract_symbol({"память"})
        engine = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(), LifecycleSettings(gc_enabled=False))
        engine.seed(core.ref(s.uid), 0.7, reason=SeedReason.SENSORY_SYMBOL)
        engine.tick()
        node = next(item for item in GraphInspector(core, engine).snapshot().nodes if item.uid == s.uid)
        self.assertGreater(node.creation_sequence, 0)
        self.assertEqual(node.first_excitation_tick, 0)

    def test_all_nodes_gui_is_a_sortable_separate_dock(self) -> None:
        main = MAIN.read_text(encoding="utf-8")
        viewer = VIEWER.read_text(encoding="utf-8")
        self.assertIn('QDockWidget("Все узлы"', main)
        self.assertIn("self.all_nodes_view.refresh", main)
        self.assertIn('"Добавлен #"', viewer)
        self.assertIn("setSortingEnabled(True)", viewer)
        self.assertIn("Qt.SortOrder.DescendingOrder", viewer)
        self.assertIn("active_semantics", main)

    def test_resolved_symbol_seed_is_strongest_default_external_seed(self) -> None:
        settings = IgnitionSettings()
        self.assertGreater(settings.seeds.sensory_symbol, settings.seeds.new_fact)
        self.assertGreater(settings.seeds.sensory_symbol, settings.seeds.experience)
        self.assertGreater(settings.seeds.resolved_symbol, settings.seeds.sensory_symbol)
        self.assertGreater(settings.seeds.resolved_symbol, settings.seeds.reactivated_fact)
        self.assertAlmostEqual(settings.seeds.sensory_symbol, 0.85)
        self.assertAlmostEqual(settings.seeds.resolved_symbol, 0.95)
        text = CONFIG.read_text(encoding="utf-8")
        self.assertIn("sensory_symbol = 0.85", text)
        self.assertIn("resolved_symbol = 0.95", text)

    def test_engine_applies_resolved_symbol_seed_level(self) -> None:
        core = AHCore()
        s = core.add_abstract_symbol({"произойти"})
        settings = IgnitionSettings(pacemaker=PacemakerSettings(enabled=False))
        engine = IgnitionEngine(core, settings, WorkspaceSettings(), LifecycleSettings(gc_enabled=False))
        engine.apply_seed_requests((ActivationSeedRequest(core.ref(s.uid), SeedReason.RESOLVED_SYMBOL),))
        result = engine.tick()
        state = core.store.runtime_state(s.uid)
        self.assertAlmostEqual(result.incoming_consumed[s.uid], settings.seeds.resolved_symbol)
        self.assertAlmostEqual(state.excitation, settings.seeds.resolved_symbol)


if __name__ == "__main__":
    unittest.main()
