from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ah.bootstrap import RuntimeServices
from ah.config import (
    GUISettings,
    IgnitionSettings,
    LifecycleSettings,
    LLMConfig,
    PersistenceSettings,
    WorkspaceSettings,
    load_config,
)
from ah.core import AHCore, JsonPersistence
from ah.diagnostics import GraphInspector
from ah.gui.config_store import ApplyMode, ConfigDocument
from ah.gui.graph_state import (
    GraphVisualMapper,
    build_edge_focus_geometry,
    build_focus_geometry,
    pick_edge_key_2d,
    rank_visible_label_indices,
)
from ah.gui.manual_links import ManualLinkManager, ManualLinkRequest
from ah.gui.manual_nodes import ManualNodeManager, ManualNodeRequest
from ah.ignition import IgnitionEngine
from ah.llm.process_backend import LocalLLMProcessBackend
from ah.model import ActantRole, Domain, Property


PROJECT = Path(__file__).resolve().parents[1]


class GUIFoundationTests(unittest.TestCase):
    def test_config_document_edits_model_path_and_hot_parameter(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.toml"
            path.write_text((PROJECT / "config/default.toml").read_text(encoding="utf-8"), encoding="utf-8")
            doc = ConfigDocument(path)
            self.assertEqual(doc.apply_mode("paths.llm_model_dir"), ApplyMode.RESTART_LLM)
            self.assertEqual(doc.apply_mode("workspace.threshold"), ApplyMode.LIVE)
            doc.set("paths.llm_model_dir", "D:/Models/Test")
            doc.set("workspace.threshold", 0.51)
            doc.set("gui.render_mode", "3d")
            cfg = doc.save()
            self.assertEqual(str(cfg.paths.llm_model_dir).replace("\\", "/"), "D:/Models/Test")
            self.assertAlmostEqual(cfg.workspace.threshold, 0.51)
            self.assertEqual(cfg.gui.render_mode, "3d")

    def test_graph_inspector_exports_structural_hypergraph_edges(self):
        core = AHCore()
        pred = core.add_abstract_symbol({"читать"})
        person = core.add_entity(Domain.C, {"name": Property("name", "Иван", "str")})
        book = core.add_entity(Domain.C, {"name": Property("name", "книга", "str")})
        template = core.add_template(
            Domain.C,
            core.ref(pred.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        node, _ = core.add_hypernode(
            Domain.C,
            core.ref(template.uid),
            {ActantRole.SUBJECT: core.ref(person.uid), ActantRole.OBJECT: core.ref(book.uid)},
            0.4,
        )
        snap = GraphInspector(core).snapshot()
        edges = {(e.source_uid, e.target_uid, e.relation_id) for e in snap.structural_edges}
        self.assertIn((template.uid, pred.uid, "PREDICATE"), edges)
        self.assertIn((node.uid, template.uid, "TEMPLATE"), edges)
        self.assertIn((node.uid, person.uid, "SUBJECT"), edges)
        self.assertIn((node.uid, book.uid, "OBJECT"), edges)


    def test_visual_mapper_hides_orphan_lexical_s_but_keeps_structural_predicate_s(self):
        core = AHCore()
        orphan = core.add_abstract_symbol({"Яблоки"})
        predicate = core.add_abstract_symbol({"be"})
        template = core.add_template(Domain.C, core.ref(predicate.uid), ())

        snap = GraphInspector(core).snapshot()
        visual = GraphVisualMapper().build(snap, GUISettings(), x_max=1.0)

        self.assertNotIn(orphan.uid, visual.node_index)
        self.assertIn(predicate.uid, visual.node_index)
        self.assertIn(template.uid, visual.node_index)
        self.assertTrue(
            any(
                edge.source_uid == template.uid
                and edge.target_uid == predicate.uid
                and edge.relation_id == "PREDICATE"
                for edge in visual.edges
            )
        )

    def test_label_ranking_uses_filtered_visual_index_space(self):
        core = AHCore()
        # More hidden S nodes than visible positions reproduces the old refresh
        # failure: snapshot indices could be valid while visual indices were not.
        for i in range(32):
            core.add_abstract_symbol({f"lexical_{i}"})
        predicate = core.add_abstract_symbol({"write"})
        template = core.add_template(Domain.C, core.ref(predicate.uid), ())

        snap = GraphInspector(core).snapshot()
        visual = GraphVisualMapper().build(snap, GUISettings(), x_max=1.0)
        ranked = rank_visible_label_indices(snap, visual, max_labels=64)

        self.assertEqual(set(visual.node_uids), {predicate.uid, template.uid})
        self.assertEqual(set(ranked), {0, 1})
        self.assertTrue(all(0 <= i < len(visual.positions) for i in ranked))

    def test_visual_mapper_does_not_show_s_without_a_visible_incident_edge(self):
        core = AHCore()
        predicate = core.add_abstract_symbol({"be"})
        core.add_template(Domain.C, core.ref(predicate.uid), ())
        snap = GraphInspector(core).snapshot()
        settings = GUISettings(show_structural_edges=False, show_relation_edges=True)
        visual = GraphVisualMapper().build(snap, settings, x_max=1.0)
        self.assertNotIn(predicate.uid, visual.node_index)

    def test_tick_exposes_real_propagation_side_channel(self):
        core = AHCore()
        a = core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        link = core.add_link("CAUSE", core.ref(a.uid), core.ref(b.uid), 0.5)
        engine = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(),
            LifecycleSettings(gc_enabled=False),
        )
        engine.seed(core.ref(a.uid), 0.8)
        result = engine.tick()
        event = next(p for p in result.propagations if p.via_uid == link.uid)
        self.assertEqual(event.source.uid, a.uid)
        self.assertEqual(event.target.uid, b.uid)
        self.assertEqual(event.relation, "CAUSE")
        self.assertGreater(event.amount, 0)

    def test_visual_mapper_encodes_workspace_and_domain_z(self):
        core = AHCore()
        c = core.add_entity(Domain.C, {"name": Property("name", "C", "str")})
        p = core.add_entity(Domain.P, {"name": Property("name", "P", "str")})
        engine = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.2),
            LifecycleSettings(gc_enabled=False),
        )
        engine.seed(core.ref(c.uid), 0.8)
        engine.tick()
        snap = GraphInspector(core, engine).snapshot()
        visual = GraphVisualMapper().build(snap, GUISettings(render_mode="2.5d"), x_max=1.0)
        idx = visual.node_index
        self.assertTrue(visual.workspace_mask[idx[c.uid]])
        self.assertFalse(visual.workspace_mask[idx[p.uid]])
        self.assertNotEqual(visual.positions[idx[c.uid], 2], visual.positions[idx[p.uid], 2])
        self.assertGreater(visual.sizes[idx[c.uid]], visual.sizes[idx[p.uid]])


    def test_focus_geometry_contains_incident_links_and_neighbours(self):
        core = AHCore()
        a = core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        c = core.add_entity(Domain.C, {"name": Property("name", "C", "str")})
        core.add_link("CAUSE", core.ref(a.uid), core.ref(b.uid), 0.5)
        core.add_link("FOLLOW", core.ref(c.uid), core.ref(a.uid), 0.5)
        snap = GraphInspector(core).snapshot()
        visual = GraphVisualMapper().build(snap, GUISettings(), x_max=1.0)
        focus = build_focus_geometry(snap, visual, a.uid)
        neighbours = {visual.node_uids[i] for i in focus.neighbor_indices}
        self.assertEqual(neighbours, {b.uid, c.uid})
        self.assertEqual(focus.segments.shape, (4, 3))

    def test_manual_node_manager_uses_core_link_and_optional_seed(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(config, llm=replace(config.llm, enabled=False))
        services = RuntimeServices.build(config, core=AHCore())
        existing = services.core.add_entity(
            Domain.C, {"name": Property("name", "existing", "str")}
        )
        result = ManualNodeManager(services).create(
            ManualNodeRequest(
                kind="M",
                text="new",
                domain=Domain.C,
                aliases=("alias",),
                selected_uid=existing.uid,
                link_relation_id="CAUSE",
                link_weight=0.4,
                seed_amount=0.7,
            )
        )
        self.assertTrue(services.core.store.has_uid(result.ref.uid))
        self.assertIsNotNone(result.link_uid)
        link = services.core.store.get_link(result.link_uid)
        self.assertEqual(link.source.uid, existing.uid)
        self.assertEqual(link.target.uid, result.ref.uid)
        self.assertAlmostEqual(services.ignition.export_snapshot().incoming[result.ref.uid], 0.7)


    def test_manual_entity_duplicate_policy_is_domain_aware(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(config, llm=replace(config.llm, enabled=False))
        services = RuntimeServices.build(config, core=AHCore())
        manager = ManualNodeManager(services)

        first = manager.create(
            ManualNodeRequest(kind="M", text="Крипл", domain=Domain.C)
        )
        reused = manager.create(
            ManualNodeRequest(kind="M", text="Крипл", domain=Domain.C)
        )
        cross_domain = manager.create(
            ManualNodeRequest(kind="M", text="Крипл", domain=Domain.P)
        )
        namesake = manager.create(
            ManualNodeRequest(
                kind="M",
                text="Крипл",
                domain=Domain.C,
                duplicate_policy="create_new",
            )
        )

        self.assertTrue(first.created)
        self.assertFalse(reused.created)
        self.assertEqual(reused.ref.uid, first.ref.uid)
        self.assertTrue(cross_domain.created)
        self.assertNotEqual(cross_domain.ref.uid, first.ref.uid)
        self.assertTrue(namesake.created)
        self.assertNotEqual(namesake.ref.uid, first.ref.uid)
        self.assertEqual(len(services.core.store.find_entities_by_name("Крипл", Domain.C)), 2)
        self.assertEqual(len(services.core.store.find_entities_by_name("Крипл", Domain.P)), 1)

    def test_manual_entity_can_explicitly_reuse_single_identity_across_domains(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(config, llm=replace(config.llm, enabled=False))
        services = RuntimeServices.build(config, core=AHCore())
        manager = ManualNodeManager(services)
        original = manager.create(
            ManualNodeRequest(kind="M", text="Иван", domain=Domain.C)
        )
        reused = manager.create(
            ManualNodeRequest(
                kind="M",
                text="Иван",
                domain=Domain.P,
                duplicate_policy="reuse_any_domain",
            )
        )
        self.assertFalse(reused.created)
        self.assertEqual(reused.ref.uid, original.ref.uid)
        self.assertEqual(services.core.store.domain_of(reused.ref.uid), Domain.C)

    def test_manual_symbol_reuses_global_s_and_merges_new_forms(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(config, llm=replace(config.llm, enabled=False))
        services = RuntimeServices.build(config, core=AHCore())
        manager = ManualNodeManager(services)
        first = manager.create(ManualNodeRequest(kind="S", text="Крипл"))
        reused = manager.create(ManualNodeRequest(kind="S", text="Крипл, Kripl"))
        self.assertTrue(first.created)
        self.assertFalse(reused.created)
        self.assertEqual(first.ref.uid, reused.ref.uid)
        symbol = services.core.store.get_symbol(first.ref.uid)
        self.assertEqual(symbol.forms, frozenset({"Крипл", "Kripl"}))

    def test_manual_node_creation_rolls_back_if_optional_link_is_invalid(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(config, llm=replace(config.llm, enabled=False))
        services = RuntimeServices.build(config, core=AHCore())
        manager = ManualNodeManager(services)
        before = set(services.core.store.all_uids())
        with self.assertRaises(ValueError):
            manager.create(
                ManualNodeRequest(
                    kind="M",
                    text="rollback",
                    domain=Domain.C,
                    selected_uid=None,
                    link_relation_id="CAUSE",
                )
            )
        self.assertEqual(set(services.core.store.all_uids()), before)
        self.assertFalse(services.core.store.find_entities_by_name("rollback", Domain.C))

    def test_manual_link_manager_reuses_exact_link(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(config, llm=replace(config.llm, enabled=False))
        services = RuntimeServices.build(config, core=AHCore())
        a = services.core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = services.core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        manager = ManualLinkManager(services)
        first = manager.create(ManualLinkRequest(a.uid, b.uid, "CAUSE", 0.4))
        reused = manager.create(ManualLinkRequest(a.uid, b.uid, "CAUSE", 0.9))
        self.assertTrue(first.created)
        self.assertFalse(reused.created)
        self.assertEqual(first.link.uid, reused.link.uid)
        self.assertAlmostEqual(reused.link.weight, 0.4)

    def test_edge_focus_and_screen_space_picking(self):
        core = AHCore()
        a = core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        link = core.add_link("CAUSE", core.ref(a.uid), core.ref(b.uid), 0.5)
        snap = GraphInspector(core).snapshot()
        visual = GraphVisualMapper().build(snap, GUISettings(), x_max=1.0)
        key = f"L:{link.uid}"
        focus = build_edge_focus_geometry(visual, key)
        self.assertEqual(focus.edge.uid, link.uid)
        self.assertEqual(len(focus.endpoint_indices), 2)
        projected = visual.positions[:, :2].copy()
        ia, ib = visual.node_index[a.uid], visual.node_index[b.uid]
        midpoint = (projected[ia] + projected[ib]) / 2.0
        picked = pick_edge_key_2d(visual, projected, midpoint, tolerance_px=0.5)
        self.assertEqual(picked, key)

    def test_persistence_repairs_legacy_duplicate_s_and_rewrites_refs(self):
        import json
        import warnings

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "broken.json"
            payload = {
                "schema_version": 1,
                "canonical": {
                    "symbols": [
                        {"uid": "S-1", "forms": ["Крипл"]},
                        {"uid": "S-2", "forms": ["Крипл", "Kripl"]},
                    ],
                    "elements": [
                        {
                            "uid": "T-1",
                            "domain": "C",
                            "kind": "T",
                            "predicate": {"uid": "S-2", "kind": "S"},
                            "roles": [],
                        }
                    ],
                    "links": [],
                },
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            persistence = JsonPersistence(path, PersistenceSettings(save_runtime_state=False))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                bundle = persistence.load()
            self.assertTrue(caught)
            symbols = [uid for uid in bundle.core.store.all_uids() if bundle.core.store.kind_of(uid).value == "S"]
            self.assertEqual(symbols, ["S-1"])
            symbol = bundle.core.store.get_symbol("S-1")
            self.assertEqual(symbol.forms, frozenset({"Крипл", "Kripl"}))
            template = bundle.core.store.get_template("T-1")
            self.assertEqual(template.predicate.uid, "S-1")


    def test_visual_mapper_uses_red_heat_for_excited_nodes_and_adjacent_links(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(
            config,
            llm=replace(config.llm, enabled=False),
            ignition=replace(
                config.ignition,
                pacemaker=replace(config.ignition.pacemaker, enabled=False),
            ),
        )
        core = AHCore()
        a = core.add_entity(Domain.C, {"name": Property("name", "hot-A", "str")})
        b = core.add_entity(Domain.C, {"name": Property("name", "cold-B", "str")})
        core.add_link("CAUSE", core.ref(a.uid), core.ref(b.uid), 0.5)
        engine = IgnitionEngine(core, config.ignition, config.workspace, config.lifecycle)
        engine.seed(core.ref(a.uid), 0.8)
        engine.tick()
        snap = GraphInspector(core, engine).snapshot()
        visual = GraphVisualMapper().build(snap, config.gui, x_max=config.ignition.x_max)
        ai = visual.node_index[a.uid]
        self.assertGreater(float(visual.face_colors[ai, 0]), float(visual.face_colors[ai, 2]))
        self.assertGreater(float(visual.relation_colors[0, 0]), float(visual.relation_colors[0, 2]))


    def test_llm_request_completion_is_visible_in_worker_log(self):
        config = load_config(PROJECT / "config/default.toml")
        backend = LocalLLMProcessBackend(config)
        backend._request_count = 7
        backend._record_request(
            req_id="req-test",
            role="perception",
            prompt="probe",
            system="",
            response_text="1",
        )
        status = backend.status()
        self.assertTrue(any("[request #7] role=perception OK" in line for line in status.recent_log))

    def test_runtime_services_hot_reconfigure_preserves_memory(self):
        config = load_config(PROJECT / "config/default.toml")
        config = replace(config, llm=replace(config.llm, enabled=False))
        services = RuntimeServices.build(config, core=AHCore())
        entity = services.core.add_entity(Domain.C, {"name": Property("name", "keep", "str")})
        new_cfg = replace(
            config,
            workspace=WorkspaceSettings(threshold=0.61),
            ignition=replace(config.ignition, x_max=2.0, tick_interval_seconds=0.1),
        )
        services.apply_config(new_cfg)
        self.assertTrue(services.core.store.has_uid(entity.uid))
        self.assertAlmostEqual(services.ignition.workspace_settings.threshold, 0.61)
        self.assertAlmostEqual(services.ignition.settings.x_max, 2.0)
        self.assertAlmostEqual(services.clock.interval_seconds, 0.1)


if __name__ == "__main__":
    unittest.main()
