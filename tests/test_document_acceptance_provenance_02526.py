from __future__ import annotations

from types import SimpleNamespace

from ah.documents import DocumentChunk, DocumentIngestionResult
from ah.model import Ref, RefKind
from ah.perception import PerceptionResult
from ah.diagnostics.document_runtime_acceptance import _runtime_checks


def _snapshot(source_ref: str):
    return {
        "H1": {
            "uid": "H1",
            "kind": "N",
            "domain": "H",
            "meta": {
                "source_ref": source_ref,
                "batch_kind": "DOCUMENT",
                "event_instance": True,
            },
        }
    }


def _result(assertion_uids, relations=()):
    text = "Документ."
    return DocumentIngestionResult(
        source_ref="doc:provenance",
        title="Doc",
        source_text=text,
        chunks=(DocumentChunk(0, text, 0, len(text)),),
        perception_units=(PerceptionResult(text),),
        integration=SimpleNamespace(
            assertions=tuple(
                SimpleNamespace(ref=Ref(uid, RefKind.N), local_id=f"B0:{index}")
                for index, uid in enumerate(assertion_uids, 1)
            ),
            relations=tuple(relations),
            experience_ref=Ref("H1", RefKind.N),
        ),
    )


def _spec():
    return SimpleNamespace(
        final_expectation={
            "facts": [{"id": "f1"}, {"id": "f2"}],
            "links": [{"relation": "CAUSE", "source": "f1", "target": "f2"}],
        }
    )


def _checks(result, matched):
    return {
        item["name"]: item
        for item in _runtime_checks(
            _spec(),
            {"require_multiple_chunks": False},
            result,
            _snapshot(result.source_ref),
            matched,
        )
    }


def test_preexisting_matched_fact_cannot_satisfy_document_acceptance_without_commit_assertion():
    checks = _checks(
        _result(("N1",)),
        {"f1": "N1", "f2": "N_PREEXISTING"},
    )

    assert checks["runtime.atomic_document_commit"]["ok"] is True
    assert checks["runtime.oracle_facts_in_document_commit"]["ok"] is False
    assert checks["runtime.oracle_facts_in_document_commit"]["actual"]["missing_fact_ids"] == ["f2"]


def test_preexisting_canonical_link_cannot_satisfy_document_acceptance_without_commit_relation():
    checks = _checks(
        _result(("N1", "N2"), relations=()),
        {"f1": "N1", "f2": "N2"},
    )

    assert checks["runtime.oracle_facts_in_document_commit"]["ok"] is True
    assert checks["runtime.oracle_links_in_document_commit"]["ok"] is False
    missing = checks["runtime.oracle_links_in_document_commit"]["actual"]["missing"]
    assert missing == [
        {
            "relation": "CAUSE",
            "source": "f1",
            "target": "f2",
            "resolved": ["CAUSE", "N1", "N2"],
        }
    ]


def test_document_commit_relation_satisfies_provenance_check_even_when_canonical_edge_preexisted():
    relation = SimpleNamespace(
        relation_id="CAUSE",
        source=Ref("N1", RefKind.N),
        target=Ref("N2", RefKind.N),
        created=False,
    )
    checks = _checks(
        _result(("N1", "N2"), relations=(relation,)),
        {"f1": "N1", "f2": "N2"},
    )

    assert checks["runtime.oracle_facts_in_document_commit"]["ok"] is True
    assert checks["runtime.oracle_links_in_document_commit"]["ok"] is True
