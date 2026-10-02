from __future__ import annotations

from types import SimpleNamespace
from threading import RLock

import pytest

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.documents import DocumentProcessor
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.errors import UnresolvedDiscourseReferenceError
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
    TemplateSelection,
)
from ah.perception.morphology import MorphInfo


class _Morphology:
    def analyze_all(self, word: str):
        key = word.strip().casefold().replace("ё", "е")
        values = {
            "он": (
                MorphInfo(
                    "он",
                    "NPRO",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    grammemes=frozenset({"NPRO", "3per"}),
                    score=1.0,
                ),
            ),
            "иван": (
                MorphInfo(
                    "Иван",
                    "NOUN",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    score=1.0,
                ),
            ),
            "петр": (
                MorphInfo(
                    "Петр",
                    "NOUN",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    score=1.0,
                ),
            ),
            "петра": (
                MorphInfo(
                    "Петр",
                    "NOUN",
                    case="gent",
                    number="sing",
                    gender="masc",
                    score=1.0,
                ),
            ),
        }
        return values.get(key, ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class _ScriptedPerception:
    def __init__(self, results: tuple[PerceptionResult, ...]) -> None:
        self.results = list(results)
        self.inputs: list[str] = []

    def parse(self, text: str, _context):
        self.inputs.append(text)
        if not self.results:
            raise AssertionError(f"unexpected perception window: {text!r}")
        result = self.results.pop(0)
        assert result.source_text == text
        return result


class _Ignition:
    def __init__(self) -> None:
        self.seeds = []
        self.refutations = []

    def apply_seed_requests(self, values):
        self.seeds.extend(values)

    def apply_refutation_requests(self, values):
        self.refutations.extend(values)


def _runtime(results: tuple[PerceptionResult, ...]):
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "USER", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "AGENT", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    integration = IntegrationService(
        core,
        IntegrationConfig(0.4, 0.3, 0.02),
        discourse_morphology=_Morphology(),
    )
    services = SimpleNamespace(
        core=core,
        context=context,
        integration=integration,
        perception=_ScriptedPerception(results),
        ignition=_Ignition(),
        operation_lock=RLock(),
    )
    return services, DocumentProcessor(services, max_chunk_chars=256)


def _long(sentence: str) -> str:
    assert sentence.endswith(".")
    filler = "подробно описывая обстоятельства произошедшего " * 2
    value = sentence[:-1] + " " + filler.strip() + "."
    assert len(value) < 256
    return value


def _two_chunks(first: str, second: str):
    source = first + " " + second
    assert len(source) > 256
    chunks = DocumentProcessor(SimpleNamespace(), max_chunk_chars=256).chunk_text(source)
    assert len(chunks) == 2
    assert chunks[0].text == first
    assert chunks[1].text == " " + second
    return source, chunks


def _subject_assertion(
    source_text: str,
    *,
    local_id: str,
    predicate_surface: str,
    predicate_lemma: str,
    predicate_start: int,
    predicate_end: int,
    mention: str,
    normalized_hint: str,
    actant_start: int,
    actant_end: int,
    entity_ref: str | None,
    template_selection: TemplateSelection | None = None,
):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate_surface,
            predicate_lemma,
            evidence=EvidenceSpan(predicate_surface, predicate_start, predicate_end),
            template_candidate=(
                None
                if template_selection is not None
                else TemplateCandidate((ActantRole.SUBJECT,))
            ),
            template_selection=template_selection,
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention=mention,
                normalized_hint=normalized_hint,
                entity_ref=entity_ref,
                evidence=EvidenceSpan(mention, actant_start, actant_end),
            ),
        ),
        evidence=EvidenceSpan(source_text, 0, len(source_text)),
    )


def test_ingest_text_binds_unique_backward_coreference_before_single_document_commit():
    first = _long(
        "Иван прибыл в порт, где долго ждал разрешения на вход и спокойно наблюдал "
        "за разгрузкой большого судна у дальнего причала."
    )
    second = _long(
        "Он вошёл в здание после долгого ожидания у ворот и затем спокойно закрыл "
        "за собой тяжёлую металлическую дверь."
    )
    source, chunks = _two_chunks(first, second)
    first_result = PerceptionResult(
        chunks[0].text,
        assertions=(
            _subject_assertion(
                chunks[0].text,
                local_id="A1",
                predicate_surface="прибыл",
                predicate_lemma="прибыть",
                predicate_start=5,
                predicate_end=11,
                mention="Иван",
                normalized_hint="Иван",
                actant_start=0,
                actant_end=4,
                entity_ref="E1",
            ),
        ),
    )
    second_result = PerceptionResult(
        chunks[1].text,
        assertions=(
            _subject_assertion(
                chunks[1].text,
                local_id="A1",
                predicate_surface="вошёл",
                predicate_lemma="войти",
                predicate_start=4,
                predicate_end=9,
                mention="Он",
                normalized_hint="он",
                actant_start=1,
                actant_end=3,
                entity_ref=None,
            ),
        ),
    )
    services, processor = _runtime((first_result, second_result))

    result = processor.ingest_text(source, source_ref="doc:backward")

    assert len(result.chunks) == 2
    assert tuple(item.local_id for item in result.integration.assertions) == ("B0:A1", "B1:A1")
    first_node = services.core.store.get_hypernode(result.integration.assertions[0].ref.uid)
    second_node = services.core.store.get_hypernode(result.integration.assertions[1].ref.uid)
    assert first_node.actants[ActantRole.SUBJECT] == second_node.actants[ActantRole.SUBJECT]
    assert len(services.core.store.find_entities_by_name("Иван", Domain.C)) == 1
    experience = services.core.store.get_hypernode(result.integration.experience_ref.uid)
    assert experience.meta.get("source_ref") == "doc:backward"
    assert experience.meta.get("batch_kind") == "DOCUMENT"


def test_ingest_text_rejects_future_only_antecedent_without_any_canonical_leak():
    first = _long(
        "Он вошёл в здание после долгого ожидания у ворот и затем спокойно закрыл "
        "за собой тяжёлую металлическую дверь."
    )
    second = _long(
        "Иван прибыл в порт, где долго ждал разрешения на вход и спокойно наблюдал "
        "за разгрузкой большого судна у дальнего причала."
    )
    source, chunks = _two_chunks(first, second)
    first_result = PerceptionResult(
        chunks[0].text,
        assertions=(
            _subject_assertion(
                chunks[0].text,
                local_id="A1",
                predicate_surface="вошёл",
                predicate_lemma="войти",
                predicate_start=3,
                predicate_end=8,
                mention="Он",
                normalized_hint="он",
                actant_start=0,
                actant_end=2,
                entity_ref=None,
            ),
        ),
    )
    second_result = PerceptionResult(
        chunks[1].text,
        assertions=(
            _subject_assertion(
                chunks[1].text,
                local_id="A1",
                predicate_surface="прибыл",
                predicate_lemma="прибыть",
                predicate_start=6,
                predicate_end=12,
                mention="Иван",
                normalized_hint="Иван",
                actant_start=1,
                actant_end=5,
                entity_ref="E1",
            ),
        ),
    )
    services, processor = _runtime((first_result, second_result))
    before = set(services.core.store.all_uids())

    with pytest.raises(UnresolvedDiscourseReferenceError):
        processor.ingest_text(source, source_ref="doc:future")

    assert set(services.core.store.all_uids()) == before
    assert services.core.store.find_entities_by_name("Иван", Domain.C) == ()


def test_ingest_text_rejects_multiple_backward_antecedents_without_guessing():
    first = _long(
        "Иван встретил Петра у ворот большого склада и долго обсуждал с ним порядок "
        "разгрузки прибывшего утром грузового автомобиля."
    )
    second = _long(
        "Он вошёл в здание после разговора у ворот и затем спокойно закрыл за собой "
        "тяжёлую металлическую дверь."
    )
    source, chunks = _two_chunks(first, second)
    meet = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "встретил",
            "встретить",
            evidence=EvidenceSpan("встретил", 5, 13),
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Иван",
                normalized_hint="Иван",
                entity_ref="E1",
                evidence=EvidenceSpan("Иван", 0, 4),
            ),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="Петра",
                normalized_hint="Петр",
                entity_ref="E2",
                evidence=EvidenceSpan("Петра", 14, 19),
            ),
        ),
        evidence=EvidenceSpan(chunks[0].text, 0, len(chunks[0].text)),
    )
    pronoun = _subject_assertion(
        chunks[1].text,
        local_id="A1",
        predicate_surface="вошёл",
        predicate_lemma="войти",
        predicate_start=4,
        predicate_end=9,
        mention="Он",
        normalized_hint="он",
        actant_start=1,
        actant_end=3,
        entity_ref=None,
    )
    services, processor = _runtime(
        (
            PerceptionResult(chunks[0].text, assertions=(meet,)),
            PerceptionResult(chunks[1].text, assertions=(pronoun,)),
        )
    )
    before = set(services.core.store.all_uids())

    with pytest.raises(UnresolvedDiscourseReferenceError):
        processor.ingest_text(source, source_ref="doc:ambiguous")

    assert set(services.core.store.all_uids()) == before
    assert services.core.store.find_entities_by_name("Иван", Domain.C) == ()
    assert services.core.store.find_entities_by_name("Петр", Domain.C) == ()


def test_late_canonical_failure_rolls_back_all_document_units():
    first = _long(
        "Иван прибыл в порт, где долго ждал разрешения на вход и спокойно наблюдал "
        "за разгрузкой большого судна у дальнего причала."
    )
    second = _long(
        "Иван вошёл в здание после ожидания у ворот и затем спокойно закрыл за собой "
        "тяжёлую металлическую дверь."
    )
    source, chunks = _two_chunks(first, second)
    good = _subject_assertion(
        chunks[0].text,
        local_id="A1",
        predicate_surface="прибыл",
        predicate_lemma="прибыть",
        predicate_start=5,
        predicate_end=11,
        mention="Иван",
        normalized_hint="Иван",
        actant_start=0,
        actant_end=4,
        entity_ref="E1",
    )
    bad = _subject_assertion(
        chunks[1].text,
        local_id="A1",
        predicate_surface="вошёл",
        predicate_lemma="войти",
        predicate_start=6,
        predicate_end=11,
        mention="Иван",
        normalized_hint="Иван",
        actant_start=1,
        actant_end=5,
        entity_ref="E1",
        template_selection=TemplateSelection(existing_template_uid="T_MISSING"),
    )
    services, processor = _runtime(
        (
            PerceptionResult(chunks[0].text, assertions=(good,)),
            PerceptionResult(chunks[1].text, assertions=(bad,)),
        )
    )
    before = set(services.core.store.all_uids())

    with pytest.raises(Exception):
        processor.ingest_text(source, source_ref="doc:late-failure")

    assert set(services.core.store.all_uids()) == before
    assert services.core.store.find_entities_by_name("Иван", Domain.C) == ()
