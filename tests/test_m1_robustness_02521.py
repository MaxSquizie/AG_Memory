from __future__ import annotations

from ah.perception.lexical_recovery import LexicalRecovery, LexicalRecoveryStatus
from ah.perception.linguistic_candidates import EllipsisKind, LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

from test_m1_robustness_02520 import StaticMorphology


PAST_M = frozenset({"past"})
PAST_F = frozenset({"past"})


def _decision(graph, raw: str):
    return next(token.recovery for token in graph.tokens if token.provenance_text == raw)


def test_bounded_recovery_rebuilds_frame_and_resolves_second_typo_on_later_pass() -> None:
    morph = StaticMorphology(
        {
            "Иван": (MorphInfo("иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
            "купл": (),
            "купил": (MorphInfo("купить", "VERB", number="sing", gender="masc", transitivity="tran", grammemes=PAST_M, score=1.0),),
            "книп": (),
            "книга": (MorphInfo("книга", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
            "книгу": (MorphInfo("книга", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
        },
        known={"Иван", "купил", "книга", "книгу"},
        candidate_map={"купл": ("купил",), "книп": ("книга", "книгу")},
    )
    graph = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Иван купл книп.")

    predicate = _decision(graph, "купл")
    object_form = _decision(graph, "книп")
    assert predicate.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert predicate.normalized_text == "купил"
    assert object_form.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert object_form.normalized_text == "книгу"


def test_stable_unknown_is_not_reopened_when_neighbouring_typo_is_corrected() -> None:
    morph = StaticMorphology(
        {
            "Нейросфера": (MorphInfo("нейросфера", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
            "Нейросферы": (MorphInfo("нейросфера", "NOUN", case="gent", number="sing", gender="femn", score=1.0),),
            "купл": (),
            "купил": (MorphInfo("купить", "VERB", number="sing", gender="masc", transitivity="tran", grammemes=PAST_M, score=1.0),),
            "сигнал": (MorphInfo("сигнал", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
        },
        known={"Нейросферы", "купил", "сигнал"},
        candidate_map={"Нейросфера": ("Нейросферы",), "купл": ("купил",)},
    )
    graph = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Нейросфера купл сигнал.")
    unknown = _decision(graph, "Нейросфера")
    predicate = _decision(graph, "купл")
    assert unknown.status is LexicalRecoveryStatus.UNKNOWN_TOKEN
    assert unknown.normalized_text == "Нейросфера"
    assert predicate.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE


def test_contextual_repeated_key_error_beats_keyboard_neighbour_but_standalone_stays_ambiguous() -> None:
    morph = StaticMorphology(
        {
            "Анна": (MorphInfo("анна", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
            "проверрила": (),
            "проверила": (MorphInfo("проверить", "VERB", number="sing", gender="femn", transitivity="tran", grammemes=PAST_F, score=1.0),),
            "проветрила": (MorphInfo("проветрить", "VERB", number="sing", gender="femn", transitivity="tran", grammemes=PAST_F, score=1.0),),
            "отчёт": (MorphInfo("отчёт", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
        },
        known={"Анна", "проверила", "проветрила", "отчёт"},
        candidate_map={"проверрила": ("проверила", "проветрила")},
    )
    contextual = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Анна проверрила отчёт.")
    fixed = _decision(contextual, "проверрила")
    assert fixed.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert fixed.normalized_text == "проверила"
    assert fixed.reason == "contextual noisy-channel dominance"

    standalone = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("проверрила")
    alone = _decision(standalone, "проверрила")
    assert alone.status is LexicalRecoveryStatus.AMBIGUOUS


def test_contextual_soft_sign_omission_beats_keyboard_variant_but_standalone_stays_ambiguous() -> None:
    morph = StaticMorphology(
        {
            "Анна": (MorphInfo("анна", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
            "отправила": (MorphInfo("отправить", "VERB", number="sing", gender="femn", transitivity="tran", grammemes=PAST_F, score=1.0),),
            "писмо": (),
            "письмо": (MorphInfo("письмо", "NOUN", case="accs", number="sing", gender="neut", score=1.0),),
            "пасмо": (MorphInfo("пасмо", "NOUN", case="accs", number="sing", gender="neut", score=1.0),),
        },
        known={"Анна", "отправила", "письмо", "пасмо"},
        candidate_map={"писмо": ("письмо", "пасмо")},
    )
    contextual = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Анна отправила писмо.")
    fixed = _decision(contextual, "писмо")
    assert fixed.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert fixed.normalized_text == "письмо"

    standalone = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("писмо")
    alone = _decision(standalone, "писмо")
    assert alone.status is LexicalRecoveryStatus.AMBIGUOUS


def test_same_lemma_surface_forms_use_frame_grammar_not_word_order() -> None:
    morph = StaticMorphology(
        {
            "книгп": (),
            "книга": (MorphInfo("книга", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
            "книгу": (MorphInfo("книга", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
            "прочитал": (MorphInfo("прочитать", "VERB", number="sing", gender="masc", transitivity="tran", grammemes=PAST_M, score=1.0),),
            "Иван": (MorphInfo("иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        },
        known={"книга", "книгу", "прочитал", "Иван"},
        candidate_map={"книгп": ("книга", "книгу")},
    )
    # Fronting deliberately verifies that the correction is frame-driven rather
    # than a "word after verb = object" shortcut.
    graph = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("книгп прочитал Иван.")
    fixed = _decision(graph, "книгп")
    assert fixed.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert fixed.normalized_text == "книгу"


def test_same_lemma_prep_case_tie_remains_ambiguous_without_semantic_evidence() -> None:
    geo = frozenset({"Geox"})
    morph = StaticMorphology(
        {
            "Иван": (MorphInfo("иван", "NOUN", case="nomn", score=1.0),),
            "едет": (MorphInfo("ехать", "VERB", number="sing", transitivity="intr", score=1.0),),
            "в": (MorphInfo("в", "PREP", score=1.0),),
            "Москвк": (),
            "Москве": (MorphInfo("москва", "NOUN", case="loct", gender="femn", grammemes=geo, score=1.0),),
            "Москву": (MorphInfo("москва", "NOUN", case="accs", gender="femn", grammemes=geo, score=1.0),),
        },
        known={"Иван", "едет", "в", "Москве", "Москву"},
        candidate_map={"Москвк": ("Москве", "Москву")},
    )
    graph = LinguisticCandidateBuilder(
        morph, lexical_recovery=LexicalRecovery(morph)
    ).build("Иван едет в Москвк.")
    decision = _decision(graph, "Москвк")
    assert decision.status is LexicalRecoveryStatus.AMBIGUOUS
    assert set(decision.alternatives[:2]) == {"Москве", "Москву"}


def test_embedding_context_is_natural_local_russian_fragment() -> None:
    morph = StaticMorphology(
        {
            "Ольга": (MorphInfo("ольга", "NOUN", case="nomn", score=1.0),),
            "положила": (MorphInfo("положить", "VERB", transitivity="tran", score=1.0),),
            "книгу": (MorphInfo("книга", "NOUN", case="accs", score=1.0),),
            "на": (MorphInfo("на", "PREP", score=1.0),),
            "полкк": (),
        },
        known={"Ольга", "положила", "книгу", "на"},
    )
    recovery = LexicalRecovery(morph)
    builder = LinguisticCandidateBuilder(morph)
    graph = builder.build("Ольга положила книгу на полкк.")
    target = next(token for token in graph.tokens if token.text == "полкк")
    context = recovery._context_text(target, graph.tokens, graph)
    assert context == "Ольга положила книгу на …"
    assert "TARGET" not in context
    assert "CLAUSE_CONTEXT" not in context


def test_punctuation_free_role_rich_dash_peer_keeps_single_tail_frame() -> None:
    morph = StaticMorphology(
        {
            "Сергей": (MorphInfo("сергей", "NOUN", case="nomn", score=1.0),),
            "передал": (MorphInfo("передать", "VERB", transitivity="tran", score=1.0),),
            "Анне": (MorphInfo("анна", "NOUN", case="datv", score=1.0),),
            "письмо": (MorphInfo("письмо", "NOUN", case="accs", score=1.0),),
            "Пётр": (MorphInfo("пётр", "NOUN", case="nomn", score=1.0),),
            "Ольге": (MorphInfo("ольга", "NOUN", case="datv", score=1.0),),
            "посылку": (MorphInfo("посылка", "NOUN", case="accs", score=1.0),),
        }
    )
    graph = LinguisticCandidateBuilder(morph).build(
        "Сергей передал Анне письмо Пётр Ольге — посылку."
    )
    assert len(graph.clauses) == 2
    assert graph.clauses[1].ellipsis_kind is EllipsisKind.FRAME


def test_inverted_dash_subject_is_not_misclassified_as_nominal_predication() -> None:
    morph = StaticMorphology(
        {
            "На": (MorphInfo("на", "PREP", score=1.0),),
            "стол": (MorphInfo("стол", "NOUN", case="accs", score=1.0),),
            "книгу": (MorphInfo("книга", "NOUN", case="accs", score=1.0),),
            "положила": (MorphInfo("положить", "VERB", transitivity="tran", score=1.0),),
            "Анна": (MorphInfo("анна", "NOUN", case="nomn", score=1.0),),
            "а": (MorphInfo("а", "CONJ", score=1.0),),
            "полку": (MorphInfo("полка", "NOUN", case="accs", score=1.0),),
            "журнал": (MorphInfo("журнал", "NOUN", case="accs", score=1.0),),
            "Ольга": (MorphInfo("ольга", "NOUN", case="nomn", score=1.0),),
        }
    )
    graph = LinguisticCandidateBuilder(morph).build(
        "На стол книгу положила Анна, а на полку журнал — Ольга."
    )
    assert len(graph.clauses) == 2
    second = graph.clauses[1]
    assert second.ellipsis_kind is EllipsisKind.FRAME
    assert second.implicit_copula is False


def test_coordinated_confirmation_subject_is_not_split_into_two_clauses() -> None:
    morph = StaticMorphology(
        {
            "Иван": (MorphInfo("иван", "NOUN", case="nomn", score=1.0),),
            "открыл": (MorphInfo("открыть", "VERB", transitivity="tran", score=1.0),),
            "дверь": (MorphInfo("дверь", "NOUN", case="accs", score=1.0),),
            "а": (MorphInfo("а", "CONJ", score=1.0),),
            "Мария": (MorphInfo("мария", "NOUN", case="nomn", score=1.0),),
            "и": (MorphInfo("и", "CONJ", score=1.0),),
            "Пётр": (MorphInfo("пётр", "NOUN", case="nomn", score=1.0),),
            "тоже": (MorphInfo("тоже", "ADVB", score=1.0),),
        }
    )
    graph = LinguisticCandidateBuilder(morph).build(
        "Иван открыл дверь, а Мария и Пётр тоже."
    )
    assert len(graph.clauses) == 2
    assert graph.clauses[1].ellipsis_kind is EllipsisKind.PROPOSITION_CONFIRMATION


def test_intransitive_nominal_boundary_stays_provisional_copula_not_frame_override() -> None:
    morph = StaticMorphology(
        {
            "Книга": (MorphInfo("книга", "NOUN", case="nomn", score=1.0),),
            "лежит": (MorphInfo("лежать", "VERB", transitivity="intr", score=1.0),),
            "на": (MorphInfo("на", "PREP", score=1.0),),
            "столе": (MorphInfo("стол", "NOUN", case="loct", score=1.0),),
            "а": (MorphInfo("а", "CONJ", score=1.0),),
            "журнал": (MorphInfo("журнал", "NOUN", case="nomn", score=1.0),),
            "подарок": (MorphInfo("подарок", "NOUN", case="nomn", score=1.0),),
        }
    )
    graph = LinguisticCandidateBuilder(morph).build(
        "Книга лежит на столе, а журнал — подарок."
    )
    assert len(graph.clauses) == 2
    assert graph.clauses[1].ellipsis_kind is EllipsisKind.FRAME
    assert graph.clauses[1].implicit_copula is True
