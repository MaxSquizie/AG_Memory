from __future__ import annotations

from pathlib import Path
import types

from ah.config import LLMRoleSettings
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.contracts import ActantCandidate, AssertionCandidate, EvidenceSpan, PredicateCandidate
from ah.perception.linguistic_candidates import EllipsisKind, LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "ellipsis-static"

    def __init__(self, data):
        self.data = {key.casefold(): tuple(value) for key, value in data.items()}

    def analyze_all(self, word: str):
        return self.data.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class NoModelBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected model call {role}:\n{prompt}")


def morphology():
    return StaticMorphology({
        "иван": (MorphInfo("иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "мария": (MorphInfo("мария", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "пётр": (MorphInfo("пётр", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "купил": (MorphInfo("купить", "VERB", number="sing", gender="masc", mood="indc", transitivity="tran", score=1.0),),
        "книгу": (MorphInfo("книга", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
        "журнал": (
            MorphInfo("журнал", "NOUN", case="nomn", number="sing", gender="masc", score=0.7),
            MorphInfo("журнал", "NOUN", case="accs", number="sing", gender="masc", score=0.3),
        ),
        "а": (MorphInfo("а", "CONJ", score=1.0),),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
        "нет": (MorphInfo("нет", "PRED", score=1.0),),
        "тоже": (MorphInfo("тоже", "ADVB", score=1.0),),
    })


def parser(morph):
    return AdaptivePerceptionParser(
        NoModelBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )


def source_assertion(text: str) -> AssertionCandidate:
    return AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "купил",
            normalized_hint="купить",
            evidence=EvidenceSpan("купил", 5, 10),
        ),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван", evidence=EvidenceSpan("Иван", 0, 4)),
            ActantCandidate(ActantRole.OBJECT, mention="книгу", normalized_hint="книга", evidence=EvidenceSpan("книгу", 11, 16)),
        ),
        evidence=EvidenceSpan("Иван купил книгу", 0, 16),
    )


def test_builder_splits_coordinated_zero_predicate_tail_as_runtime_ellipsis():
    morph = morphology()
    graph = LinguisticCandidateBuilder(morph).build("Иван купил книгу, а Мария журнал.")
    assert len(graph.clauses) == 2
    first, second = graph.clauses
    assert first.span.text == "Иван купил книгу"
    assert second.span.text == "а Мария журнал"
    assert second.predicate_heads == ()
    assert second.implicit_copula is False
    assert second.ellipsis_kind is EllipsisKind.FRAME
    assert second.ellipsis_source_clause_id == first.clause_id


def test_builder_marks_no_as_proposition_negation_and_too_as_confirmation():
    morph = morphology()
    negative = LinguisticCandidateBuilder(morph).build("Иван купил книгу, а Мария — нет.")
    assert negative.clauses[1].ellipsis_kind is EllipsisKind.PROPOSITION_NEGATION
    assert all(negative.token(item.token_index).text.casefold() != "нет" for item in negative.predicates)
    confirmation = LinguisticCandidateBuilder(morph).build("Иван купил книгу, и Мария тоже.")
    assert confirmation.clauses[1].ellipsis_kind is EllipsisKind.PROPOSITION_CONFIRMATION


def test_runtime_frame_completion_replaces_explicit_roles_and_inherits_only_missing_roles():
    text = "Иван купил книгу, а Мария журнал."
    morph = morphology()
    p = parser(morph)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    p._active_implicit_clause_id = None
    p._runtime_blocked_token_indices = set()
    tokens = p._source_tokens(text)

    def fake_extract(self, *args, **kwargs):
        assert kwargs["role_whitelist"] == {ActantRole.SUBJECT, ActantRole.OBJECT}
        return (
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Мария", normalized_hint="Мария", evidence=EvidenceSpan("Мария", 20, 25)),
                ActantCandidate(ActantRole.OBJECT, mention="журнал", normalized_hint="журнал", evidence=EvidenceSpan("журнал", 26, 32)),
            ),
            (),
        )

    p._extract_actants = types.MethodType(fake_extract, p)
    source = source_assertion(text)
    predicate_span = p._resolve_span(text, tokens, 2, 2)
    assertions, spans = p._recover_ellipsis_assertions(text, tokens, [source], {"A1": predicate_span})
    assert len(assertions) == 2
    recovered = assertions[1]
    assert recovered.predicate.lookup_form == "купить"
    assert recovered.negated is False
    assert {a.role: a.normalized_hint for a in recovered.actants} == {
        ActantRole.SUBJECT: "Мария",
        ActantRole.OBJECT: "журнал",
    }
    assert spans[recovered.local_id].evidence == recovered.evidence
    assert any(trace.stage == "ellipsis_recovery" for trace in p._traces)


def test_runtime_proposition_negation_inherits_unspoken_object():
    text = "Иван купил книгу, а Мария — нет."
    morph = morphology()
    p = parser(morph)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    p._active_implicit_clause_id = None
    p._runtime_blocked_token_indices = set()
    tokens = p._source_tokens(text)

    def fake_extract(self, *args, **kwargs):
        return (
            (ActantCandidate(ActantRole.SUBJECT, mention="Мария", normalized_hint="Мария", evidence=EvidenceSpan("Мария", 20, 25)),),
            (),
        )

    p._extract_actants = types.MethodType(fake_extract, p)
    source = source_assertion(text)
    predicate_span = p._resolve_span(text, tokens, 2, 2)
    assertions, _ = p._recover_ellipsis_assertions(text, tokens, [source], {"A1": predicate_span})
    recovered = assertions[1]
    assert recovered.negated is True
    assert {a.role: a.normalized_hint for a in recovered.actants} == {
        ActantRole.SUBJECT: "Мария",
        ActantRole.OBJECT: "книга",
    }


def test_builder_removes_nominal_predicate_candidates_owned_by_dash_ellipsis():
    morph = morphology()
    # Add a noun with a plausible nominal-predicate reading to model the production
    # failure where ``журнал`` after a dash entered the predicate work queue.
    graph = LinguisticCandidateBuilder(morph).build("Иван купил книгу, а Мария — журнал.")
    assert len(graph.clauses) == 2
    second = graph.clauses[1]
    assert second.ellipsis_kind is EllipsisKind.FRAME
    assert second.predicate_heads == ()
    assert all(
        not (second.span.start_index <= item.token_index <= second.span.end_index)
        for item in graph.predicates
    )


def test_builder_splits_comma_chained_ellipsis_and_links_each_tail_to_previous_frame():
    morph = morphology()
    graph = LinguisticCandidateBuilder(morph).build(
        "Иван купил книгу, Мария — журнал, Пётр — журнал."
    )
    assert [clause.span.text for clause in graph.clauses] == [
        "Иван купил книгу",
        "Мария — журнал",
        "Пётр — журнал",
    ]
    first, second, third = graph.clauses
    assert second.ellipsis_kind is EllipsisKind.FRAME
    assert second.ellipsis_source_clause_id == first.clause_id
    assert third.ellipsis_kind is EllipsisKind.FRAME
    assert third.ellipsis_source_clause_id == second.clause_id


def test_builder_stops_locative_ellipsis_chain_at_nominative_only_nominal_predicate():
    morph = StaticMorphology({
        "иван": (MorphInfo("иван", "NOUN", case="nomn", score=1.0),),
        "живёт": (MorphInfo("жить", "VERB", mood="indc", transitivity="intr", score=1.0),),
        "в": (MorphInfo("в", "PREP", score=1.0),),
        "москве": (MorphInfo("москва", "NOUN", case="loct", score=1.0),),
        "мария": (MorphInfo("мария", "NOUN", case="nomn", score=1.0),),
        "казани": (MorphInfo("казань", "NOUN", case="loct", score=1.0),),
        "пётр": (MorphInfo("пётр", "NOUN", case="nomn", score=1.0),),
        "париже": (MorphInfo("париж", "NOUN", case="loct", score=1.0),),
        "а": (MorphInfo("а", "CONJ", score=1.0),),
        "слава": (MorphInfo("слава", "NOUN", case="nomn", score=1.0),),
        "бродяга": (MorphInfo("бродяга", "NOUN", case="nomn", score=1.0),),
    })
    graph = LinguisticCandidateBuilder(morph).build(
        "Иван живёт в Москве, Мария — в Казани, Пётр — в Париже, а Слава — бродяга."
    )
    assert [clause.span.text for clause in graph.clauses] == [
        "Иван живёт в Москве",
        "Мария — в Казани",
        "Пётр — в Париже",
        "а Слава — бродяга",
    ]
    first, second, third, fourth = graph.clauses
    assert second.ellipsis_kind is EllipsisKind.FRAME
    assert second.ellipsis_source_clause_id == first.clause_id
    assert third.ellipsis_kind is EllipsisKind.FRAME
    assert third.ellipsis_source_clause_id == second.clause_id
    assert fourth.ellipsis_kind is None
    assert fourth.implicit_copula is True


def test_runtime_ellipsis_aligns_target_fillers_to_source_role_realization_signatures():
    morph = StaticMorphology({
        "анна": (MorphInfo("анна", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "отправила": (MorphInfo("отправить", "VERB", number="sing", gender="femn", mood="indc", transitivity="tran", score=1.0),),
        "письмо": (
            MorphInfo("письмо", "NOUN", case="nomn", number="sing", gender="neut", score=0.5),
            MorphInfo("письмо", "NOUN", case="accs", number="sing", gender="neut", score=0.5),
        ),
        "сергею": (MorphInfo("сергей", "NOUN", case="datv", number="sing", gender="masc", score=1.0),),
        "а": (MorphInfo("а", "CONJ", score=1.0),),
        "ольга": (MorphInfo("ольга", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "сообщение": (
            MorphInfo("сообщение", "NOUN", case="nomn", number="sing", gender="neut", score=0.5),
            MorphInfo("сообщение", "NOUN", case="accs", number="sing", gender="neut", score=0.5),
        ),
        "петру": (MorphInfo("пётр", "NOUN", case="datv", number="sing", gender="masc", score=1.0),),
    })
    text = "Анна отправила письмо Сергею, а Ольга сообщение Петру."
    p = parser(morph)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    p._active_implicit_clause_id = None
    p._runtime_blocked_token_indices = set()
    tokens = p._source_tokens(text)
    source = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate("отправила", normalized_hint="отправить", evidence=EvidenceSpan("отправила", 5, 14)),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="Анна", normalized_hint="Анна", evidence=EvidenceSpan("Анна", 0, 4)),
            ActantCandidate(ActantRole.OBJECT, mention="письмо", normalized_hint="письмо", evidence=EvidenceSpan("письмо", 15, 21)),
            ActantCandidate(ActantRole.RECIPIENT, mention="Сергею", normalized_hint="Сергей", evidence=EvidenceSpan("Сергею", 22, 28)),
        ),
        evidence=EvidenceSpan("Анна отправила письмо Сергею", 0, 28),
    )

    # Simulate the live bounded role probe's observed swap: Петру->SUBJECT,
    # Ольга->RECIPIENT.  Parallel realization signatures must repair it.
    def fake_extract(self, *args, **kwargs):
        return (
            (
                ActantCandidate(ActantRole.RECIPIENT, mention="Ольга", normalized_hint="Ольга", evidence=EvidenceSpan("Ольга", 32, 37)),
                ActantCandidate(ActantRole.OBJECT, mention="сообщение", normalized_hint="сообщение", evidence=EvidenceSpan("сообщение", 38, 47)),
                ActantCandidate(ActantRole.SUBJECT, mention="Петру", normalized_hint="Пётр", evidence=EvidenceSpan("Петру", 48, 53)),
            ),
            (),
        )

    p._extract_actants = types.MethodType(fake_extract, p)
    predicate_span = p._resolve_span(text, tokens, 2, 2)
    assertions, _ = p._recover_ellipsis_assertions(text, tokens, [source], {"A1": predicate_span})
    recovered = assertions[1]
    assert {a.role: a.normalized_hint for a in recovered.actants} == {
        ActantRole.SUBJECT: "Ольга",
        ActantRole.OBJECT: "сообщение",
        ActantRole.RECIPIENT: "Пётр",
    }
    assert any(trace.stage == "ellipsis_slot_alignment" for trace in p._traces)
