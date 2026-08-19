from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json

import pytest

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.core import AHCore, SequentialUidGenerator
from ah.corpus import CorpusError, import_json_payload, max_excitation
from ah.llm import OllamaBackend, build_llm_backend
from ah.model import Domain

PROJECT = Path(__file__).resolve().parents[1]


def _services(tmp: Path) -> RuntimeServices:
    cfg = load_config(PROJECT / "config" / "default.toml")
    cfg = replace(
        cfg,
        llm=replace(cfg.llm, enabled=False),
        paths=replace(cfg.paths, persistence_file=tmp / "memory.json", data_dir=tmp, logs_dir=tmp / "logs"),
        persistence=replace(cfg.persistence, load_on_start=False),
    )
    return RuntimeServices.build(cfg, core=AHCore(uid_generator=SequentialUidGenerator()))


def test_ollama_config_builds_http_backend_without_model_dir():
    cfg = load_config(PROJECT / "config" / "ollama.toml")
    assert cfg.llm.backend == "ollama"
    assert cfg.llm.ollama_model
    assert isinstance(build_llm_backend(cfg), OllamaBackend)


def test_ollama_perception_disables_thinking():
    cfg = load_config(PROJECT / "config" / "ollama.toml")
    backend = OllamaBackend(cfg)
    backend._running = backend._ready = True
    captured = {}
    def fake_chat(**kwargs):
        captured.update(kwargs)
        return "ACTOR_OR_EXPERIENCER"
    with patch.object(backend._client, "chat", side_effect=fake_chat):
        response = backend.generate("probe", system="sys", role="perception_role_cue")
    assert response.text == "ACTOR_OR_EXPERIENCER"
    assert captured["think"] is False


def test_structured_corpus_is_cold_and_idempotent():
    core = AHCore(uid_generator=SequentialUidGenerator())
    payload = {
        "entities": ["Иван", "Москва"],
        "facts": [{"predicate": "жить", "subject": "Иван", "location": "Москва"}],
    }
    first = import_json_payload(core, payload)
    second = import_json_payload(core, payload)
    assert first.facts_created == 1
    assert second.facts_created == 0
    assert second.facts_reused == 1
    assert max_excitation(core) == 0.0


def test_raw_text_no_semantics_writes_cold_h_experience():
    with TemporaryDirectory() as tmp:
        services = _services(Path(tmp))
        result = services.import_raw_text("Первый опыт.\n\nВторой опыт.", parse_user_semantics=False, save=False)
        assert result.turns_processed == 2
        assert result.errors == []
        assert max_excitation(services.core) == 0.0
        assert len(tuple(services.core.store.elements(Domain.H))) >= 2


def test_strict_import_fails_closed_instead_of_hiding_parser_error():
    class BrokenPerception:
        def parse(self, text, context):
            raise RuntimeError("parser exploded")
    with TemporaryDirectory() as tmp:
        services = _services(Path(tmp))
        services.perception = BrokenPerception()
        with pytest.raises(CorpusError, match="parser exploded"):
            services.import_raw_text("Иван читает книгу.", parse_user_semantics=True, save=False, strict=True)


def test_best_effort_must_be_explicit_and_records_error():
    class BrokenPerception:
        def parse(self, text, context):
            raise RuntimeError("parser exploded")
    with TemporaryDirectory() as tmp:
        services = _services(Path(tmp))
        services.perception = BrokenPerception()
        result = services.import_raw_text("Иван читает книгу.", parse_user_semantics=True, save=False, strict=False)
        assert result.turns_processed == 1
        assert result.errors and "parser exploded" in result.errors[0]
        assert max_excitation(services.core) == 0.0


def test_reset_memory_recreates_identity_and_removes_user_content():
    with TemporaryDirectory() as tmp:
        services = _services(Path(tmp))
        services.core.add_entity(Domain.C, meta={"probe": True})
        services.reset_memory(persist=False)
        assert services.context.self_ref is not None
        assert services.context.user_ref is not None
        assert all(not getattr(e, "meta", {}).get("probe") for e in services.core.store.all_elements())
