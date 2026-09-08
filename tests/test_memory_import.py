from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from ah.bootstrap import RuntimeServices
from ah.cli import build_parser, main
from ah.config import PersistenceSettings, load_config
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.corpus import (
    CorpusError,
    DIALOGUE_FORMAT,
    dump_dialogue_payload,
    max_excitation,
    parse_dialogue_json,
    split_raw_experience_text,
)
from ah.model import ActantRole, Domain, Hypernode, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)


PROJECT = Path(__file__).resolve().parents[1]


def _services(tmp: Path) -> RuntimeServices:
    memory = tmp / "ah_memory.json"
    config = load_config(PROJECT / "config" / "default.toml")
    config = replace(
        config,
        llm=replace(config.llm, enabled=False),
        paths=replace(
            config.paths,
            project_dir=tmp,
            data_dir=tmp,
            persistence_file=memory,
            logs_dir=tmp / "logs",
        ),
        persistence=replace(config.persistence, enabled=True, load_on_start=False),
    )
    services = RuntimeServices.build(
        config, core=AHCore(uid_generator=SequentialUidGenerator())
    )
    services.persistence.path = memory
    return services


class ScriptedPerception:
    def parse(self, text: str, interaction_context) -> PerceptionResult:
        del interaction_context
        roles = (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT)
        return PerceptionResult(
            source_text=text,
            assertions=(
                AssertionCandidate(
                    local_id="a1",
                    predicate=PredicateCandidate(
                        "подарил",
                        "подарить",
                        template_candidate=TemplateCandidate(roles),
                    ),
                    actants=(
                        ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                        ActantCandidate(
                            ActantRole.OBJECT, mention="книгу", normalized_hint="книга"
                        ),
                        ActantCandidate(
                            ActantRole.RECIPIENT, mention="Марии", normalized_hint="Мария"
                        ),
                    ),
                ),
            ),
        )


def _h_events(core: AHCore) -> tuple[Hypernode, ...]:
    return tuple(
        element
        for element in core.store.elements(Domain.H)
        if isinstance(element, Hypernode) and bool(element.meta.get("event_instance"))
    )


class MemoryImportTests(unittest.TestCase):
    def test_split_raw_experience_text_skips_comments(self) -> None:
        chunks = split_raw_experience_text(
            "# header\n\nПервый абзац.\n\n\n# skip\nВторой абзац.\nещё строка.\n"
        )
        self.assertEqual(chunks, ["Первый абзац.", "Второй абзац.\nещё строка."])

    def test_parse_dialogue_json_accepts_speaker_aliases(self) -> None:
        turns = parse_dialogue_json(
            {
                "format": DIALOGUE_FORMAT,
                "turns": [
                    {"speaker": "USER", "text": "Привет"},
                    {"speaker": "ASSISTANT", "text": "Здравствуйте"},
                ],
            }
        )
        self.assertEqual([turn.speaker for turn in turns], ["user", "agent"])
        payload = dump_dialogue_payload(turns)
        self.assertEqual(payload["format"], DIALOGUE_FORMAT)
        self.assertEqual(len(payload["turns"]), 2)

    def test_parse_dialogue_json_rejects_unknown_format(self) -> None:
        with self.assertRaises(CorpusError):
            parse_dialogue_json({"format": "chatml", "turns": []})

    def test_raw_import_writes_h_follow_without_excitation(self) -> None:
        with TemporaryDirectory() as tmp:
            services = _services(Path(tmp))
            result = services.import_raw_text(
                "Кошка спит.\n\nИван читает книгу.",
                save=True,
                cold_save=True,
            )
            self.assertEqual(result.turns_processed, 2)
            self.assertEqual(result.facts_created, 0)
            events = _h_events(services.core)
            self.assertEqual(len(events), 2)
            follow = [
                link for link in services.core.store.links() if link.relation_id == "FOLLOW"
            ]
            self.assertEqual(len(follow), 1)
            self.assertEqual(max_excitation(services.core), 0.0)
            self.assertTrue(services.persistence.path.is_file())

    def test_text_import_with_scripted_parser_creates_facts_cold(self) -> None:
        with TemporaryDirectory() as tmp:
            services = _services(Path(tmp))
            services.perception = ScriptedPerception()
            result = services.import_raw_text(
                "Иван подарил книгу Марии.",
                save=False,
                parse_user_semantics=True,
            )
            self.assertEqual(result.turns_processed, 1)
            self.assertGreaterEqual(result.facts_created, 1)
            self.assertTrue(services.core.store.find_entities_by_name("Иван", Domain.C))
            self.assertEqual(len(_h_events(services.core)), 1)
            self.assertEqual(max_excitation(services.core), 0.0)

    def test_dialogue_import_falls_back_to_raw_without_perception(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            services = _services(root)
            dialogue = root / "dialogue.json"
            dialogue.write_text(
                json.dumps(
                    dump_dialogue_payload(
                        [
                            {"speaker": "user", "text": "Иван подарил книгу Марии."},
                            {"speaker": "agent", "text": "Запомнил."},
                        ]
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = services.import_dialogue(
                dialogue, save=False, parse_user_semantics=True
            )
            self.assertEqual(result.turns_processed, 2)
            self.assertEqual(result.facts_created, 0)
            self.assertEqual(len(_h_events(services.core)), 2)
            self.assertEqual(max_excitation(services.core), 0.0)
            self.assertFalse(services.core.store.find_entities_by_name("Иван", Domain.C))

    def test_dialogue_import_with_scripted_parser_creates_facts_cold(self) -> None:
        with TemporaryDirectory() as tmp:
            services = _services(Path(tmp))
            services.perception = ScriptedPerception()
            payload = dump_dialogue_payload(
                [
                    {"speaker": "user", "text": "Иван подарил книгу Марии."},
                    {"speaker": "agent", "text": "Запомнил."},
                ]
            )
            result = services.import_dialogue(
                payload, save=False, parse_user_semantics=True
            )
            self.assertEqual(result.turns_processed, 2)
            self.assertGreaterEqual(result.facts_created, 1)
            self.assertTrue(services.core.store.find_entities_by_name("Иван", Domain.C))
            self.assertEqual(len(_h_events(services.core)), 2)
            self.assertEqual(max_excitation(services.core), 0.0)

    def test_memory_snapshot_cold_restore_drops_excitation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            services = _services(root)
            entity = services.core.add_entity(
                Domain.C, {"name": Property("name", "Марс", "str")}
            )
            ref = services.core.ref(entity.uid)
            services.ignition.seed(ref, 0.8)
            services.ignition.tick()
            self.assertGreater(services.core.store.runtime_state(ref.uid).excitation, 0.0)
            snapshot = root / "snapshot.json"
            JsonPersistence(
                snapshot,
                PersistenceSettings(
                    enabled=True,
                    save_runtime_state=True,
                    save_pending_impulses=True,
                ),
            ).save(services.core, ignition=services.ignition, context=services.context)

            extra = services.core.add_entity(
                Domain.C, {"name": Property("name", "лишнее", "str")}
            )
            result = services.import_memory(snapshot, save=True, cold_restore=True)
            self.assertEqual(result.max_excitation, 0.0)
            self.assertEqual(max_excitation(services.core), 0.0)
            self.assertTrue(services.core.store.find_entities_by_name("Марс", Domain.C))
            self.assertFalse(services.core.store.has_uid(extra.uid))

    def test_cli_import_text_and_dialogue(self) -> None:
        parser = build_parser()
        self.assertEqual(
            parser.parse_args(["import-text", "notes.txt", "--no-semantics", "--cold-save"]).command,
            "import-text",
        )
        self.assertEqual(
            parser.parse_args(["import-dialogue", "d.json", "--no-semantics"]).command,
            "import-dialogue",
        )
        self.assertEqual(
            parser.parse_args(["import-memory", "mem.json", "--cold-restore"]).command,
            "import-memory",
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "ah_memory.json"
            config = root / "cfg.toml"
            notes = root / "notes.txt"
            notes.write_text("Первый опыт.\n\nВторой опыт.\n", encoding="utf-8")
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
                    ["--config", str(config), "import-text", str(notes), "--cold-save"]
                )
            self.assertEqual(code, 0)
            self.assertTrue(memory.is_file())
            raw = json.loads(memory.read_text(encoding="utf-8"))
            self.assertNotIn("runtime_states", raw)


if __name__ == "__main__":
    unittest.main()
