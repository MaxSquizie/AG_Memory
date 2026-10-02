from __future__ import annotations

from types import SimpleNamespace

from ah.documents import DocumentProcessor
from ah.integration import DiscourseRef
from ah.model import ActantRole
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)


class _Perception:
    def __init__(self) -> None:
        self.discourse_calls = 0

    def classify_discourse_relation(self, *args, **kwargs):
        self.discourse_calls += 1
        raise AssertionError("boundary discourse probe must not run for unresolved coreference")


class _Integration:
    def bind_discourse_ref(self, *args, **kwargs):
        raise AssertionError("ambiguous discourse ref must not be guessed")


def test_unresolved_coreference_stops_document_enrichment_before_boundary_probe():
    source = (
        "Он вошёл в здание после ожидания у ворот и спокойно закрыл тяжёлую дверь. "
        "Иван прибыл в порт после полудня и Петр встретил его возле дальнего причала."
    )
    assertion = AssertionCandidate(
        "B0:A1",
        PredicateCandidate(
            "вошёл",
            "войти",
            evidence=EvidenceSpan("вошёл", 3, 8),
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Он",
                normalized_hint="он",
                evidence=EvidenceSpan("Он", 0, 2),
            ),
        ),
    )
    unresolved = DiscourseRef(
        local_id="D:B0:A1:SUBJECT:0",
        mention="Он",
        assertion_id="B0:A1",
        role=ActantRole.SUBJECT,
        grammatical_number="sing",
        grammatical_gender="masc",
        source_start=0,
        source_end=2,
        candidate_entity_refs=("B1:E1", "B1:E2"),
    )
    plan = SimpleNamespace(
        perception=PerceptionResult(source, assertions=(assertion,)),
        candidate_ir=SimpleNamespace(discourse_refs=(unresolved,)),
    )
    perception = _Perception()
    processor = DocumentProcessor(
        SimpleNamespace(
            perception=perception,
            integration=_Integration(),
            context=SimpleNamespace(),
        ),
        max_chunk_chars=256,
    )

    result = processor._resolve_batch_discourse_refs(plan)

    assert result is plan
    assert perception.discourse_calls == 0
    assert result.candidate_ir.discourse_refs == (unresolved,)
