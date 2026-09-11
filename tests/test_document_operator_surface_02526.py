from __future__ import annotations

from types import SimpleNamespace

import ah.documents as documents
from ah.documents import (
    DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS,
    DocumentProcessor,
    DocumentSliceDiagnostic,
    DocumentSummary,
    last_document_summary_runtime_state,
)
from ah.documents.cli import build_parser


def _summary(source_ref: str = "doc:operator") -> DocumentSummary:
    return DocumentSummary(
        source_ref=source_ref,
        request="summary",
        text="result",
        rendered_context="frozen-context",
        workspace_refs=("N1", "N2"),
        estimated_tokens=321,
        slice_diagnostics=(
            DocumentSliceDiagnostic(
                slice_index=1,
                cursor_start=0,
                cursor_end=2,
                primary_refs=("N1", "N2"),
                overlap_refs=(),
                workspace_refs=("N1", "N2"),
                estimated_tokens=200,
                done=False,
            ),
            DocumentSliceDiagnostic(
                slice_index=2,
                cursor_start=2,
                cursor_end=3,
                primary_refs=("N3",),
                overlap_refs=("N2",),
                workspace_refs=("N2", "N3"),
                estimated_tokens=180,
                done=True,
            ),
        ),
        stop_reason="source_complete",
    )


def test_public_document_processor_enforces_fixed_default_summary_budget(monkeypatch):
    captured = {}

    def fake_summary(self, source_ref, **kwargs):
        captured.update(kwargs)
        return _summary(source_ref)

    monkeypatch.setattr(documents._PipelineDocumentProcessor, "summarize", fake_summary)
    processor = DocumentProcessor(SimpleNamespace())

    result = processor.summarize("doc:operator", budget_tokens=None)

    assert result.text == "result"
    assert captured["budget_tokens"] == DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS == 4096
    assert captured["max_primary_roots"] == 24
    assert captured["max_slices"] == 128


def test_runtime_summary_diagnostics_report_cursor_budget_stop_and_full_primary_coverage(monkeypatch):
    monkeypatch.setattr(
        documents._PipelineDocumentProcessor,
        "summarize",
        lambda self, source_ref, **kwargs: _summary(source_ref),
    )
    DocumentProcessor(SimpleNamespace()).summarize("doc:operator")

    state = last_document_summary_runtime_state("doc:operator")

    assert state is not None
    assert state.stop_reason == "source_complete"
    assert state.primary_covered == 3
    assert state.source_primary_total == 3
    assert state.source_coverage_ratio == 1.0
    assert state.final_estimated_tokens == 321
    assert [item.cursor_end for item in state.slice_diagnostics] == [2, 3]
    assert state.slice_diagnostics[1].overlap_refs == ("N2",)


def test_document_cli_exposes_fixed_continuation_controls():
    args = build_parser().parse_args(["summarize", "doc:operator"])

    assert args.source_ref == "doc:operator"
    assert args.budget_tokens == 4096
    assert args.roots_per_slice == 24
    assert args.max_slices == 128
    assert args.settle_ticks == 1


def test_document_cli_run_combines_ingestion_and_continuation_surface():
    args = build_parser().parse_args(
        [
            "run",
            "example.md",
            "--chunk-chars",
            "512",
            "--budget-tokens",
            "2048",
            "--roots-per-slice",
            "8",
            "--max-slices",
            "20",
        ]
    )

    assert args.path == "example.md"
    assert args.chunk_chars == 512
    assert args.budget_tokens == 2048
    assert args.roots_per_slice == 8
    assert args.max_slices == 20
