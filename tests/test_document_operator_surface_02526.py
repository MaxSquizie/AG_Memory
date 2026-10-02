from __future__ import annotations

import inspect
from types import SimpleNamespace

import ah.documents.runtime as document_runtime
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


def test_public_document_processor_declares_fixed_default_summary_budget():
    parameter = inspect.signature(DocumentProcessor.summarize).parameters["budget_tokens"]

    assert parameter.default == DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS == 4096


def test_runtime_summary_diagnostics_report_cursor_budget_stop_and_full_primary_coverage():
    document_runtime._remember_summary(_summary("doc:operator"))

    state = last_document_summary_runtime_state("doc:operator")

    assert state is not None
    assert state.stop_reason == "source_complete"
    assert state.primary_covered == 3
    assert state.source_primary_total == 3
    assert state.source_coverage_ratio == 1.0
    assert state.final_estimated_tokens == 321
    assert state.failure is None
    assert [item.cursor_end for item in state.slice_diagnostics] == [2, 3]
    assert state.slice_diagnostics[1].overlap_refs == ("N2",)


def test_live_runtime_progress_uses_fixed_total_and_runtime_only_stop_state():
    diagnostics = _summary("doc:live").slice_diagnostics[:1]
    document_runtime._remember_progress(
        "doc:live",
        diagnostics,
        source_primary_total=3,
        stop_reason="projecting",
        estimated_tokens=200,
    )

    state = last_document_summary_runtime_state("doc:live")

    assert state is not None
    assert state.stop_reason == "projecting"
    assert state.primary_covered == 2
    assert state.source_primary_total == 3
    assert state.source_coverage_ratio == 2 / 3
    assert state.final_estimated_tokens == 200
    assert state.failure is None


def test_runtime_progress_preserves_failure_category_without_entering_agent_context():
    document_runtime._remember_progress(
        "doc:failed",
        (),
        source_primary_total=4,
        stop_reason="slice_budget_exceeded",
        estimated_tokens=5000,
        failure="ProjectionBudgetExceeded: deterministic budget exceeded",
    )

    state = last_document_summary_runtime_state("doc:failed")

    assert state is not None
    assert state.stop_reason == "slice_budget_exceeded"
    assert state.failure == "ProjectionBudgetExceeded: deterministic budget exceeded"
    assert state.primary_covered == 0
    assert state.source_primary_total == 4
    assert state.final_estimated_tokens == 5000


def test_hierarchical_aggregation_stays_within_fixed_budget_and_reduces_to_one_result():
    class Agent:
        def __init__(self):
            self.contexts = []

        def respond(self, context):
            self.contexts.append(context)
            return f"compressed-{len(self.contexts)}"

    agent = Agent()
    processor = DocumentProcessor(SimpleNamespace(agent=agent))
    partials = ("A" * 120, "B" * 120, "C" * 120, "D" * 120)
    pair_context = processor._aggregation_context(
        "doc:operator",
        "summary",
        partials[:2],
        budget_tokens=None,
    )
    budget = pair_context.estimated_tokens
    assert processor._aggregation_context(
        "doc:operator", "summary", partials[:2], budget_tokens=budget
    ).estimated_tokens <= budget

    text, final_context = processor._reduce_partial_results(
        "doc:operator",
        "summary",
        partials,
        budget_tokens=budget,
    )

    assert text.startswith("compressed-")
    assert len(agent.contexts) == 3
    assert all(context.estimated_tokens <= budget for context in agent.contexts)
    assert final_context is agent.contexts[-1]


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
