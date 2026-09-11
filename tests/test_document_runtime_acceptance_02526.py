from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace
from threading import RLock

import pytest

from ah.documents import DocumentChunk, DocumentIngestionResult
from ah.perception import PerceptionResult
import ah.diagnostics.document_runtime_acceptance as runtime_acceptance


def _oracle(tmp_path):
    root = tmp_path / "document_acceptance"
    texts = root / "texts"
    texts.mkdir(parents=True)
    (texts / "one.md").write_text(
        "Первое предложение. " * 10 + "\n\n" + "Второе предложение. " * 10,
        encoding="utf-8",
    )
    payload = {
        "version": 1,
        "documents": [
            {
                "id": "one",
                "title": "One",
                "file": "texts/one.md",
                "paragraphs": [
                    {"expect": {}, "family": "document.runtime", "tags": ["document"]},
                    {"expect": {}, "family": "document.runtime", "tags": ["document"]},
                ],
                "final": {"facts": [], "links": [], "forbidden_links": []},
                "m2_questions": [],
            }
        ],
    }
    path = root / "oracle.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _h_event(source_ref: str):
    return {
        "H1": {
            "uid": "H1",
            "kind": "N",
            "domain": "H",
            "meta": {"source_ref": source_ref, "batch_kind": "DOCUMENT"},
        }
    }


class _Clock:
    running = False

    def stop(self):
        self.running = False

    def start(self):
        self.running = True


def _services(tmp_path):
    return SimpleNamespace(
        config=SimpleNamespace(paths=SimpleNamespace(data_dir=tmp_path)),
        operation_lock=RLock(),
        clock=_Clock(),
        snapshot={},
    )


def _install_state_shims(monkeypatch):
    monkeypatch.setattr(
        runtime_acceptance,
        "canonical_ah_snapshot",
        lambda services: deepcopy(services.snapshot),
    )
    monkeypatch.setattr(
        runtime_acceptance,
        "_capture_runtime_state",
        lambda services: deepcopy(services.snapshot),
    )

    def restore(services, state):
        services.snapshot = deepcopy(state)

    monkeypatch.setattr(runtime_acceptance, "_restore_runtime_state", restore)


def test_public_document_acceptance_routes_to_atomic_runner():
    from ah.diagnostics import run_document_acceptance

    assert run_document_acceptance.__module__.endswith("document_runtime_acceptance")


def test_runner_calls_one_document_processor_ingest_and_checks_single_document_commit(tmp_path, monkeypatch):
    oracle = _oracle(tmp_path)
    services = _services(tmp_path)
    _install_state_shims(monkeypatch)
    calls = []

    class FakeProcessor:
        def __init__(self, services_arg, *, max_chunk_chars):
            assert services_arg is services
            self.limit = max_chunk_chars

        def ingest_text(self, text, *, title, source_ref):
            calls.append((text, title, source_ref, self.limit))
            services.snapshot = _h_event(source_ref)
            cut = len(text) // 2
            return DocumentIngestionResult(
                source_ref=source_ref,
                title=title,
                source_text=text,
                chunks=(
                    DocumentChunk(0, text[:cut], 0, cut),
                    DocumentChunk(1, text[cut:], cut, len(text)),
                ),
                perception_units=(PerceptionResult(text[:cut]), PerceptionResult(text[cut:])),
                integration=SimpleNamespace(assertions=()),
            )

    monkeypatch.setattr(runtime_acceptance, "DocumentProcessor", FakeProcessor)
    result = runtime_acceptance.run_document_acceptance(services, oracle_file=oracle)

    assert len(calls) == 1
    assert result.total_documents == 1
    assert result.passed_documents == 1
    assert result.runtime_errors == 0
    assert services.snapshot == {}  # live state restored after diagnostics
    record = json.loads(next(result.output_dir.glob("document_001_*.json")).read_text(encoding="utf-8"))
    checks = {item["name"]: item for item in record["graph_checks"]}
    assert checks["runtime.atomic_document_commit"]["ok"] is True
    assert checks["runtime.source_coverage"]["ok"] is True
    assert checks["runtime.multiple_operational_chunks"]["ok"] is True


def test_failed_document_records_atomic_rollback_violation_instead_of_hiding_it(tmp_path, monkeypatch):
    oracle = _oracle(tmp_path)
    services = _services(tmp_path)
    _install_state_shims(monkeypatch)

    class BrokenProcessor:
        def __init__(self, services_arg, *, max_chunk_chars):
            self.services = services_arg

        def ingest_text(self, text, *, title, source_ref):
            self.services.snapshot = {"LEAK": {"uid": "LEAK", "kind": "M", "domain": "C"}}
            raise RuntimeError("late failure")

    monkeypatch.setattr(runtime_acceptance, "DocumentProcessor", BrokenProcessor)
    result = runtime_acceptance.run_document_acceptance(services, oracle_file=oracle)

    assert result.failed_documents == 1
    assert result.runtime_errors == 1
    record = json.loads(next(result.output_dir.glob("document_001_*.json")).read_text(encoding="utf-8"))
    rollback = next(item for item in record["graph_checks"] if item["name"] == "runtime.atomic_rollback")
    assert rollback["ok"] is False
    assert record["runtime_status"] == "ERROR"
    assert services.snapshot == {}


def test_failed_document_with_real_rollback_is_still_failure_but_rollback_check_passes(tmp_path, monkeypatch):
    oracle = _oracle(tmp_path)
    services = _services(tmp_path)
    _install_state_shims(monkeypatch)

    class RolledBackProcessor:
        def __init__(self, services_arg, *, max_chunk_chars):
            self.services = services_arg

        def ingest_text(self, text, *, title, source_ref):
            raise RuntimeError("validation failure before commit")

    monkeypatch.setattr(runtime_acceptance, "DocumentProcessor", RolledBackProcessor)
    result = runtime_acceptance.run_document_acceptance(services, oracle_file=oracle)

    assert result.failed_documents == 1
    record = json.loads(next(result.output_dir.glob("document_001_*.json")).read_text(encoding="utf-8"))
    rollback = next(item for item in record["graph_checks"] if item["name"] == "runtime.atomic_rollback")
    assert rollback["ok"] is True
