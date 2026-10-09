#!/usr/bin/env python3
"""Prepare an isolated GUI session with the oracle's explicit TEST_ONLY resources.

This does not create reviewed production data, change the original config, or
reuse an existing memory. The release and its actual template catalog are
prepared together; copying only the two resource JSON files is insufficient.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from ah.config import PersistenceSettings, load_config
from ah.core import AHCore, JsonPersistence
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.resources.loader import ResourceRelease
from ah.gui.config_store import ConfigDocument, dumps_toml
from tools.formalizer_v7_native_binding import fixture


def _write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def prepare(config_path: str | Path, destination: str | Path) -> Path:
    """Create a new fixture directory and return its runnable config path."""
    source = Path(config_path).expanduser().resolve()
    output = Path(destination).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Fixture destination already exists; choose a new directory: {output}")
    config = load_config(source)
    document = ConfigDocument(source)
    # The generated TOML lives elsewhere. Resolve every canonical path first,
    # including omitted defaults; keep empty optional paths empty and preserve
    # Windows absolute model paths when preparing on a different OS.
    for item in fields(config.paths):
        value = getattr(config.paths, item.name)
        document.set("paths." + item.name, str(value) if value is not None else "")
    document.set("llm.engine_script", str(config.llm.engine_script) if config.llm.engine_script else "")
    document.set("paths.data_dir", str(output))
    document.set("paths.persistence_file", str(output / "ah_memory.json"))
    document.set("paths.logs_dir", str(output / "logs"))
    document.set("persistence.enabled", True)
    document.set("persistence.load_on_start", True)
    document.set("formalizer.native_commit", True)
    document.set("formalizer.resource_release_filename", "formalizer_release.json")
    document.set("formalizer.review_records_filename", "formalizer_reviews.json")
    document.set("formalizer.journal_filename", "formalizer_journal.log")

    core = AHCore()
    release, _ = fixture(core, "native_language")
    trusted = release._oracle_test_trust
    # mkdir is the exclusive reservation: existing (even empty) sessions cannot
    # be overwritten or accidentally mixed with a previous canonical WAL.
    output.mkdir(parents=True, exist_ok=False)
    journal = JournalChannel(output / "formalizer_journal.log")
    store = AHStoreAdapter(core.store, journal, core)
    if journal.read_global_head() != 0 or store.ledger.data["nodes"]:
        raise RuntimeError("Fixture seed must have an empty journal and no asserted facts")
    _write_json(output / "formalizer_release.json", release.manifest)
    _write_json(output / "formalizer_reviews.json", trusted)
    JsonPersistence(output / "ah_memory.json", PersistenceSettings()).save(core)
    generated = output / "gui.toml"
    with generated.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# TEST_ONLY oracle fixture session; not a reviewed production release.\n")
        # ConfigDocument owns type-preserving TOML serialization. Its save()
        # would target the source, so serialize a fresh mapping from entries.
        values: dict = {}
        for entry in document.entries():
            target = values
            parts = entry.path.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = entry.value
        stream.write(dumps_toml(values))
    prepared = load_config(generated)
    snapshot = JsonPersistence(prepared.paths.persistence_file, prepared.persistence).load().core
    checked = ResourceRelease.load(output / "formalizer_release.json", trusted_reviews=trusted)
    checked.validate_store(snapshot.store)
    AHStoreAdapter(snapshot.store, JournalChannel(output / "formalizer_journal.log"), snapshot)
    _write_json(output / "fixture_manifest.json", {
        "profile": "FORMALIZER_V7_GUI_ORACLE_FIXTURE",
        "reviewer": "ORACLE_FIXTURE_ONLY",
        "key_id": "TEST_ONLY",
        "production_review_claim": False,
        "gates_pass_claim": False,
        "source_config": str(source),
        "source_config_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "release_sha256": checked.sha256,
        "seed_journal_head": 0,
        "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                  for name in ("formalizer_release.json", "formalizer_reviews.json", "ah_memory.json", "gui.toml")},
    })
    return generated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "lmstudio.toml",
                        help="Existing config whose backend/model settings are preserved")
    parser.add_argument("--out", type=Path, required=True, help="New isolated session directory; must not exist")
    args = parser.parse_args(argv)
    try:
        generated = prepare(args.config, args.out)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Prepared TEST_ONLY / ORACLE_FIXTURE_ONLY resources and matching AH memory.")
    print("The public fixture key is not a production review or architecture gate PASS.")
    print("Original config and memory were not modified. Launch this isolated GUI session:")
    print(f'"{sys.executable}" -m ah.gui.app --config "{generated}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
