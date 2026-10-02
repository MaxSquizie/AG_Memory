from __future__ import annotations

from ah.model import ActantRole
from ah.llm.process_backend import LLMResponse
from ah.perception import TemporalMode, TransitionOperator
from ah.perception.morphology import Pymorphy3Morphology
from test_full_ellipsis_pipeline_02514 import SemanticFixture, make_parser


class _ResidualFixture(SemanticFixture):
    """Bounded semantic answers needed only by the residual frame shapes."""

    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "perception_frame_relation":
            parent = prompt.split("PARENT PREDICATE:\n", 1)[1].split("\n", 1)[0]
            if parent in {"начала", "попросила"}:
                return LLMResponse("CONTENT_LINK", {})
        if role == "semantic_nonfinite_assertion_status":
            matrix = prompt.split("MATRIX PREDICATE:\n", 1)[1].split("\n", 1)[0]
            if matrix == "начала":
                return LLMResponse("SCOPED_EVENT", {})
        if role == "semantic_transition_operator" and "MATRIX PREDICATE:\nначала" in prompt:
            return LLMResponse("START", {})
        if role == "perception_control_subject" and "PARENT PREDICATE:\nпопросила" in prompt:
            return LLMResponse("SECOND", {})
        if role == "perception_nominal_genitive_attachment":
            return LLMResponse("SEPARATE", {})
        if role == "perception_lexeme_comparison":
            target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0]
            intended = {
                "Петру": "пётр",
                "Марии": "мария",
                "Сергея": "сергей",
                "Ивана": "иван",
            }.get(target)
            if intended is not None:
                for label in ("A", "B"):
                    if f"{label.casefold()} lemma:\n{intended}\n" in prompt.casefold():
                        return LLMResponse(label, {})
        if role == "perception_role_cue":
            predicate = prompt.split("PREDICATE:\n", 1)[1].split("\n", 1)[0]
            target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0]
            if predicate == "попросила" and target in {"Сергея", "Ивана"}:
                return LLMResponse("RECEIVER_OR_ADDRESSEE", {})
            if predicate == "отправить" and target in {"Петру", "Марии"}:
                return LLMResponse("RECEIVER_OR_ADDRESSEE", {})
        return super().generate(
            prompt, system=system, override=override, role=role
        )


def _role(assertion, role: ActantRole) -> str:
    return next(
        (item.lookup_text or "").casefold()
        for item in assertion.actants
        if item.role is role
    )


def test_punctuation_free_locative_chain_does_not_exhaust_role_space() -> None:
    parser = make_parser(Pymorphy3Morphology(), _ResidualFixture())
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


def test_single_punctuation_free_locative_peer_gets_its_own_clause() -> None:
    parser = make_parser(Pymorphy3Morphology(), _ResidualFixture())
    parsed = parser.parse(
        "Книга лежит на столе журнал — на полке."
    ).perception
    assert [
        (
            item.predicate.lookup_form,
            _role(item, ActantRole.SUBJECT),
            _role(item, ActantRole.LOCATION),
        )
        for item in parsed.assertions
    ] == [
        ("лежать", "книга", "стол"),
        ("лежать", "журнал", "полка"),
    ]


def test_phase_operator_is_inherited_by_ellipsis_frame_not_left_as_matrix_fact() -> None:
    parser = make_parser(Pymorphy3Morphology(), _ResidualFixture())
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
    parser = make_parser(Pymorphy3Morphology(), _ResidualFixture())
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
