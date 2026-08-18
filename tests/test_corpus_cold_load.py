from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest

from ah.cli import build_parser, main
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.config import PersistenceSettings
from ah.corpus import CorpusError, import_corpus_file, import_json_payload, max_excitation
from ah.ignition import IgnitionEngine
from ah.config import IgnitionSettings, PacemakerSettings, WorkspaceSettings
from ah.model import ActantRole, Domain, RefKind


PROJECT = Path(__file__).resolve().parents[1]
EXAMPLE_JSON = PROJECT / "data" / "corpus" / "example.json"
EXAMPLE_AHM = PROJECT / "data" / "corpus" / "example.ahm"
EXAMPLE_PRJ = PROJECT / "data" / "corpus" / "example.prj"


class CorpusColdLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())

    def test_json_example_writes_facts_without_excitation(self) -> None:
        result = import_corpus_file(self.core, EXAMPLE_JSON)
        self.assertEqual(result.facts_created, 1)
        self.assertEqual(result.entities_created, 4)
        self.assertEqual(max_excitation(self.core), 0.0)
        workspace = IgnitionEngine(
            self.core,
            IgnitionSettings(pacemaker=PacemakerSettings(enabled=False)),
            WorkspaceSettings(threshold=0.35),
        ).workspace_refs()
        self.assertEqual(workspace, ())

        ivan = self.core.store.find_entities_by_name("Иван", Domain.C)
        self.assertEqual(len(ivan), 1)
        links = self.core.store.outgoing_links(ivan[0].uid, "IS-A")
        self.assertEqual(len(links), 1)

    def test_json_import_is_idempotent(self) -> None:
        first = import_corpus_file(self.core, EXAMPLE_JSON)
        second = import_corpus_file(self.core, EXAMPLE_JSON)
        self.assertEqual(first.facts_created, 1)
        self.assertEqual(second.facts_created, 0)
        self.assertEqual(second.facts_reused, 1)
        self.assertEqual(second.entities_created, 0)

    def test_ahm_example_matches_json_semantics(self) -> None:
        import_corpus_file(self.core, EXAMPLE_AHM)
        self.assertEqual(max_excitation(self.core), 0.0)
        gift = self.core.store.find_symbols_by_form("дарить")
        self.assertEqual(len(gift), 1)
        templates = self.core.store.find_templates_by_predicate(gift[0].uid)
        self.assertEqual(len(templates), 1)
        self.assertEqual(
            templates[0].roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        facts = self.core.store.find_hypernodes_by_template(templates[0].uid)
        self.assertEqual(len(facts), 1)
        self.assertEqual(self.core.store.kind_of(facts[0].uid), RefKind.N)

    def test_prj_imports_relative_ahm(self) -> None:
        result = import_corpus_file(self.core, EXAMPLE_PRJ)
        self.assertGreaterEqual(result.facts_created, 1)
        self.assertEqual(max_excitation(self.core), 0.0)

    def test_ollama_and_default_share_ignition_settings(self) -> None:
        from ah.config import load_config

        demo = load_config(PROJECT / "config" / "default.toml")
        ollama = load_config(PROJECT / "config" / "ollama.toml")
        self.assertAlmostEqual(demo.ignition.decay.alpha, ollama.ignition.decay.alpha)
        self.assertEqual(demo.ignition.pacemaker.enabled, ollama.ignition.pacemaker.enabled)
        self.assertAlmostEqual(demo.workspace.threshold, ollama.workspace.threshold)
        self.assertNotEqual(demo.llm.backend, ollama.llm.backend)

    def test_runtime_import_corpus_does_not_excite_nodes(self) -> None:
        from dataclasses import replace

        from ah.bootstrap import RuntimeServices
        from ah.config import load_config

        with TemporaryDirectory() as tmp:
            memory = Path(tmp) / "ah_memory.json"
            config = load_config(PROJECT / "config" / "default.toml")
            config = replace(config, llm=replace(config.llm, enabled=False))
            services = RuntimeServices.build(
                config, core=AHCore(uid_generator=SequentialUidGenerator())
            )
            services.persistence.path = memory
            result = services.import_corpus(EXAMPLE_JSON, save=True, cold_save=True)
            self.assertEqual(result.facts_created, 1)
            self.assertEqual(max_excitation(services.core), 0.0)
            self.assertTrue(memory.is_file())

    def test_unknown_format_fails_closed(self) -> None:
        with self.assertRaises(CorpusError):
            import_corpus_file(self.core, Path("memory.txt"))
        with self.assertRaises(CorpusError):
            import_corpus_file(self.core, Path("memory.txt"))

    def test_payload_auto_creates_missing_actants(self) -> None:
        import_json_payload(
            self.core,
            {
                "facts": [
                    {
                        "predicate": "жить",
                        "subject": "Пётр",
                        "location": "Москва",
                    }
                ]
            },
        )
        self.assertEqual(len(self.core.store.find_entities_by_name("Пётр", Domain.C)), 1)
        self.assertEqual(max_excitation(self.core), 0.0)

    def test_cli_import_corpus_cold_save(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["import-corpus", "data/corpus/example.json", "--cold-save"])
        self.assertEqual(args.command, "import-corpus")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "ah_memory.json"
            config = root / "cfg.toml"
            config.write_text(
                "\n".join(
                    [
                        "[paths]",
                        f'project_dir = "{root.as_posix()}"',
                        f'data_dir = "{root.as_posix()}"',
                        f'persistence_file = "{memory.as_posix()}"',
                        f'logs_dir = "{(root / "logs").as_posix()}"',
                        "[llm]",
                        "enabled = false",
                    ]
                ),
                encoding="utf-8",
            )
            buf = StringIO()
            with redirect_stdout(buf):
                code = main(
                    [
                        "--config",
                        str(config),
                        "import-corpus",
                        str(EXAMPLE_JSON),
                        "--cold-save",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue(memory.is_file())
            raw = json.loads(memory.read_text(encoding="utf-8"))
            self.assertNotIn("runtime_states", raw)
            loaded = JsonPersistence(
                memory,
                PersistenceSettings(save_runtime_state=False, save_pending_impulses=False),
            ).load()
            self.assertEqual(max_excitation(loaded.core), 0.0)
            self.assertTrue(loaded.core.store.find_entities_by_name("Иван", Domain.C))


if __name__ == "__main__":
    unittest.main()
