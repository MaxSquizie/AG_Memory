from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock

from .pipeline import (
    DocumentChunk,
    DocumentContext,
    DocumentIngestionResult,
    DocumentProcessingError,
    DocumentProcessor as _PipelineDocumentProcessor,
    DocumentSliceDiagnostic,
    DocumentSummary,
)


DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS = 4096
_MAX_RUNTIME_SUMMARY_DIAGNOSTICS = 32
_RUNTIME_DIAGNOSTICS_LOCK = RLock()
_RUNTIME_SUMMARY_DIAGNOSTICS: "OrderedDict[str, DocumentSummaryRuntimeState]" = OrderedDict()


@dataclass(frozen=True, slots=True)
class DocumentSummaryRuntimeState:
    """Operator-only continuation state from the most recent summary run.

    This object is not canonical AH, is never serialized into H and is never added
    to ``AgentContext.rendered``. It is only a bounded in-process diagnostic cache
    so GUI surfaces can inspect the continuation protocol without changing the
    existing MainWindow worker/result wiring.
    """

    source_ref: str
    slice_diagnostics: tuple[DocumentSliceDiagnostic, ...]
    stop_reason: str
    primary_covered: int
    source_primary_total: int
    final_estimated_tokens: int

    @property
    def source_coverage_ratio(self) -> float:
        if self.source_primary_total <= 0:
            return 0.0
        return min(1.0, self.primary_covered / self.source_primary_total)


def _remember_summary(result: DocumentSummary) -> None:
    diagnostics = tuple(result.slice_diagnostics)
    primary_covered = sum(len(item.primary_refs) for item in diagnostics)
    source_primary_total = diagnostics[-1].cursor_end if diagnostics else 0
    state = DocumentSummaryRuntimeState(
        source_ref=result.source_ref,
        slice_diagnostics=diagnostics,
        stop_reason=result.stop_reason,
        primary_covered=primary_covered,
        source_primary_total=source_primary_total,
        final_estimated_tokens=result.estimated_tokens,
    )
    with _RUNTIME_DIAGNOSTICS_LOCK:
        _RUNTIME_SUMMARY_DIAGNOSTICS[result.source_ref] = state
        _RUNTIME_SUMMARY_DIAGNOSTICS.move_to_end(result.source_ref)
        while len(_RUNTIME_SUMMARY_DIAGNOSTICS) > _MAX_RUNTIME_SUMMARY_DIAGNOSTICS:
            _RUNTIME_SUMMARY_DIAGNOSTICS.popitem(last=False)


def last_document_summary_runtime_state(source_ref: str) -> DocumentSummaryRuntimeState | None:
    with _RUNTIME_DIAGNOSTICS_LOCK:
        return _RUNTIME_SUMMARY_DIAGNOSTICS.get(source_ref)


class DocumentProcessor(_PipelineDocumentProcessor):
    """Public document facade with fixed continuation budget and operator telemetry."""

    def summarize(
        self,
        source_ref: str,
        *,
        request: str = "Сделай краткое содержание документа в 5–7 предложениях.",
        settle_ticks: int = 1,
        budget_tokens: int | None = DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS,
        max_primary_roots: int = 24,
        max_slices: int = 128,
    ) -> DocumentSummary:
        if budget_tokens is None:
            budget_tokens = DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS
        result = super().summarize(
            source_ref,
            request=request,
            settle_ticks=settle_ticks,
            budget_tokens=budget_tokens,
            max_primary_roots=max_primary_roots,
            max_slices=max_slices,
        )
        _remember_summary(result)
        return result


__all__ = [
    "DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS",
    "DocumentChunk",
    "DocumentContext",
    "DocumentIngestionResult",
    "DocumentProcessingError",
    "DocumentProcessor",
    "DocumentSliceDiagnostic",
    "DocumentSummary",
    "DocumentSummaryRuntimeState",
    "last_document_summary_runtime_state",
]
