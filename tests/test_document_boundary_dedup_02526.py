from __future__ import annotations

from types import SimpleNamespace

from ah.documents import DocumentProcessor
from ah.model import ActantRole
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)


class _CapturingPerception:
    def __init__(self) -> None:
        self.calls = []

    def classify_discourse_relation(
        self,
        narrative_context,
        prior_events,
        current_events,
        *,
        excluded_pairs=(),
    ):
        self.calls.append(
            (narrative_context, tuple(prior_events), tuple(current_events), tuple(excluded_pairs))
        )
        return None


def _assertion(local_id: str, source: str, start: int, predicate: str, lemma: str):
    subject_start = source.index("Иван")
    predicate_start = source.index(predicate)
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            lemma,
            evidence=EvidenceSpan(predicate, start + predicate_start, start + predicate_start + len(predicate)),
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Иван",
                normalized_hint="Иван",
                entity_ref=f"E:{local_id}",
                evidence=EvidenceSpan("Иван", start + subject_start, start + subject_start + 4),
            ),
        ),
        evidence=EvidenceSpan(source, start, start + len(source)),
        status=AssertionStatus.ASSERTED,
    )


def test_boundary_probe_excludes_semantic_duplicate_repeated_in_later_chunk():
    first = (
        "Иван прибыл в порт и остановился у дальнего причала, подробно описывая "
        "обстоятельства произошедшего и ожидая дальнейших указаний диспетчера."
    )
    second = (
        " Иван прибыл в порт. Иван вошёл в здание после ожидания у ворот, подробно "
        "описывая обстоятельства произошедшего и закрывая за собой тяжёлую дверь."
    )
    source = first + second
    processor_for_chunks = DocumentProcessor(SimpleNamespace(), max_chunk_chars=256)
    chunks = processor_for_chunks.chunk_text(source)
    assert len(chunks) == 2
    assert chunks[0].text == first
    assert chunks[1].text == second

    prior = _assertion("B0:A1", first, 0, "прибыл", "прибыть")
    duplicate = _assertion("B1:A1", second, len(first), "прибыл", "прибыть")
    current = _assertion("B1:A2", second, len(first), "вошёл", "войти")
    perception = _CapturingPerception()
    services = SimpleNamespace(perception=perception)
    processor = DocumentProcessor(services, max_chunk_chars=256)
    plan = SimpleNamespace(
        perception=PerceptionResult(source, assertions=(prior, duplicate, current))
    )

    additions = processor._boundary_discourse_relations(plan)

    assert additions == ()
    assert len(perception.calls) == 1
    _narrative, prior_events, current_events, excluded = perception.calls[0]
    assert prior_events == ("прибыть(SUBJECT=Иван)",)
    assert current_events == ("войти(SUBJECT=Иван)",)
    assert excluded == ()
