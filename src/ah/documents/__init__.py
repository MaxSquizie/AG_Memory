from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock

from ah.projection import ProjectionBudgetExceeded, SourceProjectionCursor

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
    """Public document facade with bounded continuation and operator telemetry."""

    def _resolve_batch_discourse_refs(self, plan):
        """Bind only one uniquely compatible backward antecedent.

        Future candidates are excluded by document-global evidence offsets; multiple
        prior candidates remain unresolved and therefore keep Integration fail-closed.
        """
        while plan.candidate_ir.discourse_refs:
            positions: dict[str, int] = {}
            for assertion in plan.perception.assertions:
                variants = assertion.alternatives or (assertion,)
                for variant in variants:
                    for actant in variant.actants:
                        if actant.entity_ref is None or actant.evidence is None:
                            continue
                        positions[actant.entity_ref] = min(
                            positions.get(actant.entity_ref, actant.evidence.start),
                            actant.evidence.start,
                        )

            selected: tuple[str, str] | None = None
            for ref in plan.candidate_ir.discourse_refs:
                if ref.source_start is None:
                    continue
                prior = tuple(
                    candidate
                    for candidate in ref.candidate_entity_refs
                    if candidate in positions and positions[candidate] < ref.source_start
                )
                if len(prior) == 1:
                    selected = (ref.local_id, prior[0])
                    break
            if selected is None:
                break
            plan = self.services.integration.bind_discourse_ref(
                plan,
                selected[0],
                selected[1],
                context=self.services.context,
            )
        return plan

    def _reduce_partial_results(
        self,
        source_ref: str,
        request: str,
        partials: tuple[str, ...],
        *,
        budget_tokens: int,
    ):
        """Deterministically reduce AH-derived partials under the same fixed budget.

        Packing is sequential and greedy. A singleton may be carried to the next
        reduction round, but every round must reduce the number of partials. If no
        adjacent pair can fit, the operation fails closed rather than truncating or
        retrieving raw source through another channel.
        """
        current = list(partials)
        last_context = None
        while len(current) > 1:
            groups: list[tuple[str, ...]] = []
            index = 0
            while index < len(current):
                group = [current[index]]
                index += 1
                while index < len(current):
                    candidate = tuple((*group, current[index]))
                    try:
                        self._aggregation_context(
                            source_ref,
                            request,
                            candidate,
                            budget_tokens=budget_tokens,
                        )
                    except ProjectionBudgetExceeded:
                        break
                    group.append(current[index])
                    index += 1
                groups.append(tuple(group))

            reduced: list[str] = []
            reduced_any = False
            for group in groups:
                if len(group) == 1:
                    # Ensure even a singleton remains representable under the fixed
                    # aggregation budget before carrying it into the next round.
                    try:
                        self._aggregation_context(
                            source_ref,
                            request,
                            group,
                            budget_tokens=budget_tokens,
                        )
                    except ProjectionBudgetExceeded as exc:
                        raise DocumentProcessingError(
                            "One AH-derived partial result exceeds the fixed document "
                            "aggregation budget; no truncation/raw-source fallback is allowed"
                        ) from exc
                    reduced.append(group[0])
                    continue
                context = self._aggregation_context(
                    source_ref,
                    request,
                    group,
                    budget_tokens=budget_tokens,
                )
                reduced.append(self.services.agent.respond(context))
                last_context = context
                reduced_any = True

            if not reduced_any or len(reduced) >= len(current):
                raise DocumentProcessingError(
                    "Document partial aggregation cannot make progress within the fixed "
                    f"budget {budget_tokens}; no hidden fallback is permitted"
                )
            current = reduced

        if last_context is None:
            raise DocumentProcessingError("Document partial aggregation produced no final context")
        return current[0], last_context

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
        """Run bounded AH-only slices and bounded hierarchical final aggregation."""
        if self.services.agent is None:
            raise DocumentProcessingError(
                "LLM agent is disabled; memory-grounded summary requires the agent"
            )
        if budget_tokens is None:
            budget_tokens = DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS
        if budget_tokens < 1:
            raise ValueError("budget_tokens must be >= 1")
        if max_primary_roots < 1:
            raise ValueError("max_primary_roots must be >= 1")
        if max_slices < 1:
            raise ValueError("max_slices must be >= 1")

        scoped = self._source_context_service()
        cursor = SourceProjectionCursor(source_ref, 0)
        diagnostics: list[DocumentSliceDiagnostic] = []
        partials: list[str] = []
        workspace_seen: list[str] = []
        last_slice_context = None

        for slice_index in range(1, max_slices + 1):
            with self.services.operation_lock:
                sliced, result = scoped.build_source_slice(
                    request,
                    cursor,
                    max_primary_roots=max_primary_roots,
                    settle_ticks=settle_ticks,
                    budget_tokens=budget_tokens,
                )
            last_slice_context = result.context
            workspace_refs = tuple(ref.uid for ref in result.activation.workspace_after)
            for uid in workspace_refs:
                if uid not in workspace_seen:
                    workspace_seen.append(uid)
            diagnostics.append(
                DocumentSliceDiagnostic(
                    slice_index=slice_index,
                    cursor_start=sliced.cursor.next_index,
                    cursor_end=sliced.next_cursor.next_index,
                    primary_refs=tuple(ref.uid for ref in sliced.primary_refs),
                    overlap_refs=tuple(ref.uid for ref in sliced.overlap_refs),
                    workspace_refs=workspace_refs,
                    estimated_tokens=result.context.estimated_tokens,
                    done=sliced.done,
                )
            )
            partials.append(self.services.agent.respond(result.context))
            cursor = sliced.next_cursor
            if sliced.done:
                break
        else:
            raise DocumentProcessingError(
                f"Document summary exceeded max_slices={max_slices} before source cursor reached done"
            )

        if last_slice_context is None or not partials:
            raise DocumentProcessingError("Document source projection produced no semantic slice")

        if len(partials) == 1:
            text = partials[0]
            final_context = last_slice_context
        else:
            text, final_context = self._reduce_partial_results(
                source_ref,
                request,
                tuple(partials),
                budget_tokens=budget_tokens,
            )

        result = DocumentSummary(
            source_ref=source_ref,
            request=request,
            text=text,
            rendered_context=final_context.rendered,
            workspace_refs=tuple(workspace_seen),
            estimated_tokens=final_context.estimated_tokens,
            slice_diagnostics=tuple(diagnostics),
            stop_reason="source_complete",
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
