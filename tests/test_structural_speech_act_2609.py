from __future__ import annotations

from ah.config import LLMRoleSettings
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
        "что": (
            MorphInfo(
                "что", "NPRO", case="accs", number="sing",
                grammemes=frozenset({"Ques"}), score=1.0,
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

    force = parser._deterministic_act_type(
        tokens,
        (predicate_index,),
        clause.clause_id,
    )

    assert force == "QUERY"


def test_embedded_wh_does_not_turn_matrix_into_query() -> None:
    parser, graph, tokens = _parser_and_graph("Я знаю, что сделал Илья")
    predicate_index = _predicate_index(graph, "знаю")
    clause = graph.clause_for_token(predicate_index)
    assert clause is not None

    force = parser._deterministic_act_type(
        tokens,
        (predicate_index,),
        clause.clause_id,
    )

    assert force == "ASSERTION"
