from __future__ import annotations

from ah.model import ActantRole
from ah.perception import TemporalMode, TransitionOperator
from ah.perception.morphology import Pymorphy3Morphology
from test_full_ellipsis_pipeline_02514 import SemanticFixture, make_parser


def _role(assertion, role: ActantRole) -> str:
    return next(
        (item.lookup_text or "").casefold()
        for item in assertion.actants
        if item.role is role
    )


def test_punctuation_free_locative_chain_does_not_exhaust_role_space() -> None:
    parser = make_parser(Pymorphy3Morphology(), SemanticFixture())
    parsed = parser.parse(
        "Иван живёт в Москве Мария — в Казани Пётр — в Париже."
    ).perception
    rows = [
        (
            item.predicate.lookup_form,
            _role(item, ActantRole.SUBJECT),
            _role(item, ActantRole.LOCATION),
        )
        for item in parsed.assertions
    ]
    assert rows == [
        ("жить", "иван", "москва"),
        ("жить", "мария", "казань"),
        ("жить", "пётр", "париж"),
    ]


def test_phase_operator_is_inherited_by_ellipsis_frame_not_left_as_matrix_fact() -> None:
    parser = make_parser(Pymorphy3Morphology(), SemanticFixture())
    parsed = parser.parse(
        "Анна начала писать письмо, а Мария — отчёт."
    ).perception
    assert len(parsed.assertions) == 2
    for assertion, subject, obj in zip(
        parsed.assertions,
        ("анна", "мария"),
        ("письмо", "отчёт"),
    ):
        assert assertion.predicate.lookup_form == "писать"
        assert assertion.temporal_mode is TemporalMode.TRANSITION
        assert assertion.transition_operator is TransitionOperator.START
        assert _role(assertion, ActantRole.SUBJECT) == subject
        assert _role(assertion, ActantRole.OBJECT) == obj


def test_nested_control_ellipsis_keeps_two_complete_control_frames() -> None:
    parser = make_parser(Pymorphy3Morphology(), SemanticFixture())
    parsed = parser.parse(
        "Анна попросила Сергея отправить письмо Петру, а Ольга — Ивана сообщение Марии."
    ).perception
    predicates = [item.predicate.lookup_form for item in parsed.assertions]
    assert predicates.count("попросить") == 2
    assert predicates.count("отправить") == 2

    requests = [item for item in parsed.assertions if item.predicate.lookup_form == "попросить"]
    sends = [item for item in parsed.assertions if item.predicate.lookup_form == "отправить"]
    assert [_role(item, ActantRole.SUBJECT) for item in requests] == ["анна", "ольга"]
    assert [_role(item, ActantRole.SUBJECT) for item in sends] == ["сергей", "иван"]
    assert [_role(item, ActantRole.OBJECT) for item in sends] == ["письмо", "сообщение"]
    assert [_role(item, ActantRole.RECIPIENT) for item in sends] == ["пётр", "мария"]
