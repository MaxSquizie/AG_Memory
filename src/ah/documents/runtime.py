from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from threading import RLock

from ah.perception import AssertionStatus, SituationRelationCandidate
from ah.projection import ProjectionBudgetExceeded, SourceProjectionCursor

from .pipeline import (
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
    failure: str | None = None

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
    failure: str | None = None,
) -> None:
    _store_runtime_state(
        DocumentSummaryRuntimeState(
            source_ref=source_ref,
            slice_diagnostics=diagnostics,
            stop_reason=stop_reason,
            primary_covered=sum(len(item.primary_refs) for item in diagnostics),
            source_primary_total=source_primary_total,
            final_estimated_tokens=estimated_tokens,
            failure=failure,
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


def _failure_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class DocumentProcessor(_PipelineDocumentProcessor):
    """Production document facade with safe chunking and bounded continuation."""

    @classmethod
    def _latest_structural_boundary(cls, text: str, start: int, hard_end: int) -> int | None:
        """Cut only after a complete sentence or a real paragraph boundary.

        A semicolon, colon or arbitrary single newline can still connect predicate,
        actants or a discourse relation. If no safe boundary fits the operational
        budget, inherited ``chunk_text`` fails closed rather than severing semantics.
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

    @staticmethod
    def _assertion_start(assertion) -> int | None:
        starts: list[int] = []
        evidence = getattr(assertion, "evidence", None)
        if evidence is not None and evidence.start is not None:
            starts.append(int(evidence.start))
        predicate = getattr(assertion, "predicate", None)
        predicate_evidence = None if predicate is None else getattr(predicate, "evidence", None)
        if predicate_evidence is not None and predicate_evidence.start is not None:
            starts.append(int(predicate_evidence.start))
        for actant in getattr(assertion, "actants", ()):
            actant_evidence = getattr(actant, "evidence", None)
            if actant_evidence is not None and actant_evidence.start is not None:
                starts.append(int(actant_evidence.start))
        return min(starts) if starts else None

    @staticmethod
    def _assertion_semantic(assertion) -> str:
        predicate = assertion.predicate.lookup_form
        bindings: list[str] = []
        for actant in assertion.actants:
            value = actant.lookup_text
            if value:
                bindings.append(f"{actant.role.value}={value}")
            elif actant.candidate_ref is not None or actant.proposition is not None:
                bindings.append(f"{actant.role.value}=[situation]")
        body = predicate if not bindings else f"{predicate}({', '.join(bindings)})"
        return f"NOT {body}" if assertion.negated else body

    def _boundary_discourse_relations(self, plan) -> tuple[SituationRelationCandidate, ...]:
        """Resolve CAUSE/FOLLOW that crosses operational chunk boundaries.

        The semantic probe receives only two adjacent bounded source windows plus
        UID-free candidate strings. Its finite-choice decision is mapped back to
        parser-local assertion IDs. Canonical UIDs are never shown to Perception and
        no canonical mutation occurs here.

        Assertions whose UID-free semantic fingerprint already appeared in an
        earlier window are excluded from ``current``. Those are document dedup
        bridges, not new events, and allowing them into the probe could create a
        spurious self/FOLLOW edge after canonical deduplication.
        """
        classifier = getattr(self.services.perception, "classify_discourse_relation", None)
        if not callable(classifier):
            return ()

        source_text = plan.perception.source_text
        chunks = self.chunk_text(source_text)
        if len(chunks) < 2:
            return ()

        buckets: list[list[object]] = [[] for _ in chunks]
        for assertion in plan.perception.assertions:
            if assertion.status is not AssertionStatus.ASSERTED or assertion.quoted:
                continue
            start = self._assertion_start(assertion)
            if start is None:
                continue
            for index, chunk in enumerate(chunks):
                if chunk.start <= start < chunk.end:
                    buckets[index].append(assertion)
                    break
        for bucket in buckets:
            bucket.sort(
                key=lambda item: (
                    self._assertion_start(item)
                    if self._assertion_start(item) is not None
                    else 2**63,
                    item.local_id,
                )
            )

        existing = {
            (item.canonical_relation_id, item.source_ref, item.target_ref)
            for item in plan.perception.relations
        }
        additions: list[SituationRelationCandidate] = []

        for boundary_index in range(1, len(chunks)):
            prior = tuple(buckets[boundary_index - 1])
            earlier_semantics = {
                self._assertion_semantic(item)
                for bucket in buckets[:boundary_index]
                for item in bucket
            }
            current = tuple(
                item
                for item in buckets[boundary_index]
                if self._assertion_semantic(item) not in earlier_semantics
            )
            if not prior or not current:
                continue

            prior_semantics = tuple(self._assertion_semantic(item) for item in prior)
            current_semantics = tuple(self._assertion_semantic(item) for item in current)
            resolved_current = {
                current_index
                for current_index, assertion in enumerate(current)
                if any(
                    relation.canonical_relation_id in {"CAUSE", "FOLLOW"}
                    and relation.target_ref == assertion.local_id
                    for relation in plan.perception.relations
                )
            }
            excluded = {
                (prior_index, current_index)
                for current_index in resolved_current
                for prior_index in range(len(prior))
            }
            narrative_context = chunks[boundary_index - 1].text + chunks[boundary_index].text

            while len(resolved_current) < len(current):
                decision = classifier(
                    narrative_context,
                    prior_semantics,
                    current_semantics,
                    excluded_pairs=tuple(sorted(excluded)),
                )
                if decision is None:
                    break
                if (
                    decision.prior_index < 0
                    or decision.prior_index >= len(prior)
                    or decision.current_index < 0
                    or decision.current_index >= len(current)
                    or decision.current_index in resolved_current
                    or (decision.prior_index, decision.current_index) in excluded
                ):
                    raise DocumentProcessingError(
                        "Document boundary discourse probe escaped its finite candidate set"
                    )
                relation_id = decision.canonical_relation_id
                if relation_id not in {"CAUSE", "FOLLOW"}:
                    raise DocumentProcessingError(
                        f"Unsupported document boundary discourse relation: {relation_id}"
                    )
                source_ref = prior[decision.prior_index].local_id
                target_ref = current[decision.current_index].local_id
                key = (relation_id, source_ref, target_ref)
                if key not in existing:
                    additions.append(
                        SituationRelationCandidate(
                            relation_id=relation_id,
                            source_ref=source_ref,
                            target_ref=target_ref,
                        )
                    )
                    existing.add(key)
                resolved_current.add(decision.current_index)
                excluded.update(
                    (prior_index, decision.current_index)
                    for prior_index in range(len(prior))
                )

        return tuple(additions)

    def _resolve_batch_discourse_refs(self, plan):
        """Resolve document-wide references/relations before the sole canonical commit."""
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

        # Ambiguous/future-only coreference already makes the document invalid.
        # Do not spend semantic-probe calls enriching a plan that Integration must
        # reject before canonical mutation.
        if plan.candidate_ir.discourse_refs:
            return plan

        boundary_relations = self._boundary_discourse_relations(plan)
        if not boundary_relations:
            return plan

        perception = replace(
            plan.perception,
            relations=tuple((*plan.perception.relations, *boundary_relations)),
        )
        return self.services.integration.prepare_external_plan(
            perception,
            self.services.context,
            batch_kind=plan.candidate_ir.batch_kind,
            source_ref=plan.candidate_ir.source_ref,
            source_timestamp=plan.candidate_ir.source_timestamp,
            existing_experience_ref=plan.existing_experience_ref,
        )

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
        diagnostics: list[DocumentSliceDiagnostic] = []
        partials: list[str] = []
        workspace_seen: list[str] = []
        last_slice_context = None

        try:
            with self.services.operation_lock:
                source_primary_total = len(
                    scoped.activator.resolver.resolve(source_ref).semantic_roots
                )
        except Exception as exc:
            _remember_progress(
                source_ref,
                (),
                source_primary_total=0,
                stop_reason="source_scope_failed",
                estimated_tokens=0,
                failure=_failure_text(exc),
            )
            raise

        cursor = SourceProjectionCursor(source_ref, 0)
        _remember_progress(
            source_ref,
            (),
            source_primary_total=source_primary_total,
            stop_reason="running",
            estimated_tokens=0,
        )

        for slice_index in range(1, max_slices + 1):
            try:
                with self.services.operation_lock:
                    sliced, result = scoped.build_source_slice(
                        request,
                        cursor,
                        max_primary_roots=max_primary_roots,
                        settle_ticks=settle_ticks,
                        budget_tokens=budget_tokens,
                    )
            except ProjectionBudgetExceeded as exc:
                _remember_progress(
                    source_ref,
                    tuple(diagnostics),
                    source_primary_total=source_primary_total,
                    stop_reason="slice_budget_exceeded",
                    estimated_tokens=exc.estimated_tokens,
                    failure=_failure_text(exc),
                )
                raise
            except Exception as exc:
                _remember_progress(
                    source_ref,
                    tuple(diagnostics),
                    source_primary_total=source_primary_total,
                    stop_reason="slice_projection_failed",
                    estimated_tokens=(
                        0 if last_slice_context is None else last_slice_context.estimated_tokens
                    ),
                    failure=_failure_text(exc),
                )
                raise

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
            try:
                partial = self.services.agent.respond(result.context)
            except Exception as exc:
                _remember_progress(
                    source_ref,
                    tuple(diagnostics),
                    source_primary_total=source_primary_total,
                    stop_reason="slice_generation_failed",
                    estimated_tokens=result.context.estimated_tokens,
                    failure=_failure_text(exc),
                )
                raise
            partials.append(partial)
            cursor = sliced.next_cursor
            if sliced.done:
                break
        else:
            message = (
                f"Document summary exceeded max_slices={max_slices} "
                "before source cursor reached done"
            )
            _remember_progress(
                source_ref,
                tuple(diagnostics),
                source_primary_total=source_primary_total,
                stop_reason="max_slices_exceeded",
                estimated_tokens=(
                    0 if last_slice_context is None else last_slice_context.estimated_tokens
                ),
                failure=message,
            )
            raise DocumentProcessingError(message)

        if last_slice_context is None or not partials:
            message = "Document source projection produced no semantic slice"
            _remember_progress(
                source_ref,
                tuple(diagnostics),
                source_primary_total=source_primary_total,
                stop_reason="empty_source_projection",
                estimated_tokens=0,
                failure=message,
            )
            raise DocumentProcessingError(message)

        if len(partials) == 1:
            text = partials[0]
            final_context = last_slice_context
        else:
            try:
                text, final_context = self._reduce_partial_results(
                    source_ref,
                    request,
                    tuple(partials),
                    budget_tokens=budget_tokens,
                )
            except ProjectionBudgetExceeded as exc:
                _remember_progress(
                    source_ref,
                    tuple(diagnostics),
                    source_primary_total=source_primary_total,
                    stop_reason="aggregation_budget_exceeded",
                    estimated_tokens=exc.estimated_tokens,
                    failure=_failure_text(exc),
                )
                raise
            except Exception as exc:
                _remember_progress(
                    source_ref,
                    tuple(diagnostics),
                    source_primary_total=source_primary_total,
                    stop_reason="aggregation_failed",
                    estimated_tokens=(
                        0 if last_slice_context is None else last_slice_context.estimated_tokens
                    ),
                    failure=_failure_text(exc),
                )
                raise

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
