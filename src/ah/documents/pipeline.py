from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import TYPE_CHECKING

from ah.integration import BatchKind, FormalizationBatch, TemplateCompletionService
from ah.perception import PerceptionResult
from ah.projection import (
    AgentContext,
    ProjectionBudgetExceeded,
    SourceProjectionCursor,
    SourceScopeActivator,
    SourceScopedContextService,
)

if TYPE_CHECKING:
    from ah.bootstrap import RuntimeServices


class DocumentProcessingError(RuntimeError):
    """Fail-closed document ingestion error."""


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    index: int
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class DocumentIngestionResult:
    source_ref: str
    title: str
    source_text: str
    chunks: tuple[DocumentChunk, ...]
    perception_units: tuple[PerceptionResult, ...]
    integration: object

    @property
    def coverage_chars(self) -> int:
        return sum(chunk.end - chunk.start for chunk in self.chunks)

    @property
    def coverage_ratio(self) -> float:
        return 1.0 if not self.source_text else self.coverage_chars / len(self.source_text)


@dataclass(frozen=True, slots=True)
class DocumentContext:
    source_ref: str
    request: str
    agent_context: AgentContext
    workspace_refs: tuple[str, ...]

    @property
    def rendered_context(self) -> str:
        return self.agent_context.rendered

    @property
    def estimated_tokens(self) -> int:
        return self.agent_context.estimated_tokens


@dataclass(frozen=True, slots=True)
class DocumentSliceDiagnostic:
    """Runtime-only progress record for one bounded source projection slice."""

    slice_index: int
    cursor_start: int
    cursor_end: int
    primary_refs: tuple[str, ...]
    overlap_refs: tuple[str, ...]
    workspace_refs: tuple[str, ...]
    estimated_tokens: int
    done: bool


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    source_ref: str
    request: str
    text: str
    rendered_context: str
    workspace_refs: tuple[str, ...]
    estimated_tokens: int
    slice_diagnostics: tuple[DocumentSliceDiagnostic, ...] = ()
    stop_reason: str = "complete"


class DocumentProcessor:
    """Ingest and project a whole document without raw-text response shortcuts.

    Chunks are operational perception windows only. Every window is parsed and
    template-completed before one ``FormalizationBatch(DOCUMENT)`` is submitted to
    the one canonical transaction. Summary input is frozen AH projection, never
    raw source or raw chunks. Large-source summarization advances over deterministic
    source-scope slices and aggregates only model results produced from those
    frozen AH contexts.
    """

    _SENTENCE_BOUNDARY_RE = re.compile(r"[.!?…](?:[\"'»”’)\]]+)?(?=\s|$)")
    _CLAUSE_BOUNDARY_RE = re.compile(r"[;:](?=\s|$)")

    def __init__(self, services: "RuntimeServices", *, max_chunk_chars: int = 6000) -> None:
        if max_chunk_chars < 256:
            raise ValueError("max_chunk_chars must be >= 256")
        self.services = services
        self.max_chunk_chars = int(max_chunk_chars)

    @staticmethod
    def source_id(text: str, title: str = "") -> str:
        payload = f"{title.strip()}\n{text}".encode("utf-8")
        return "document:" + hashlib.sha256(payload).hexdigest()[:24]

    @staticmethod
    def load_text(path: str | Path) -> str:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        suffix = source.suffix.casefold()
        if suffix in {".txt", ".md", ".markdown", ".text"}:
            return source.read_text(encoding="utf-8-sig")
        if suffix == ".docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise DocumentProcessingError("DOCX support requires python-docx") from exc
            document = Document(source)
            return "\n\n".join(paragraph.text for paragraph in document.paragraphs)
        raise DocumentProcessingError(
            f"Unsupported document format: {suffix or '<none>'}; use TXT, Markdown or DOCX"
        )

    @classmethod
    def _latest_structural_boundary(cls, text: str, start: int, hard_end: int) -> int | None:
        """Return the latest source-grounded boundary at or before ``hard_end``.

        Operational chunks may end at paragraph, line, sentence or explicit clause
        punctuation. Ordinary spaces are deliberately not boundaries: splitting at
        a random whitespace can sever a predicate from its frame or actants.
        """
        candidates: list[tuple[int, int]] = []
        window = text[start:hard_end]

        paragraph = window.rfind("\n\n")
        if paragraph >= 0:
            candidates.append((4, start + paragraph + 2))
        line = window.rfind("\n")
        if line >= 0:
            candidates.append((3, start + line + 1))
        for match in cls._SENTENCE_BOUNDARY_RE.finditer(window):
            candidates.append((2, start + match.end()))
        for match in cls._CLAUSE_BOUNDARY_RE.finditer(window):
            candidates.append((1, start + match.end()))

        viable = tuple(item for item in candidates if start < item[1] <= hard_end)
        if not viable:
            return None
        # Prefer the furthest safe point so chunks remain bounded and useful. The
        # structural rank is only a deterministic tie-break for coincident points.
        return max(viable, key=lambda item: (item[1], item[0]))[1]

    def chunk_text(self, text: str) -> tuple[DocumentChunk, ...]:
        if not text.strip():
            raise DocumentProcessingError("Document text is empty")
        chunks: list[DocumentChunk] = []
        start = 0
        while start < len(text):
            hard_end = min(len(text), start + self.max_chunk_chars)
            if hard_end == len(text):
                end = hard_end
            else:
                end = self._latest_structural_boundary(text, start, hard_end)
                if end is None:
                    raise DocumentProcessingError(
                        "Semantic unit exceeds max_chunk_chars without a source-grounded "
                        f"paragraph/sentence/clause boundary at source offset {start}; "
                        "document ingestion is fail-closed rather than splitting the unit"
                    )
            if end <= start:
                raise DocumentProcessingError("Chunking produced an empty chunk")
            chunks.append(DocumentChunk(len(chunks), text[start:end], start, end))
            start = end
        if "".join(chunk.text for chunk in chunks) != text:
            raise DocumentProcessingError("Document chunk coverage invariant failed")
        if any(left.end != right.start for left, right in zip(chunks, chunks[1:])):
            raise DocumentProcessingError("Document chunk offsets are not contiguous")
        return tuple(chunks)

    def _resolve_batch_discourse_refs(self, plan):
        """Bind only uniquely compatible prior document anchors before commit.

        CandidateIR already exposes grammatical compatibility without choosing an
        antecedent. Document chunks are operational windows, so here we use their
        global source offsets to reject future mentions. A pronoun is grounded only
        when exactly one compatible entity handle has appeared earlier in the same
        document; multiple prior candidates remain explicit ``DiscourseRef`` and
        Integration fails closed rather than guessing.
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
                plan, selected[0], selected[1], self.services.context
            )
        return plan

    def ingest_text(
        self,
        text: str,
        *,
        title: str = "",
        source_ref: str | None = None,
        source_timestamp: datetime | None = None,
    ) -> DocumentIngestionResult:
        perception = self.services.perception
        if perception is None:
            raise DocumentProcessingError(
                "LLM perception is disabled; document ingestion requires perception"
            )
        if source_timestamp is not None and source_timestamp.tzinfo is None:
            raise ValueError("source_timestamp must be timezone-aware")
        source_text = text.replace("\r\n", "\n").replace("\r", "\n")
        chunks = self.chunk_text(source_text)
        source_ref = source_ref or self.source_id(source_text, title)

        completion = TemplateCompletionService(self.services.integration, perception)
        units: list[PerceptionResult] = []
        # Complete every staging unit before the first canonical write.
        for chunk in chunks:
            units.append(completion.complete(perception.parse(chunk.text, self.services.context)))

        batch = FormalizationBatch(
            source_text=source_text,
            units=tuple(units),
            batch_kind=BatchKind.DOCUMENT,
            source_ref=source_ref,
            unit_offsets=tuple(chunk.start for chunk in chunks),
            source_timestamp=source_timestamp,
        )
        with self.services.operation_lock:
            commit = self.services.integration.integrate_external_batch(
                batch,
                self.services.context,
                plan_transform=self._resolve_batch_discourse_refs,
            )
            self.services.ignition.apply_seed_requests(commit.activation_seeds)
            self.services.ignition.apply_refutation_requests(commit.refutations)

        return DocumentIngestionResult(
            source_ref=source_ref,
            title=title.strip(),
            source_text=source_text,
            chunks=chunks,
            perception_units=tuple(units),
            integration=commit,
        )

    def ingest_file(
        self,
        path: str | Path,
        *,
        title: str | None = None,
        source_ref: str | None = None,
        source_timestamp: datetime | None = None,
    ) -> DocumentIngestionResult:
        source = Path(path)
        if source_timestamp is None:
            source_timestamp = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
        return self.ingest_text(
            self.load_text(source),
            title=title if title is not None else source.stem,
            source_ref=source_ref,
            source_timestamp=source_timestamp,
        )

    def _source_context_service(self) -> SourceScopedContextService:
        return SourceScopedContextService(
            SourceScopeActivator(self.services.core, self.services.ignition),
            self.services.projector,
        )

    def build_context(
        self,
        source_ref: str,
        *,
        request: str = "Сделай краткое содержание документа в 5–7 предложениях.",
        settle_ticks: int = 1,
        budget_tokens: int | None = None,
    ) -> DocumentContext:
        scoped = self._source_context_service()
        with self.services.operation_lock:
            result = scoped.build_complete_source(
                request,
                source_ref,
                settle_ticks=settle_ticks,
                budget_tokens=budget_tokens,
            )
        return DocumentContext(
            source_ref=source_ref,
            request=request,
            agent_context=result.context,
            workspace_refs=tuple(ref.uid for ref in result.activation.workspace_after),
        )

    @staticmethod
    def _aggregation_context(
        source_ref: str,
        request: str,
        partials: tuple[str, ...],
        *,
        budget_tokens: int | None,
    ) -> AgentContext:
        """Freeze an aggregation request containing only AH-derived partial results.

        The partials were produced from bounded frozen AgentContexts. They are not
        raw source text and do not grant the model a second retrieval channel.
        """
        body = "\n\n".join(
            f"[PART {index}]\n{text.strip()}" for index, text in enumerate(partials, 1)
        )
        aggregate_request = (
            f"{request}\n\n"
            "Ниже даны последовательные промежуточные результаты, каждый получен "
            "только из AH-проекции соответствующего фрагмента источника. Объедини "
            "их в один ответ, не добавляя фактов, которых нет в промежуточных результатах."
        )
        rendered = f"[CURRENT INPUT]\n{aggregate_request}\n\n[DOCUMENT PARTIALS]\n{body}"
        estimated_tokens = max(1, (len(rendered) + 3) // 4)
        if budget_tokens is not None and estimated_tokens > budget_tokens:
            raise ProjectionBudgetExceeded(estimated_tokens, budget_tokens)
        return AgentContext(
            current_input=aggregate_request,
            workspace_blocks=(),
            inference_blocks=(),
            rendered=rendered,
            source_scope_ref=source_ref,
            estimated_tokens=estimated_tokens,
        )

    def summarize(
        self,
        source_ref: str,
        *,
        request: str = "Сделай краткое содержание документа в 5–7 предложениях.",
        settle_ticks: int = 1,
        budget_tokens: int | None = None,
        max_primary_roots: int = 24,
        max_slices: int = 128,
    ) -> DocumentSummary:
        """Summarize a source through deterministic bounded AH-only continuation.

        Progress is the source cursor, not model state. Every canonical semantic root
        is primary exactly once; only already-seen causal/temporal neighbors may be
        repeated as overlap. The loop stops solely when ``SourceScopeSlice.done`` is
        true or fails closed at ``max_slices``. The final model call, when needed,
        sees only partial results derived from frozen AH contexts and never raw
        source/chunk text.
        """
        if self.services.agent is None:
            raise DocumentProcessingError(
                "LLM agent is disabled; memory-grounded summary requires the agent"
            )
        if max_primary_roots < 1:
            raise ValueError("max_primary_roots must be >= 1")
        if max_slices < 1:
            raise ValueError("max_slices must be >= 1")

        scoped = self._source_context_service()
        cursor = SourceProjectionCursor(source_ref, 0)
        diagnostics: list[DocumentSliceDiagnostic] = []
        partials: list[str] = []
        workspace_seen: list[str] = []
        last_context: AgentContext | None = None

        for slice_index in range(1, max_slices + 1):
            with self.services.operation_lock:
                sliced, result = scoped.build_source_slice(
                    request,
                    cursor,
                    max_primary_roots=max_primary_roots,
                    settle_ticks=settle_ticks,
                    budget_tokens=budget_tokens,
                )
            last_context = result.context
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

        if last_context is None or not partials:
            raise DocumentProcessingError("Document source projection produced no semantic slice")

        if len(partials) == 1:
            text = partials[0]
            final_context = last_context
        else:
            final_context = self._aggregation_context(
                source_ref,
                request,
                tuple(partials),
                budget_tokens=budget_tokens,
            )
            text = self.services.agent.respond(final_context)

        return DocumentSummary(
            source_ref=source_ref,
            request=request,
            text=text,
            rendered_context=final_context.rendered,
            workspace_refs=tuple(workspace_seen),
            estimated_tokens=final_context.estimated_tokens,
            slice_diagnostics=tuple(diagnostics),
            stop_reason="source_complete",
        )
