"""Explicit GUI fixtures keep production memory and review trust isolated."""
from dataclasses import fields
import json
from pathlib import Path
import tomllib

import pytest

from ah.bootstrap import _build_formalizer_adapter
from ah.config import load_config
from ah.core import JsonPersistence
from ah.core.journal import JournalChannel
from ah.formalizer.resources.loader import ResourceRelease
from tools.prepare_formalizer_v7_gui import main, prepare


def source_config(tmp_path):
    source = tmp_path / "source" / "config.toml"
    source.parent.mkdir()
    source.write_text('''[paths]
project_dir = "../project"
llm_model_dir = "C:/AI/Local Model"
tokenizer_dir = "../tokenizer"
adapter_dir = ""
system_prompt_path = "../prompts/system.txt"
agent_prompt_path = "../prompts/agent.txt"
perception_prompt_path = "../prompts/perception.txt"
perception_prompt_dir = "../prompts/perception"
data_dir = "../production"
persistence_file = "../production/existing_memory.json"
logs_dir = "../production/logs"
[llm]
enabled = true
backend = "lmstudio"
lmstudio_base_url = "http://127.0.0.1:1234"
lmstudio_model = "user-selected-model"
lmstudio_api_key = "local-config-value"
engine_script = "../workers/model.py"
[persistence]
enabled = false
load_on_start = false
[formalizer]
resource_release_filename = "custom_release.json"
review_records_filename = "custom_reviews.json"
journal_filename = "custom.log"
''', encoding="utf-8")
    return source


def test_gui_fixture_has_valid_release_actual_templates_and_restart_safe_seed(tmp_path):
    source = source_config(tmp_path)
    original = source.read_bytes()
    production = tmp_path / "production"
    production.mkdir()
    marker = production / "existing_memory.json"
    marker.write_bytes(b"production memory must stay untouched")
    generated = prepare(source, tmp_path / "isolated")
    config = load_config(generated)
    trusted = json.loads((config.paths.data_dir / "formalizer_reviews.json").read_text())
    release = ResourceRelease.load(config.paths.data_dir / "formalizer_release.json", trusted_reviews=trusted)
    core = JsonPersistence(config.paths.persistence_file, config.persistence).load().core
    release.validate_store(core.store)
    assert release.entries("TemplateMap")
    assert all(core.store.has_uid(row["template_ref"]) for row in release.entries("TemplateMap"))
    assert JournalChannel(config.paths.data_dir / "formalizer_journal.log").read_global_head() == 0
    assert core.store._state.formalizer_state["nodes"] == {}
    adapter = _build_formalizer_adapter(config, core, backend=object())
    assert adapter.native_available
    assert adapter._release.sha256 == release.sha256
    notice = json.loads((config.paths.data_dir / "fixture_manifest.json").read_text())
    assert notice["reviewer"] == "ORACLE_FIXTURE_ONLY"
    assert notice["key_id"] == "TEST_ONLY"
    assert notice["production_review_claim"] is False
    assert notice["gates_pass_claim"] is False
    assert source.read_bytes() == original
    assert marker.read_bytes() == b"production memory must stay untouched"
    assert not (production / "formalizer_release.json").exists()


def test_generated_config_preserves_backend_and_resolves_moved_relative_paths(tmp_path):
    source = source_config(tmp_path)
    original = load_config(source)
    generated = prepare(source, tmp_path / "nested" / "isolated")
    config = load_config(generated)
    assert config.llm == original.llm
    for item in fields(config.paths):
        if item.name not in {"data_dir", "persistence_file", "logs_dir"}:
            assert getattr(config.paths, item.name) == getattr(original.paths, item.name)
    assert config.persistence.enabled and config.persistence.load_on_start
    assert config.paths.data_dir == generated.parent
    assert config.paths.persistence_file == generated.parent / "ah_memory.json"
    assert config.paths.logs_dir == generated.parent / "logs"
    assert config.formalizer.resource_release_filename == "formalizer_release.json"
    raw = tomllib.loads(generated.read_text())
    assert raw["paths"]["adapter_dir"] == ""
    assert raw["paths"]["llm_model_dir"] == "C:/AI/Local Model"
    assert Path(raw["llm"]["engine_script"]).is_absolute()


@pytest.mark.parametrize("with_file", [False, True])
def test_existing_destination_even_empty_is_refused_without_mutation(tmp_path, with_file):
    source = source_config(tmp_path)
    output = tmp_path / "isolated"
    output.mkdir()
    if with_file:
        (output / "memory.json").write_bytes(b"preserve")
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError, match="already exists"):
        prepare(source, output)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_cli_prints_exact_launch_config_and_test_only_status(tmp_path, capsys):
    source = source_config(tmp_path)
    output = tmp_path / "isolated"
    assert main(["--config", str(source), "--out", str(output)]) == 0
    emitted = capsys.readouterr().out
    assert f'-m ah.gui.app --config "{output / "gui.toml"}"' in emitted
    assert "TEST_ONLY / ORACLE_FIXTURE_ONLY" in emitted
    assert "not a production review" in emitted
