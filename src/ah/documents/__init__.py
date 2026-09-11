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
    """Operator-only continuation state from the current/most recent summary run."""

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


def _store_runtime_state(state: DocumentSummaryRuntimeState) -> None:
    with _RUNTIME_DIAGNOSTICS_LOCK:
        _RUNTIME_SUMMARY_DIAGNOSTICS[state.source_ref] = state
        _RUNTIME_SUMMARY_DIAGNOSTICS.move_to_end(state.source_ref)
        while len(_RUNTIME_SUMMARY_DIAGNOSTICS) > _MAX_RUNTIME_SUMMARY_DIAGNOSTICS:
            _RUNTIME_SUMMARY_DIAGNOSTICS.popitem(last=False)


def _remember_progress(
    source_ref: str,
    diagnostics: tuple[DocumentSliceDiagnostic, ...],
    *,
    source_primary_total: int,
    stop_reason: str,
    estimated_tokens: int,
) -> None:
    _store_runtime_state(
        DocumentSummaryRuntimeState(
            source_ref=source_ref,
            slice_diagnostics=diagnostics,
            stop_reason=stop_reason,
            primary_covered=sum(len(item.primary_refs) for item in diagnostics),
            source_primary_total=source_primary_total,
            final_estimated_tokens=estimated_tokens,
        )
    )


def _remember_summary(result: DocumentSummary) -> None:
    diagnostics = tuple(result.slice_diagnostics)
    source_primary_total = diagnostics[-1].cursor_end if diagnostics else 0
    _remember_progress(
        result.source_ref,
        diagnostics,
        source_primary_total=source_primary_total,
        stop_reason=result.stop_reason,
        estimated_tokens=result.estimated_tokens,
    )


def last_document_summary_runtime_state(source_ref: str) -> DocumentSummaryRuntimeState | None:
    with _RUNTIME_DIAGNOSTICS_LOCK:
        return _RUNTIME_SUMMARY_DIAGNOSTICS.get(source_ref)


class DocumentProcessor(_PipelineDocumentProcessor):
    """Public document facade with bounded continuation and operator telemetry."""

    @classmethod
    def _latest_structural_boundary(cls, text: str, start: int, hard_end: int) -> int | None:
        """Use only boundaries that do not intentionally split a clause relation.

        A semicolon, colon or arbitrary single newline can still connect predicate,
        actants or a discourse relation. Production document ingestion therefore
        cuts only after a complete sentence or a real paragraph boundary. If none
        fits the operational budget, inherited ``chunk_text`` fails closed.
        """
        window = text[start:hard_end]
        candidates: list[int] = []
        paragraph = window.rfind("\n\n")
        if paragraph >= 0:
            candidates.append(start + paragraph + 2)
        for match in cls._SENTENCE_BOUNDARY_RE.finditer(window):
            candidates.append(start + match.end())
        viable = tuple(value for value in candidates if start < value <= hard_end)
        return max(viable) if viable else None

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
        """Deterministically reduce AH-derived partials under the same fixed budget."""
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
        source_primary_total = len(scoped.activator.resolver.resolve(source_ref).semantic_roots)
        cursor = SourceProjectionCursor(source_ref, 0)
        diagnostics: list[DocumentSliceDiagnostic] = []
        partials: list[str] = []
        workspace_seen: list[str] = []
        last_slice_context = None
        _remember_progress(
            source_ref,
            (),
            source_primary_total=source_primary_total,
            stop_reason="running",
            estimated_tokens=0,
        )

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
            _remember_progress(
                source_ref,
                tuple(diagnostics),
                source_primary_total=source_primary_total,
                stop_reason="projecting" if not sliced.done else "aggregating",
                estimated_tokens=result.context.estimated_tokens,
            )
            partials.append(self.services.agent.respond(result.context))
            cursor = sliced.next_cursor
            if sliced.done:
                break
        else:
            _remember_progress(
                source_ref,
                tuple(diagnostics),
                source_primary_total=source_primary_total,
                stop_reason="max_slices_exceeded",
                estimated_tokens=0 if last_slice_context is None else last_slice_context.estimated_tokens,
            )
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
