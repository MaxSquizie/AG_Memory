from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "document_acceptance"


def _norm(value: str) -> str:
    return value.casefold().replace("ё", "е")


def test_runtime_source_span_contract_is_predeclared_and_grounded_in_each_document():
    runtime = json.loads((DATA / "runtime_contract.json").read_text(encoding="utf-8"))
    oracle = json.loads((DATA / "oracle.json").read_text(encoding="utf-8"))

    oracle_docs = {item["id"]: item for item in oracle["documents"]}
    runtime_docs = runtime["documents"]

    assert runtime["version"] == 1
    assert set(runtime_docs) == set(oracle_docs)

    for document_id, contract in runtime_docs.items():
        spec = oracle_docs[document_id]
        fact_ids = {item["id"] for item in spec["final"]["facts"]}
        source = (DATA / spec["file"]).read_text(encoding="utf-8-sig")
        spans = contract.get("source_spans") or {}

        assert contract.get("require_multiple_chunks") is True
        assert len(spans) >= 3
        assert set(spans).issubset(fact_ids)

        positions = []
        for fact_id, expected in spans.items():
            needle = str(expected["contains"])
            assert needle.strip(), fact_id
            position = _norm(source).find(_norm(needle))
            assert position >= 0, (document_id, fact_id, needle)
            positions.append(position)

        # Span checks deliberately cover separated source regions rather than
        # validating three near-identical facts from one local parser window.
        assert max(positions) > min(positions), document_id


def test_runtime_contract_for_strict_causal_documents_forces_small_operational_windows():
    runtime = json.loads((DATA / "runtime_contract.json").read_text(encoding="utf-8"))

    for document_id in ("cooling_station", "greenhouse_control", "archive_leak"):
        assert runtime["documents"][document_id]["max_chunk_chars"] == 256
