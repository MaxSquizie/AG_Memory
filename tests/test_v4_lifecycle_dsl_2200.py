from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ah.config import (
    IgnitionSettings,
    LifecycleSettings,
    PacemakerSettings,
    PersistenceSettings,
    WorkspaceSettings,
    load_config,
)
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.diagnostics import HackathonPreflightInspector
from ah.dsl import DSLInterpreter
from ah.ignition import IgnitionEngine
from ah.integration.contracts import SeedReason
from ah.model import ActantRole, Domain, Property


PROJECT = Path(__file__).resolve().parents[1]


class V4LifecycleDsl2200Tests(unittest.TestCase):
    @staticmethod
    def _quiet_ignition() -> IgnitionSettings:
        return replace(IgnitionSettings(), pacemaker=PacemakerSettings(enabled=False))

    def test_normative_gc_removes_200_cold_isolated_nodes_within_50_ticks(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(
                initial_lifetime_ticks=10,
                reinforced_lifetime_ticks=100,
                min_spacing_1_ticks=20,
                min_spacing_2_ticks=50,
            ),
        )
        injected = [
            core.add_entity(Domain.C, {"name": Property("name", f"orphan-{i}", "str")}).uid
            for i in range(200)
        ]
        for _ in range(50):
            engine.tick(include_pacemaker=False)
        self.assertFalse(any(core.store.has_uid(uid) for uid in injected))

    def test_default_hackathon_lifetime_allows_m3_orphans_to_expire_within_50_ticks(self) -> None:
        cfg = load_config(PROJECT / "config/default.toml")
        self.assertLessEqual(cfg.lifecycle.initial_lifetime_ticks, 50)
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            replace(cfg.ignition, pacemaker=PacemakerSettings(enabled=False)),
            cfg.workspace,
            cfg.lifecycle,
        )
        injected = [
            core.add_entity(Domain.C, {"name": Property("name", f"default-orphan-{i}", "str")}).uid
            for i in range(200)
        ]
        for _ in range(50):
            engine.tick(include_pacemaker=False)
        self.assertFalse(any(core.store.has_uid(uid) for uid in injected))

    def test_normative_gc_preserves_s_anchored_live_structure(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(5, 100, 20, 50),
        )
        s = core.add_abstract_symbol({"работать"})
        t = core.add_template(Domain.C, core.ref(s.uid), (ActantRole.SUBJECT,))
        machine = core.add_entity(Domain.C, {"name": Property("name", "станок", "str")})
        n, _ = core.add_hypernode(
            Domain.C,
            core.ref(t.uid),
            {ActantRole.SUBJECT: core.ref(machine.uid)},
            0.4,
        )
        uids = (s.uid, t.uid, machine.uid, n.uid)
        for _ in range(20):
            engine.tick(include_pacemaker=False)
        self.assertTrue(all(core.store.has_uid(uid) for uid in uids))

    def test_initial_lifetime_is_immunity_window_not_connected_node_ttl(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(2, 100, 20, 50),
        )
        s = core.add_abstract_symbol({"проверять"})
        t = core.add_template(Domain.C, core.ref(s.uid), (ActantRole.SUBJECT,))
        actor = core.add_entity(Domain.C, {"name": Property("name", "агент", "str")})
        n, _ = core.add_hypernode(
            Domain.C,
            core.ref(t.uid),
            {ActantRole.SUBJECT: core.ref(actor.uid)},
            0.4,
        )

        # All four records are older than the configured immunity window, but the
        # component is structurally live and S-anchored, so age alone cannot delete
        # any of it.
        for _ in range(12):
            engine.tick(include_pacemaker=False)
        self.assertTrue(all(core.store.has_uid(uid) for uid in (s.uid, t.uid, actor.uid, n.uid)))

    def test_normative_gc_removes_detached_positive_subgraph_and_incident_link(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(3, 100, 20, 50),
        )
        a = core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        link = core.add_link("ASSOC", core.ref(a.uid), core.ref(b.uid), 0.8)
        seen_reasons: dict[str, str] = {}
        for _ in range(8):
            result = engine.tick(include_pacemaker=False)
            if result.gc is not None:
                seen_reasons.update(result.gc.reasons)
        self.assertFalse(core.store.has_uid(a.uid))
        self.assertFalse(core.store.has_uid(b.uid))
        self.assertFalse(core.store.has_uid(link.uid))
        self.assertEqual(seen_reasons.get(link.uid), "INCIDENT_TO_DELETED_ENDPOINT")

    def test_lone_s_obeys_initial_lifetime_then_is_collected(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(2, 100, 20, 50),
        )
        s = core.add_abstract_symbol({"одиночный"})
        engine.tick(include_pacemaker=False)
        self.assertTrue(core.store.has_uid(s.uid))
        engine.tick(include_pacemaker=False)
        self.assertTrue(core.store.has_uid(s.uid))
        engine.tick(include_pacemaker=False)
        self.assertFalse(core.store.has_uid(s.uid))

    def test_lifetime_birth_metadata_survives_persistence_and_does_not_reset_ttl(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            persistence_settings = PersistenceSettings(
                enabled=True,
                load_on_start=True,
                autosave_every_ticks=100,
                save_runtime_state=True,
                save_pending_impulses=True,
            )
            core = AHCore(uid_generator=SequentialUidGenerator())
            engine = IgnitionEngine(
                core,
                self._quiet_ignition(),
                WorkspaceSettings(),
                LifecycleSettings(6, 100, 20, 50),
            )
            for _ in range(3):
                engine.tick(include_pacemaker=False)
            orphan = core.add_entity(Domain.C, {"name": Property("name", "persisted orphan", "str")})
            birth = core.store.lifetime_birth_tick(orphan.uid)
            for _ in range(2):
                engine.tick(include_pacemaker=False)

            persistence = JsonPersistence(path, persistence_settings)
            persistence.save(core, ignition=engine)
            bundle = persistence.load(uid_generator=SequentialUidGenerator())
            restored = IgnitionEngine(
                bundle.core,
                self._quiet_ignition(),
                WorkspaceSettings(),
                LifecycleSettings(6, 100, 20, 50),
            )
            self.assertIsNotNone(bundle.ignition_snapshot)
            restored.restore_snapshot(bundle.ignition_snapshot)
            self.assertEqual(bundle.core.store.lifetime_birth_tick(orphan.uid), birth)

            # Birth was tick 3 and expiry is tick 9. Snapshot is at tick 5, so four
            # more ticks should reach the original deadline rather than granting a
            # fresh six-tick lifetime on reload.
            for _ in range(5):
                restored.tick(include_pacemaker=False)
            self.assertFalse(bundle.core.store.has_uid(orphan.uid))

    def test_dsl_manifest_is_complete_and_edit_element_covers_core_kinds(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        dsl = DSLInterpreter(core)
        expected = {
            "addAbstractSymbol", "editAbstractSymbol", "addElement", "editElement",
            "addProperty", "editProperty", "addLink", "getAbstractSymbol",
            "findAbstractSymbols", "getSReference", "findSReferences", "getMReference",
            "findMReferences", "getSymbol", "findSymbols", "getList", "findLists",
            "getTemplate", "getHypernode", "findHypernodes", "findRoles", "getLink",
            "findLinks",
        }
        self.assertEqual(set(dsl.operation_names()), expected)

        s = dsl.execute('addAbstractSymbol forms="читать,читает"').value
        m = dsl.execute('addElement domain=C kind=M name="Иван"').value
        dsl.execute(f'editElement uid=@{m.uid} name="Иван Петров" pr.age=32')
        self.assertEqual(core.store.get_element_any_domain(m.uid).properties["age"].value, 32)

        t = dsl.execute(
            f'addElement domain=C kind=T predicate=@{s.uid} roles=SUBJECT'
        ).value
        dsl.execute(f'editElement uid=@{t.uid} roles=SUBJECT,OBJECT')
        self.assertIn(ActantRole.OBJECT, core.store.get_template(t.uid).roles)

        obj = dsl.execute('addElement domain=C kind=M name="Книга"').value
        n = dsl.execute(
            f'addElement domain=C kind=N template=@{t.uid} SUBJECT=@{m.uid} OBJECT=@{obj.uid} weight=0.4'
        ).value
        dsl.execute(f'editElement uid=@{n.uid} weight=0.7')
        self.assertAlmostEqual(core.store.get_hypernode(n.uid).weight, 0.7)

        k = dsl.execute(f'addElement domain=C kind=K members=@{m.uid}').value
        dsl.execute(f'editElement uid=@{k.uid} members=@{m.uid},@{obj.uid}')
        self.assertEqual(len(core.store.get_element_any_domain(k.uid).members), 2)

    def test_preflight_exposes_exactly_five_required_hyperparameters(self) -> None:
        cfg = load_config(PROJECT / "config/default.toml")
        core = AHCore(uid_generator=SequentialUidGenerator())
        report = HackathonPreflightInspector(core, cfg).inspect()
        self.assertEqual(
            tuple(item.key for item in report.hyperparameters),
            (
                "initial_lifetime",
                "decay_g",
                "workspace_threshold_t",
                "weight_update_h",
                "rhythm_frequency_nu",
            ),
        )
        self.assertEqual(len(report.hyperparameters), 5)
        self.assertFalse(report.missing_dsl_operations)
        self.assertTrue(report.structural_ok)

    def test_every_normative_dsl_query_operation_executes_against_canonical_core(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        dsl = DSLInterpreter(core)
        s = dsl.execute('addAbstractSymbol forms="жить,живёт"').value
        dsl.execute(f'editAbstractSymbol uid=@{s.uid} forms="жить,живёт,жил"')
        actor = dsl.execute('addElement domain=C kind=M name="Заяц"').value
        dsl.execute(f'addProperty uid=@{actor.uid} name=kind value="animal" type=str')
        dsl.execute(f'editProperty uid=@{actor.uid} name=kind value="wild_animal" type=str')
        t = dsl.execute(
            f'addElement domain=C kind=T predicate=@{s.uid} roles=SUBJECT,LOCATION'
        ).value
        place = dsl.execute('addElement domain=C kind=M name="Лес"').value
        n = dsl.execute(
            f'addElement domain=C kind=N template=@{t.uid} SUBJECT=@{actor.uid} LOCATION=@{place.uid}'
        ).value
        k = dsl.execute(f'addElement domain=C kind=K members=@{n.uid}').value
        link = dsl.execute(
            f'addLink relation=IS-A source=@{actor.uid} target=@{place.uid} weight=0.2'
        ).value

        commands = (
            f'getAbstractSymbol uid=@{s.uid}',
            'findAbstractSymbols forms="жил"',
            f'getSReference uid=@{s.uid} domain=C',
            f'findSReferences uid=@{s.uid} domain=C',
            f'getMReference uid=@{actor.uid} domain=C',
            f'findMReferences uid=@{actor.uid} domain=C',
            f'getSymbol uid=@{actor.uid} domain=C',
            'findSymbols domain=C name="Заяц"',
            f'getList uid=@{k.uid} domain=C',
            f'findLists member=@{n.uid} domain=C',
            f'getTemplate uid=@{t.uid} domain=C',
            f'getHypernode uid=@{n.uid} domain=C',
            f'findHypernodes operand=@{t.uid} domain=C',
            f'findRoles role=LOCATION value=@{place.uid} domain=C',
            f'getLink uid=@{link.uid}',
            f'findLinks element=@{actor.uid}',
        )
        for command in commands:
            with self.subTest(command=command):
                result = dsl.execute(command)
                self.assertIsNotNone(result.value)

    def test_preflight_detects_is_a_and_h_follow_cycles(self) -> None:
        cfg = load_config(PROJECT / "config/default.toml")
        core = AHCore(uid_generator=SequentialUidGenerator())
        a = core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        core.add_link("IS-A", core.ref(a.uid), core.ref(b.uid), 0.2)
        core.add_link("IS-A", core.ref(b.uid), core.ref(a.uid), 0.2)

        hs = core.add_abstract_symbol({"эпизод"})
        ht = core.add_template(Domain.H, core.ref(hs.uid), ())
        h1, _ = core.add_hypernode(Domain.H, core.ref(ht.uid), {}, 0.3, deduplicate=False)
        h2, _ = core.add_hypernode(Domain.H, core.ref(ht.uid), {}, 0.3, deduplicate=False)
        core.add_link("FOLLOW", core.ref(h1.uid), core.ref(h2.uid), 0.2)
        core.add_link("FOLLOW", core.ref(h2.uid), core.ref(h1.uid), 0.2)
        report = HackathonPreflightInspector(core, cfg).inspect()
        self.assertFalse(report.is_a_acyclic)
        self.assertFalse(report.h_follow_acyclic)
        self.assertFalse(report.structural_ok)

    def test_pacemaker_pulse_does_not_immortalize_orphan(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            IgnitionSettings(
                nu=1.0,
                tick_interval_seconds=1.0,
                pacemaker=PacemakerSettings(enabled=True, target_policy="round_robin"),
            ),
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(2, 100, 20, 50),
        )
        orphan = core.add_entity(Domain.C, {"name": Property("name", "ν-orphan", "str")})
        pulsed = False
        for _ in range(12):
            result = engine.tick(include_pacemaker=True)
            if orphan.uid in result.pacemaker_targets:
                pulsed = True
        self.assertTrue(pulsed)
        self.assertFalse(core.store.has_uid(orphan.uid))

    def test_semantic_excitation_preserves_s_anchored_live_node(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            IgnitionSettings(
                nu=1.0,
                tick_interval_seconds=1.0,
                pacemaker=PacemakerSettings(enabled=True),
            ),
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(2, 100, 20, 50),
        )
        s = core.add_abstract_symbol({"хранить"})
        t = core.add_template(Domain.C, core.ref(s.uid), (ActantRole.SUBJECT,))
        actor = core.add_entity(Domain.C, {"name": Property("name", "память", "str")})
        n, _ = core.add_hypernode(
            Domain.C,
            core.ref(t.uid),
            {ActantRole.SUBJECT: core.ref(actor.uid)},
            0.4,
        )
        engine.seed(core.ref(n.uid), 0.65, reason=SeedReason.NEW_FACT)
        for _ in range(12):
            engine.tick(include_pacemaker=True)
        self.assertTrue(all(core.store.has_uid(uid) for uid in (s.uid, t.uid, actor.uid, n.uid)))

    def test_false_wrapper_protects_zero_weight_refuted_n(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(2, 100, 20, 50),
        )
        s = core.add_abstract_symbol({"отрицать"})
        t = core.add_template(Domain.C, core.ref(s.uid), (ActantRole.SUBJECT,))
        actor = core.add_entity(Domain.C, {"name": Property("name", "факт", "str")})
        n, _ = core.add_hypernode(
            Domain.C,
            core.ref(t.uid),
            {ActantRole.SUBJECT: core.ref(actor.uid)},
            0.4,
        )
        false_g, _ = core.ensure_function(Domain.C, "FALSE", (core.ref(n.uid),))
        core.store._replace_hypernode(Domain.C, replace(core.store.get_hypernode(n.uid), weight=0.0))
        for _ in range(10):
            engine.tick(include_pacemaker=False)
        self.assertTrue(core.store.has_uid(n.uid))
        self.assertTrue(core.store.has_uid(false_g.uid))

    def test_h_event_instance_is_historically_protected(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(2, 100, 20, 50),
        )
        s = core.add_abstract_symbol({"сказать"})
        t = core.add_template(Domain.H, core.ref(s.uid), ())
        event, _ = core.add_hypernode(
            Domain.H,
            core.ref(t.uid),
            {},
            0.3,
            meta={"event_instance": True},
            deduplicate=False,
        )
        for _ in range(10):
            engine.tick(include_pacemaker=False)
        self.assertTrue(core.store.has_uid(event.uid))

    def test_corpus_import_after_ignition_is_not_lifetime_managed(self) -> None:
        from ah.corpus.loader import import_json_payload

        core = AHCore(uid_generator=SequentialUidGenerator())
        IgnitionEngine(
            core,
            self._quiet_ignition(),
            WorkspaceSettings(),
            LifecycleSettings(5, 100, 20, 50),
        )
        import_json_payload(core, {"entities": [{"name": "КорпусныйУзел"}]})
        imported = core.store.find_entities_by_name("КорпусныйУзел", Domain.C)
        self.assertEqual(len(imported), 1)
        self.assertFalse(core.store.is_lifetime_managed(imported[0].uid))
        injected = core.add_entity(Domain.C, {"name": Property("name", "API-узел", "str")})
        self.assertTrue(core.store.is_lifetime_managed(injected.uid))

    def test_dsl_orphan_is_collected_with_pacemaker_on(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        engine = IgnitionEngine(
            core,
            IgnitionSettings(pacemaker=PacemakerSettings(enabled=True)),
            WorkspaceSettings(),
            LifecycleSettings(3, 100, 20, 50),
        )
        dsl = DSLInterpreter(core)
        orphan = dsl.execute('addElement domain=C kind=M name="dsl-orphan"').value
        self.assertTrue(core.store.is_lifetime_managed(orphan.uid))
        for _ in range(10):
            engine.tick(include_pacemaker=True)
        self.assertFalse(core.store.has_uid(orphan.uid))


if __name__ == "__main__":
    unittest.main()
