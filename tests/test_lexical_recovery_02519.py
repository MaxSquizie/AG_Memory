from __future__ import annotations

from pathlib import Path

import pytest

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import (
    AdaptiveParseError,
    AdaptivePerceptionParser,
    AdaptiveSettings,
)
from ah.perception.lexical_recovery import (
    LexicalRecovery,
    LexicalRecoveryStatus,
    weighted_damerau_levenshtein,
)
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import Pymorphy3Morphology


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def morphology() -> Pymorphy3Morphology:
    return Pymorphy3Morphology()


def decisions(text: str, morphology, reranker=None):
    recovery = LexicalRecovery(morphology, semantic_reranker=reranker)
    graph = LinguisticCandidateBuilder(
        morphology, lexical_recovery=recovery
    ).build(text)
    return graph, {item.provenance_text: item.recovery for item in graph.tokens}


def test_weighted_damerau_levenshtein_covers_all_edit_families() -> None:
    assert weighted_damerau_levenshtein("стол", "стол") == 0.0
    assert weighted_damerau_levenshtein("стол", "сто") == 1.0
    assert weighted_damerau_levenshtein("стоол", "стол") == 1.0
    assert weighted_damerau_levenshtein("стол", "стул") == 1.0
    assert weighted_damerau_levenshtein("стло", "стол") == pytest.approx(0.65)
    assert weighted_damerau_levenshtein("елка", "ёлка") == pytest.approx(0.15)
    assert weighted_damerau_levenshtein("книгп", "книга") < 1.0


def test_pymorphy_dawg_index_is_on_demand_and_finds_transposition(morphology) -> None:
    assert morphology.is_known("документ")
    assert not morphology.is_known("докмент")
    assert "документ" in morphology.indexed_candidates(
        "докмент", max_distance=1
    )
    assert "стол" in morphology.indexed_candidates("стло", max_distance=1)


def test_unique_candidate_is_corrected_before_final_morphology(morphology) -> None:
    graph, by_raw = decisions("Мария прочитала докмент.", morphology)
    item = by_raw["докмент"]
    assert item.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert item.normalized_text == "документ"
    assert graph.token(item.token_index).text == "документ"
    assert graph.token(item.token_index).provenance_text == "докмент"
    assert any(info.normal_form == "документ" for info in graph.token(item.token_index).analyses)


def test_morphosyntax_selects_finite_predicate_without_a_verb_list(morphology) -> None:
    graph, by_raw = decisions("Пётр открл дверь ключом.", morphology)
    item = by_raw["открл"]
    assert item.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert item.normalized_text == "открыл"
    assert [(head.token_index, head.lemma_candidates) for head in graph.predicates] == [
        (2, ("открыть",))
    ]


def test_order_does_not_change_local_recovery_constraints(morphology) -> None:
    _left, normal = decisions("Инженер прочитал докмент.", morphology)
    _right, inverted = decisions("Докмент прочитал инженер.", morphology)
    # Sentence-initial title case is protected as a possible name/term.  The same
    # typo is safely recoverable when source syntax proves it is not such a token;
    # recovery never assigns SUBJECT/OBJECT from position.
    assert normal["докмент"].normalized_text == "документ"
    assert inverted["Докмент"].status is LexicalRecoveryStatus.UNKNOWN_TOKEN


def test_names_terms_acronyms_and_codes_are_not_forced_to_dictionary_words(morphology) -> None:
    _graph, by_raw = decisions(
        "Ксентарий передал РКТ модуль QX17 под названием «кванторий».",
        morphology,
    )
    for raw in ("Ксентарий", "РКТ", "QX17", "кванторий"):
        assert by_raw[raw].status is LexicalRecoveryStatus.UNKNOWN_TOKEN
        assert by_raw[raw].normalized_text == raw


def test_unresolved_close_candidates_are_ambiguous_not_a_forced_guess(morphology) -> None:
    _graph, by_raw = decisions("Ребёнок увидел ктт.", morphology)
    item = by_raw["ктт"]
    assert item.status is LexicalRecoveryStatus.AMBIGUOUS
    assert item.normalized_text is None
    assert {"кот", "кит"}.issubset(set(item.alternatives))


class _SemanticReranker:
    def __init__(self, preferred: str) -> None:
        self.preferred = preferred
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def rank(self, context: str, candidates: tuple[str, ...]) -> dict[str, float]:
        self.calls.append((context, candidates))
        return {item: (1.0 if item == self.preferred else 0.0) for item in candidates}


def test_semantic_reranker_runs_only_for_the_narrow_close_shortlist(morphology) -> None:
    reranker = _SemanticReranker("кот")
    _graph, by_raw = decisions("Ребёнок увидел ктт.", morphology, reranker)
    assert by_raw["ктт"].normalized_text == "кот"
    assert len(reranker.calls) == 1
    assert 2 <= len(reranker.calls[0][1]) <= 8

    unique = _SemanticReranker("документ")
    decisions("Мария прочитала докмент.", morphology, unique)
    assert unique.calls == []


class _ParserFixture:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "perception_role_cue":
            target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0].casefold()
            if target in {"мария", "пётр"}:
                return LLMResponse("ACTOR_OR_EXPERIENCER", {})
            if target in {"документ", "дверь"}:
                return LLMResponse("AFFECTED_OR_CONTENT", {})
            if target == "ключом":
                return LLMResponse("INSTRUMENT", {})
        if role == "perception_act_relation":
            return LLMResponse("NONE", {})
        raise AssertionError(f"unexpected bounded call: {role}\n{prompt[:600]}")


def parser(morphology, *, reranker=None) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        _ParserFixture(),
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts" / "perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
        semantic_reranker=reranker,
    )


def test_parser_uses_corrected_identity_but_keeps_raw_evidence(morphology) -> None:
    parsed = parser(morphology).parse("Мария прочитала докмент.").perception
    assertion = parsed.assertions[0]
    object_ = next(item for item in assertion.actants if item.role is ActantRole.OBJECT)
    assert object_.mention == "документ"
    assert object_.lookup_text == "документ"
    assert object_.evidence.text == "докмент"
    assert parsed.source_text == "Мария прочитала докмент."

    predicate_parsed = parser(morphology).parse("Пётр открл дверь ключом.").perception
    predicate = predicate_parsed.assertions[0].predicate
    assert predicate.surface == "открыл"
    assert predicate.lookup_form == "открыть"
    assert predicate.evidence.text == "открл"


def test_parser_fails_closed_before_semantics_on_ambiguous_oov(morphology) -> None:
    with pytest.raises(AdaptiveParseError, match="ambiguous lexical recovery"):
        parser(morphology).parse("Мария увидела ктт.")

