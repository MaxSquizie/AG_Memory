from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from ah.integration import BatchKind, FormalizationBatch, TemplateCompletionService
from ah.perception import PerceptionResult
from ah.projection import AgentContext, SourceScopeActivator, SourceScopedContextService

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
class DocumentSummary:
    source_ref: str
    request: str
    text: str
    rendered_context: str
    workspace_refs: tuple[str, ...]
    estimated_tokens: int


class DocumentProcessor:
    """Ingest a whole document through the existing formalization pipeline.

    Chunks are operational perception windows only. Every window is parsed and
    template-completed before one ``FormalizationBatch(DOCUMENT)`` is submitted to
    the one canonical transaction. Summary input is frozen AH projection, never
    raw source or raw chunks.
    """

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

    def chunk_text(self, text: str) -> tuple[DocumentChunk, ...]:
        if not text.strip():
            raise DocumentProcessingError("Document text is empty")
        chunks: list[DocumentChunk] = []
        start = 0
        while start < len(text):
            hard_end = min(len(text), start + self.max_chunk_chars)
            end = hard_end
            if hard_end < len(text):
                boundary = max(
                    text.rfind("\n\n", start, hard_end),
                    text.rfind("\n", start, hard_end),
                    text.rfind(" ", start, hard_end),
                )
                if boundary > start + self.max_chunk_chars // 2:
                    end = boundary
            if end <= start:
                raise DocumentProcessingError("Chunking produced an empty chunk")
            chunks.append(DocumentChunk(len(chunks), text[start:end], start, end))
            start = end
        if "".join(chunk.text for chunk in chunks) != text:
            raise DocumentProcessingError("Document chunk coverage invariant failed")
        return tuple(chunks)

    def _resolve_batch_discourse_refs(self, plan):
        """Bind only uniquely compatible prior document anchors before commit.

        CandidateIR already exposes grammatical compatibility without choosing an
        antecedent.  Document chunks are operational windows, so here we use their
        global source offsets to reject future mentions.  A pronoun is grounded
        only when exactly one compatible entity handle has appeared earlier in the
        same document; multiple prior candidates remain explicit DiscourseRef and
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

    def build_context(
        self,
        source_ref: str,
        *,
        request: str = "Сделай краткое содержание документа в 5–7 предложениях.",
        settle_ticks: int = 1,
        budget_tokens: int | None = None,
    ) -> DocumentContext:
        scoped = SourceScopedContextService(
            SourceScopeActivator(self.services.core, self.services.ignition),
            self.services.projector,
        )
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

    def summarize(
        self,
        source_ref: str,
        *,
        request: str = "Сделай краткое содержание документа в 5–7 предложениях.",
        settle_ticks: int = 1,
        budget_tokens: int | None = None,
    ) -> DocumentSummary:
        if self.services.agent is None:
            raise DocumentProcessingError(
                "LLM agent is disabled; memory-grounded summary requires the agent"
            )
        context = self.build_context(
            source_ref,
            request=request,
            settle_ticks=settle_ticks,
            budget_tokens=budget_tokens,
        )
        # This is the only object handed to the response model; it contains no raw
        # source/chunk field.
        text = self.services.agent.respond(context.agent_context)
        return DocumentSummary(
            source_ref=source_ref,
            request=request,
            text=text,
            rendered_context=context.rendered_context,
            workspace_refs=context.workspace_refs,
            estimated_tokens=context.estimated_tokens,
        )
