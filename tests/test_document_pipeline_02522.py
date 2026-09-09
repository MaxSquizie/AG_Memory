from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from threading import RLock

import pytest

from ah.agent import InteractionContext
from ah.config import ContextSettings, IgnitionSettings, LifecycleSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.documents import DocumentProcessingError, DocumentProcessor
from ah.ignition import IgnitionEngine
from ah.integration import BatchKind
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, Domain, Property
from ah.perception import PerceptionResult
from ah.projection import AgentContext, ContextProjector


class FakePerception:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.inputs: list[str] = []
        self.fail_at = fail_at

    def parse(self, text, _context):
        self.inputs.append(text)
        if self.fail_at == len(self.inputs):
            raise RuntimeError("parse failure")
        return PerceptionResult(text)


class FakeIntegration:
    def __init__(self) -> None:
        self.batches = []

    def template_requests(self, _result):
        return ()

    def integrate_external_batch(self, batch, _context):
        self.batches.append(batch)
        return SimpleNamespace(activation_seeds=("seed",), refutations=("refute",))


class FakeIgnition:
    def __init__(self) -> None:
        self.seeds = []
        self.refutations = []

    def apply_seed_requests(self, values):
        self.seeds.extend(values)

    def apply_refutation_requests(self, values):
        self.refutations.extend(values)


def fake_services(perception=None):
    return SimpleNamespace(
        perception=perception or FakePerception(),
        integration=FakeIntegration(),
        ignition=FakeIgnition(),
        context=InteractionContext(),
        operation_lock=RLock(),
    )


def test_chunking_is_contiguous_and_reconstructs_the_exact_normalized_source():
    processor = DocumentProcessor(fake_services(), max_chunk_chars=256)
    text = ("Первый абзац содержит связное описание.\n\n" * 20) + "Финал."
    chunks = processor.chunk_text(text)
    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks) == text
    assert chunks[0].start == 0 and chunks[-1].end == len(text)
    assert all(left.end == right.start for left, right in zip(chunks, chunks[1:]))


def test_document_source_id_is_deterministic_and_content_sensitive():
    assert DocumentProcessor.source_id("abc", "title") == DocumentProcessor.source_id("abc", "title")
    assert DocumentProcessor.source_id("abc", "title") != DocumentProcessor.source_id("abd", "title")


def test_ingestion_parses_all_windows_then_commits_one_document_batch_with_offsets_and_timestamp():
    services = fake_services()
    processor = DocumentProcessor(services, max_chunk_chars=256)
    timestamp = datetime(2026, 9, 8, 10, 30, tzinfo=timezone.utc)
    result = processor.ingest_text(
        "Длинный документ. " * 100,
        title="Документ",
        source_ref="doc:test",
        source_timestamp=timestamp,
    )
    assert len(services.integration.batches) == 1
    batch = services.integration.batches[0]
    assert batch.batch_kind is BatchKind.DOCUMENT
    assert batch.source_ref == "doc:test"
    assert batch.source_timestamp == timestamp
    assert batch.unit_offsets == tuple(chunk.start for chunk in result.chunks)
    assert len(batch.units) == len(result.chunks) == len(services.perception.inputs)
    assert result.coverage_ratio == 1.0
    assert services.ignition.seeds == ["seed"]
    assert services.ignition.refutations == ["refute"]


def test_parse_failure_is_fail_closed_before_any_canonical_batch_write():
    services = fake_services(FakePerception(fail_at=2))
    processor = DocumentProcessor(services, max_chunk_chars=256)
    with pytest.raises(RuntimeError, match="parse failure"):
        processor.ingest_text("Фрагмент документа. " * 100)
    assert services.integration.batches == []


def test_ingest_file_uses_file_mtime_as_aware_source_anchor(tmp_path: Path):
    path = tmp_path / "article.md"
    path.write_text("Материал статьи. " * 30, encoding="utf-8")
    services = fake_services()
    DocumentProcessor(services, max_chunk_chars=256).ingest_file(path)
    timestamp = services.integration.batches[0].source_timestamp
    assert timestamp is not None and timestamp.tzinfo is not None


def _source_services():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.ref(core.add_entity(Domain.P, {"name": Property("name", "USER", "str")}).uid)
    subject = core.ref(core.add_entity(Domain.C, {"name": Property("name", "Датчик", "str")}).uid)
    obj = core.ref(core.add_entity(Domain.C, {"name": Property("name", "Сигнал", "str")}).uid)
    symbol = core.ensure_abstract_symbol("обнаружить")
    template = core.add_template(Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.OBJECT))
    node, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: subject, ActantRole.OBJECT: obj},
        0.4,
    )
    fact = core.ref(node.uid)
    context = InteractionContext(user_ref=user)
    ExperienceMapper(core, event_weight=0.3, follow_weight=0.2).record_turn(
        source_text="SECRET RAW DOCUMENT",
        speaker_ref=user,
        semantic_refs=(fact,),
        context=context,
        speech_act_kinds=("ASSERTION",),
        source_ref="doc:memory",
        batch_kind="DOCUMENT",
    )
    ignition = IgnitionEngine(
        core, IgnitionSettings(), WorkspaceSettings(threshold=0.35), LifecycleSettings(gc_enabled=False)
    )
    return SimpleNamespace(
        core=core,
        ignition=ignition,
        projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
        operation_lock=RLock(),
        agent=None,
    )


def test_build_context_and_summary_pass_only_frozen_ah_context_to_agent():
    services = _source_services()
    processor = DocumentProcessor(services)
    context = processor.build_context("doc:memory", request="Перескажи.")
    assert "обнаружить" in context.rendered_context
    assert "SECRET RAW DOCUMENT" not in context.rendered_context

    class CapturingAgent:
        def __init__(self):
            self.seen = None

        def respond(self, value):
            self.seen = value
            return "Краткое содержание"

    services.agent = CapturingAgent()
    summary = processor.summarize("doc:memory", request="Перескажи.")
    assert summary.text == "Краткое содержание"
    assert isinstance(services.agent.seen, AgentContext)
    assert not hasattr(services.agent.seen, "source_text")
    assert "SECRET RAW DOCUMENT" not in services.agent.seen.rendered


def test_empty_and_unsupported_documents_fail_explicitly(tmp_path: Path):
    with pytest.raises(DocumentProcessingError, match="empty"):
        DocumentProcessor(fake_services()).chunk_text("  \n")
    path = tmp_path / "archive.pdf"
    path.write_bytes(b"not a document")
    with pytest.raises(DocumentProcessingError, match="Unsupported"):
        DocumentProcessor.load_text(path)
