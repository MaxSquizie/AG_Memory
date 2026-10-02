from __future__ import annotations

from ah.config import LLMRoleSettings
from ah.model import ActantRole
from ah.perception import ActantCandidate, AssertionCandidate, EvidenceSpan, PredicateCandidate
from ah.perception.adaptive_parser import AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo
from ah.perception.structural_speech_act import StructuralSpeechActAdaptiveParser


class _Backend:
    def generate(self, *args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("speech-act classification should be deterministic")


class _Morphology:
    name = "test"

    _MAP = {
        # Model a common homography problem deliberately: the complementizer
        # reading is much more probable than the interrogative-pronoun reading.
        # Speech force must use the closed Ques grammeme after clause scoping,
        # rather than letting the generic morphology score erase it.
        "что": (
            MorphInfo("что", "CONJ", score=0.9),
            MorphInfo(
                "что", "NPRO", case="accs", number="sing",
                grammemes=frozenset({"Ques"}), score=0.1,
            ),
        ),
        "я": (
            MorphInfo("я", "NPRO", case="nomn", number="sing", score=1.0),
        ),
        "илья": (
            MorphInfo(
                "илья", "NOUN", case="nomn", number="sing", gender="masc",
                score=1.0,
            ),
        ),
        "вчера": (
            MorphInfo("вчера", "ADVB", score=1.0),
        ),
        "делал": (
            MorphInfo(
                "делать", "VERB", number="sing", gender="masc", mood="indc",
                transitivity="tran", grammemes=frozenset({"past"}), score=1.0,
            ),
        ),
        "сделал": (
            MorphInfo(
                "сделать", "VERB", number="sing", gender="masc", mood="indc",
                transitivity="tran", grammemes=frozenset({"past"}), score=1.0,
            ),
        ),
        "знаю": (
            MorphInfo(
                "знать", "VERB", number="sing", mood="indc",
                transitivity="tran", score=1.0,
            ),
        ),
        "моё": (
            MorphInfo(
                "мой", "ADJF", case="nomn", number="sing", gender="neut",
                grammemes=frozenset({"Apro"}), score=1.0,
            ),
        ),
        "имя": (
            MorphInfo(
                "имя", "NOUN", case="nomn", number="sing", gender="neut",
                score=1.0,
            ),
        ),
    }

    def analyze_all(self, word: str):
        return self._MAP.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def _parser_and_graph(text: str):
    morph = _Morphology()
    graph = LinguisticCandidateBuilder(morph).build(text)
    parser = StructuralSpeechActAdaptiveParser(
        _Backend(),
        AdaptiveSettings(
            prompt_dir=None,
            generation=LLMRoleSettings(max_new_tokens=24),
            morphology_backend="none",
        ),
        morphology=morph,
    )
    parser._candidate_graph = graph
    tokens = parser._source_tokens_from_graph(graph)
    return parser, graph, tokens


def _predicate_index(graph, surface: str) -> int:
    return next(
        token.index
        for token in graph.tokens
        if token.text.casefold() == surface.casefold()
    )


def test_top_level_wh_is_query_without_question_mark() -> None:
    parser, graph, tokens = _parser_and_graph("Что вчера делал Илья")
    predicate_index = _predicate_index(graph, "делал")
    clause = graph.clause_for_token(predicate_index)
    assert clause is not None
    predicate_span = parser._resolve_span_from_source(
        tokens, predicate_index, predicate_index
    )

    force = parser._deterministic_act_type(
        tokens,
        (predicate_index,),
        clause.clause_id,
    )
    placeholders = parser._explicit_question_words(tokens, predicate_span)

    assert force == "QUERY"
    assert tuple(item.text for item in placeholders) == ("Что",)


def test_embedded_wh_does_not_turn_matrix_into_query() -> None:
    parser, graph, tokens = _parser_and_graph("Я знаю, что сделал Илья")
    predicate_index = _predicate_index(graph, "знаю")
    clause = graph.clause_for_token(predicate_index)
    assert clause is not None
    predicate_span = parser._resolve_span_from_source(
        tokens, predicate_index, predicate_index
    )

    force = parser._deterministic_act_type(
        tokens,
        (predicate_index,),
        clause.clause_id,
    )
    placeholders = parser._explicit_question_words(tokens, predicate_span)

    assert force == "ASSERTION"
    assert placeholders == ()


def test_relative_day_is_time_before_free_role_classification() -> None:
    parser, graph, tokens = _parser_and_graph("Что вчера делал Илья")
    predicate_index = _predicate_index(graph, "делал")
    time_index = _predicate_index(graph, "вчера")
    predicate_span = parser._resolve_span_from_source(
        tokens, predicate_index, predicate_index
    )
    time_span = parser._resolve_span_from_source(tokens, time_index, time_index)

    roles = parser._deterministic_role_candidates(
        tokens,
        predicate_span,
        PredicateCandidate("делал", normalized_hint="делать"),
        time_span,
    )

    assert roles == (ActantRole.TIME,)


def test_deictic_nominal_owner_is_recovered_from_morphology_not_name_phrase_table() -> None:
    parser, graph, _tokens = _parser_and_graph("Моё имя — Илья")
    possessive = next(token for token in graph.tokens if token.text.casefold() == "моё")
    noun = next(token for token in graph.tokens if token.text.casefold() == "имя")
    phrase_start = min(possessive.start, noun.start)
    phrase_end = max(possessive.end, noun.end)
    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "Илья",
            normalized_hint="илья",
            sense_hint="NOMINAL_PREDICATION",
        ),
        actants=(
            ActantCandidate(
                ActantRole.STATE,
                mention="Моё имя",
                normalized_hint="имя",
                evidence=EvidenceSpan("Моё имя", phrase_start, phrase_end),
            ),
        ),
    )

    owner = parser._deictic_nominal_owner(assertion)

    assert owner is not None
    assert owner.role is ActantRole.SUBJECT
    assert owner.mention == "Моё"
