from ah.perception import EvidenceSpan, PredicateCandidate
from ah.perception.quantifier_formalization import QuantifierFormalizer


def _predicate(source: str, surface: str) -> PredicateCandidate:
    start = source.index(surface)
    return PredicateCandidate(
        surface=surface,
        normalized_hint=surface,
        evidence=EvidenceSpan(surface, start, start + len(surface)),
    )


def test_not_forall_plus_separate_body_not_is_scope_conflict() -> None:
    source = "Не каждый студент не сдал экзамен."
    assert QuantifierFormalizer._independent_negative_scope_conflict(
        source,
        _predicate(source, "сдал"),
        "Не каждый студент",
        predicate_negated=True,
    )


def test_not_forall_without_second_body_not_is_not_scope_conflict() -> None:
    source = "Не каждый студент сдал экзамен."
    assert not QuantifierFormalizer._independent_negative_scope_conflict(
        source,
        _predicate(source, "сдал"),
        "Не каждый студент",
        predicate_negated=True,
    )


def test_negative_concord_ni_phrase_does_not_look_like_independent_not_scope() -> None:
    source = "Ни один студент не сдал экзамен."
    assert not QuantifierFormalizer._independent_negative_scope_conflict(
        source,
        _predicate(source, "сдал"),
        "Ни один студент",
        predicate_negated=True,
    )
