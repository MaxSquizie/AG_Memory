from __future__ import annotations

from types import SimpleNamespace
from threading import RLock

import pytest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.documents import DocumentProcessingError, DocumentProcessor
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    DiscourseRelationDecision,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.morphology import NullMorphology


class _Perception:
    def __init__(self, results, decisions) -> None:
        self.results = list(results)
        self.decisions = list(decisions)
        self.discourse_calls = []

    def parse(self, text, _context):
        if not self.results:
            raise AssertionError(f"unexpected parse window: {text!r}")
        result = self.results.pop(0)
        assert result.source_text == text
        return result

    def classify_discourse_relation(
        self,
        narrative_context,
        prior_events,
        current_events,
        *,
        excluded_pairs=(),
    ):
        self.discourse_calls.append(
            (narrative_context, tuple(prior_events), tuple(current_events), tuple(excluded_pairs))
        )
        if not self.decisions:
            return None
        return self.decisions.pop(0)


class _Ignition:
    def apply_seed_requests(self, _values):
        pass

    def apply_refutation_requests(self, _values):
        pass


def _long(sentence: str) -> str:
    assert sentence.endswith(".")
    filler = "подробно описывая обстоятельства произошедшего " * 2
    result = sentence[:-1] + " " + filler.strip() + "."
    assert len(result) < 256
    return result


def _assertion(source_text: str, predicate: str, lemma: str, predicate_start: int, predicate_end: int, *, leading: int):
    return AssertionCandidate(
        "A1",
        PredicateCandidate(
            predicate,
            lemma,
            evidence=EvidenceSpan(predicate, predicate_start, predicate_end),
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Иван",
                normalized_hint="Иван",
                entity_ref="E1",
                evidence=EvidenceSpan("Иван", leading, leading + 4),
            ),
        ),
        evidence=EvidenceSpan(source_text, 0, len(source_text)),
    )


def _runtime(relation_id: str, *, invalid_index: bool = False):
    first = _long(
        "Иван прибыл в порт и остановился у дальнего причала рядом с большим грузовым складом."
    )
    second = _long(
        "Иван вошёл в здание и закрыл за собой тяжёлую металлическую дверь у внутреннего коридора."
    )
    source = first + " " + second
    chunks = DocumentProcessor(SimpleNamespace(), max_chunk_chars=256).chunk_text(source)
    assert len(chunks) == 2
    assert chunks[0].text == first
    assert chunks[1].text == " " + second

    first_result = PerceptionResult(
        chunks[0].text,
        assertions=(
            _assertion(
                chunks[0].text,
                "прибыл",
                "прибыть",
                5,
                11,
                leading=0,
            ),
        ),
    )
    second_result = PerceptionResult(
        chunks[1].text,
        assertions=(
            _assertion(
                chunks[1].text,
                "вошёл",
                "войти",
                6,
                11,
                leading=1,
            ),
        ),
    )

    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "USER", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "AGENT", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    integration = IntegrationService(
        core,
        IntegrationConfig(0.4, 0.3, 0.02),
        discourse_morphology=NullMorphology(),
    )
    decision = DiscourseRelationDecision(
        relation_id,
        9 if invalid_index else 0,
        0,
    )
    perception = _Perception((first_result, second_result), (decision,))
    services = SimpleNamespace(
        core=core,
        context=context,
        integration=integration,
        perception=perception,
        ignition=_Ignition(),
        operation_lock=RLock(),
    )
    return source, services, DocumentProcessor(services, max_chunk_chars=256), perception


@pytest.mark.parametrize("relation_id", ["CAUSE", "FOLLOW"])
def test_cross_chunk_discourse_relation_is_revalidated_and_committed_atomically(relation_id: str):
    source, services, processor, perception = _runtime(relation_id)

    result = processor.ingest_text(source, source_ref=f"doc:{relation_id.casefold()}")

    assert len(result.integration.assertions) == 2
    assert len(result.integration.relations) == 1
    relation = result.integration.relations[0]
    assert relation.relation_id == relation_id
    assert relation.source == result.integration.assertions[0].ref
    assert relation.target == result.integration.assertions[1].ref
    assert services.core.store.find_link(
        relation_id,
        result.integration.assertions[0].ref.uid,
        result.integration.assertions[1].ref.uid,
    ) is not None

    experience = services.core.store.get_hypernode(result.integration.experience_ref.uid)
    assert experience.meta.get("batch_kind") == "DOCUMENT"
    assert experience.meta.get("source_ref") == f"doc:{relation_id.casefold()}"

    assert len(perception.discourse_calls) == 1
    narrative, prior, current, excluded = perception.discourse_calls[0]
    assert narrative == source
    assert excluded == ()
    assert prior == ("прибыть(SUBJECT=Иван)",)
    assert current == ("войти(SUBJECT=Иван)",)
    assert all("N_" not in text and "M_" not in text for text in (*prior, *current))


def test_invalid_boundary_probe_decision_fails_before_any_document_commit():
    source, services, processor, _perception = _runtime("CAUSE", invalid_index=True)
    before = set(services.core.store.all_uids())

    with pytest.raises(DocumentProcessingError, match="finite candidate set"):
        processor.ingest_text(source, source_ref="doc:invalid-boundary")

    assert set(services.core.store.all_uids()) == before
    assert services.core.store.find_entities_by_name("Иван", Domain.C) == ()
