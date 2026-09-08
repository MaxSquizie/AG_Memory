from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.contracts import EvidenceSpan, PredicateCandidate
from ah.perception.lexical_recovery import (
    LexicalRecovery,
    LexicalRecoveryStatus,
    TokenCandidate,
)
from ah.perception.linguistic_candidates import (
    EllipsisKind,
    LinguisticCandidateBuilder,
)
from ah.perception.morphology import MorphInfo


ROOT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "static"

    def __init__(self, mapping, *, known=None, candidate_map=None):
        self.mapping = {key.casefold(): tuple(value) for key, value in mapping.items()}
        self.known = {item.casefold() for item in (known or mapping.keys())}
        self.candidate_map = {
            key.casefold(): tuple(value) for key, value in (candidate_map or {}).items()
        }

    def analyze_all(self, word: str):
        return self.mapping.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None

    def is_known(self, word: str) -> bool:
        return word.casefold() in self.known

    def indexed_candidates(self, word: str, *, max_distance: int, limit: int = 512):
        del max_distance
        return self.candidate_map.get(word.casefold(), ())[:limit]


class NoProbeBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected semantic probe {role}: {prompt[:300]}")



def parser(morphology) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        NoProbeBackend(),
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts" / "perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


NOM_M = MorphInfo("иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0)
NOM_F = MorphInfo("мария", "NOUN", case="nomn", number="sing", gender="femn", score=1.0)
ACC = MorphInfo("книга", "NOUN", case="accs", number="sing", gender="femn", score=1.0)


def test_missing_comma_before_coordinator_still_licenses_structural_ellipsis() -> None:
    morph = StaticMorphology({
        "Иван": (NOM_M,),
        "купил": (MorphInfo("купить", "VERB", number="sing", gender="masc", transitivity="tran", grammemes=frozenset({"past"}), score=1.0),),
        "книгу": (ACC,),
        "а": (MorphInfo("а", "CONJ", score=1.0),),
        "Мария": (NOM_F,),
        "журнал": (
            MorphInfo("журнал", "NOUN", case="nomn", number="sing", gender="masc", score=0.5),
            MorphInfo("журнал", "NOUN", case="accs", number="sing", gender="masc", score=0.5),
        ),
    })
    graph = LinguisticCandidateBuilder(morph).build("Иван купил книгу а Мария журнал.")
    assert len(graph.clauses) == 2
    assert graph.clauses[1].ellipsis_kind is EllipsisKind.FRAME
    assert graph.clauses[1].ellipsis_source_clause_id == graph.clauses[0].clause_id


def test_missing_all_separator_punctuation_uses_strong_dash_peer_shell_only() -> None:
    morph = StaticMorphology({
        "Иван": (NOM_M,),
        "купил": (MorphInfo("купить", "VERB", number="sing", gender="masc", transitivity="tran", grammemes=frozenset({"past"}), score=1.0),),
        "книгу": (ACC,),
        "Мария": (NOM_F,),
        "журнал": (
            MorphInfo("журнал", "NOUN", case="nomn", score=0.5),
            MorphInfo("журнал", "NOUN", case="accs", score=0.5),
        ),
    })
    graph = LinguisticCandidateBuilder(morph).build("Иван купил книгу Мария — журнал.")
    assert len(graph.clauses) == 2
    assert graph.clauses[1].ellipsis_kind is EllipsisKind.FRAME

    # No dash/coordinator: do not invent a peer boundary inside an ordinary
    # multi-actant clause merely because another nominative-looking word occurs.
    guarded = LinguisticCandidateBuilder(morph).build("Иван купил книгу Мария журнал.")
    assert len(guarded.clauses) == 1


def test_dash_nominal_predication_is_preserved_for_nom_acc_syncretic_complement() -> None:
    morph = StaticMorphology({
        "Книга": (MorphInfo("книга", "NOUN", case="nomn", score=1.0),),
        "лежит": (MorphInfo("лежать", "VERB", number="sing", transitivity="intr", score=1.0),),
        "на": (MorphInfo("на", "PREP", score=1.0),),
        "столе": (MorphInfo("стол", "NOUN", case="loct", score=1.0),),
        "а": (MorphInfo("а", "CONJ", score=1.0),),
        "журнал": (
            MorphInfo("журнал", "NOUN", case="nomn", score=0.5),
            MorphInfo("журнал", "NOUN", case="accs", score=0.5),
        ),
        "подарок": (
            MorphInfo("подарок", "NOUN", case="nomn", score=0.5),
            MorphInfo("подарок", "NOUN", case="accs", score=0.5),
        ),
    })
    graph = LinguisticCandidateBuilder(morph).build(
        "Книга лежит на столе, а журнал — подарок."
    )
    assert len(graph.clauses) == 2
    second = graph.clauses[1]
    assert second.ellipsis_kind is EllipsisKind.FRAME
    assert second.implicit_copula is True


def test_adverbial_realization_can_replace_inherited_adverbial_slot() -> None:
    morph = StaticMorphology({
        "Вчера": (MorphInfo("вчера", "ADVB", score=1.0),),
        "сегодня": (MorphInfo("сегодня", "ADVB", score=1.0),),
    })
    p = parser(morph)
    tokens = LinguisticCandidateBuilder(morph).build("Вчера сегодня").tokens
    left = p._realization_signature(EvidenceSpan("Вчера", 0, 5), tokens)
    right = p._realization_signature(EvidenceSpan("сегодня", 6, 13), tokens)
    assert left is not None and left[0] == "ADVERBIAL"
    assert right is not None and right[0] == "ADVERBIAL"
    assert p._compatible_realizations(left, right)


def test_titlecase_oov_can_be_corrected_when_clause_structure_excludes_name_subject() -> None:
    morph = StaticMorphology(
        {
            "Докмент": (MorphInfo("докмент", "NOUN", case="nomn", score=1.0),),
            "Документ": (
                MorphInfo("документ", "NOUN", case="nomn", score=0.5),
                MorphInfo("документ", "NOUN", case="accs", score=0.5),
            ),
            "прочитал": (MorphInfo("прочитать", "VERB", number="sing", gender="masc", transitivity="tran", grammemes=frozenset({"past"}), score=1.0),),
            "инженер": (MorphInfo("инженер", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        },
        known={"Документ", "прочитал", "инженер"},
        candidate_map={"Докмент": ("Документ",)},
    )
    recovery = LexicalRecovery(morph)
    graph = LinguisticCandidateBuilder(morph, lexical_recovery=recovery).build(
        "Докмент прочитал инженер."
    )
    first = graph.tokens[0].recovery
    assert first is not None
    assert first.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert first.normalized_text == "Документ"


def test_titlecase_unknown_subject_remains_protected() -> None:
    morph = StaticMorphology(
        {
            "Нейросфера": (MorphInfo("нейросфера", "NOUN", case="nomn", score=1.0),),
            "Нейросферы": (MorphInfo("нейросфера", "NOUN", case="gent", score=1.0),),
            "анализирует": (MorphInfo("анализировать", "VERB", number="sing", transitivity="tran", score=1.0),),
            "сигнал": (
                MorphInfo("сигнал", "NOUN", case="nomn", score=0.5),
                MorphInfo("сигнал", "NOUN", case="accs", score=0.5),
            ),
        },
        known={"Нейросферы", "анализирует", "сигнал"},
        candidate_map={"Нейросфера": ("Нейросферы",)},
    )
    graph = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Нейросфера анализирует сигнал.")
    decision = graph.tokens[0].recovery
    assert decision is not None
    assert decision.status is LexicalRecoveryStatus.UNKNOWN_TOKEN
    assert decision.normalized_text == "Нейросфера"


def test_protected_unknown_is_not_reopened_by_contextual_lexeme_probe() -> None:
    morph = StaticMorphology({
        "Нейросфера": (
            MorphInfo("нейросфер", "NOUN", case="nomn", score=0.5),
            MorphInfo("нейросфера", "NOUN", case="nomn", score=0.5),
        ),
    })
    p = parser(morph)
    graph = LinguisticCandidateBuilder(morph).build("Нейросфера")
    unknown = TokenCandidate(
        1,
        "Нейросфера",
        "Нейросфера",
        LexicalRecoveryStatus.UNKNOWN_TOKEN,
        reason="protected new term",
    )
    token = replace(graph.tokens[0], recovery=unknown)
    p._contextualize_nominal_span(
        "Нейросфера",
        PredicateCandidate("анализирует"),
        p._resolve_span("Нейросфера", (token,), 1, 1),
        (token,),
    )
    assert p._contextual_nominal_lemmas == {}


def test_opaque_unknown_bare_filler_is_object_only_when_subject_is_independently_present() -> None:
    morph = StaticMorphology({
        "Модуль": (MorphInfo("модуль", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "использует": (MorphInfo("использовать", "VERB", number="sing", transitivity="tran", score=1.0),),
    }, known={"Модуль", "использует"})
    recovery = LexicalRecovery(morph)
    graph = LinguisticCandidateBuilder(morph, lexical_recovery=recovery).build(
        "Модуль использует QX17."
    )
    p = parser(morph)
    p._candidate_graph = graph
    tokens = graph.tokens
    predicate_span = p._resolve_span(graph.text, tokens, 2, 2)
    target_span = p._resolve_span(graph.text, tokens, 3, 3)
    assert tokens[2].recovery is not None
    assert tokens[2].recovery.status is LexicalRecoveryStatus.UNKNOWN_TOKEN
    assert p._deterministic_role_candidates(
        tokens,
        predicate_span,
        PredicateCandidate("использует", normalized_hint="использовать"),
        target_span,
    ) == (ActantRole.OBJECT,)


def test_transitive_frame_disambiguates_noun_from_verbal_typo_candidate_but_standalone_does_not() -> None:
    morph = StaticMorphology(
        {
            "Сергей": (MorphInfo("сергей", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
            "передал": (MorphInfo("передать", "VERB", number="sing", gender="masc", transitivity="tran", grammemes=frozenset({"past"}), score=1.0),),
            "Анне": (MorphInfo("анна", "NOUN", case="datv", number="sing", gender="femn", score=1.0),),
            "клю": (),
            "ключ": (
                MorphInfo("ключ", "NOUN", case="nomn", score=0.5),
                MorphInfo("ключ", "NOUN", case="accs", score=0.5),
            ),
            "клюй": (MorphInfo("клевать", "VERB", mood="impr", score=1.0),),
            "колю": (MorphInfo("колоть", "VERB", mood="indc", score=1.0),),
        },
        known={"Сергей", "передал", "Анне", "ключ", "клюй", "колю"},
        candidate_map={"клю": ("ключ", "клюй", "колю")},
    )
    contextual = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Сергей передал Анне клю.")
    decision = next(t.recovery for t in contextual.tokens if t.provenance_text == "клю")
    assert decision is not None
    assert decision.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert decision.normalized_text == "ключ"

    standalone = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("клю")
    alone = standalone.tokens[0].recovery
    assert alone is not None
    assert alone.status is LexicalRecoveryStatus.AMBIGUOUS


def test_preposition_government_narrows_surface_form_without_assigning_semantic_role() -> None:
    morph = StaticMorphology(
        {
            "Иван": (NOM_M,),
            "подошёл": (MorphInfo("подойти", "VERB", number="sing", gender="masc", transitivity="intr", grammemes=frozenset({"past"}), score=1.0),),
            "к": (MorphInfo("к", "PREP", score=1.0),),
            "станци": (),
            "станции": (MorphInfo("станция", "NOUN", case="datv", score=1.0),),
            "станция": (MorphInfo("станция", "NOUN", case="nomn", score=1.0),),
        },
        known={"Иван", "подошёл", "к", "станции", "станция"},
        candidate_map={"станци": ("станции", "станция")},
    )
    graph = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Иван подошёл к станци.")
    decision = next(t.recovery for t in graph.tokens if t.provenance_text == "станци")
    assert decision is not None
    assert decision.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert decision.normalized_text == "станции"
