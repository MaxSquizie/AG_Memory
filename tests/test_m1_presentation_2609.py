from ah.diagnostics.m1_presentation import (
    build_m1_formalization_view,
    render_m1_formalization_html,
)


def _predicate(surface: str, normalized: str):
    return {
        "surface": surface,
        "normalized_hint": normalized,
        "evidence": {"text": surface, "start": None, "end": None},
    }


def test_fact_view_marks_quantifier_predicate_and_roles_from_perception():
    source = "Каждый инженер имеет инструмент"
    perception = {
        "source_text": source,
        "assertions": [
            {
                "local_id": "a1",
                "predicate": _predicate("имеет", "иметь"),
                "status": "ASSERTED",
                "negated": False,
                "actants": [
                    {
                        "role": "SUBJECT",
                        "mention": "Каждый инженер",
                        "normalized_hint": "инженер",
                        "evidence": {"text": "Каждый инженер", "start": None, "end": None},
                        "quantifier": {
                            "kind": "FORALL",
                            "surface": "Каждый",
                            "restriction_lemma": "инженер",
                            "evidence": {"text": "Каждый", "start": None, "end": None},
                        },
                    },
                    {
                        "role": "OBJECT",
                        "mention": "инструмент",
                        "normalized_hint": "инструмент",
                        "evidence": {"text": "инструмент", "start": None, "end": None},
                    },
                ],
            }
        ],
    }

    view = build_m1_formalization_view(perception)

    assert view.prompt_type == "ФАКТ"
    assert [(word.text, word.label, word.detail) for word in view.words] == [
        ("Каждый", "Квантор", "FORALL"),
        ("инженер", "SUBJECT", "субъект"),
        ("имеет", "Предикат", "иметь"),
        ("инструмент", "OBJECT", "объект"),
    ]
    frame = view.frames[0]
    assert frame.predicate == "иметь"
    assert frame.roles[0].operator == "FORALL"
    assert "Квантор FORALL относится к SUBJECT" in view.interpretation


def test_query_view_shows_requested_role_as_gap_without_inventing_wh_semantics():
    source = "Что вчера сделал Илья"
    perception = {
        "source_text": source,
        "queries": [
            {
                "local_id": "q1",
                "predicate": _predicate("сделал", "сделать"),
                "query_mode": "FILL_ROLE",
                "requested_roles": ["OBJECT"],
                "actants": [
                    {
                        "role": "TIME",
                        "mention": "вчера",
                        "normalized_hint": "вчера",
                        "evidence": {"text": "вчера", "start": None, "end": None},
                    },
                    {
                        "role": "SUBJECT",
                        "mention": "Илья",
                        "normalized_hint": "Илья",
                        "evidence": {"text": "Илья", "start": None, "end": None},
                    },
                ],
            }
        ],
    }

    view = build_m1_formalization_view(perception)

    assert view.prompt_type == "ЗАПРОС"
    assert view.prompt_detail == "Найти: OBJECT"
    assert next(word for word in view.words if word.text == "Что").label == "—"
    assert next(word for word in view.words if word.text == "вчера").label == "TIME"
    assert next(word for word in view.words if word.text == "сделал").label == "Предикат"
    assert next(word for word in view.words if word.text == "Илья").label == "SUBJECT"
    requested = [role for role in view.frames[0].roles if role.requested]
    assert [(role.role, role.value) for role in requested] == [("OBJECT", "?")]
    assert view.interpretation.startswith("Нужно найти OBJECT")


def test_logical_root_is_presented_as_simple_operator_over_frames():
    source = "Иван пришёл или Мария позвонила"
    perception = {
        "source_text": source,
        "assertions": [
            {
                "local_id": "a1",
                "predicate": _predicate("пришёл", "прийти"),
                "actants": [{"role": "SUBJECT", "mention": "Иван", "evidence": {"text": "Иван"}}],
            },
            {
                "local_id": "a2",
                "predicate": _predicate("позвонила", "позвонить"),
                "actants": [{"role": "SUBJECT", "mention": "Мария", "evidence": {"text": "Мария"}}],
            },
        ],
        "proposition_roots": [
            {
                "local_id": "g1",
                "expression": {
                    "operator": "OR",
                    "members": [
                        {"operator": "REF", "ref": "a1", "members": []},
                        {"operator": "REF", "ref": "a2", "members": []},
                    ],
                },
            }
        ],
    }

    view = build_m1_formalization_view(perception)

    assert view.prompt_type == "ФАКТ · ЛОГИЧЕСКОЕ ВЫРАЖЕНИЕ"
    assert view.logic_operator == "OR"
    assert view.formula == "(прийти OR позвонить)"
    assert len(view.frames) == 2
    html = render_m1_formalization_html(view)
    assert "Итоговая схема смысла" in html
    assert "ИЛИ (OR)" in html
    assert "Человеческое прочтение" in html


def test_typed_naming_is_presented_as_name_relation_not_bad_source_roles():
    source = "Меня зовут Илья"
    perception = {
        "source_text": source,
        "assertions": [
            {
                "local_id": "a1",
                "predicate": _predicate("зовут", "звать"),
                "status": "ASSERTED",
                "actants": [
                    {
                        "role": "SUBJECT",
                        "mention": "Меня",
                        "evidence": {"text": "Меня"},
                    },
                    {
                        "role": "STATE",
                        "mention": "Илья",
                        "normalized_hint": "илья",
                        "evidence": {"text": "Илья"},
                    },
                ],
                "owner": {
                    "role": "SUBJECT",
                    "mention": "Меня",
                    "evidence": {"text": "Меня"},
                },
                "name_value": "Илья",
                "name_normalized_hint": "илья",
            }
        ],
    }

    view = build_m1_formalization_view(perception)

    assert view.prompt_type == "ФАКТ · ИМЕНОВАНИЕ"
    assert view.prompt_detail == "Задаёт имя существующей сущности"
    assert view.frames[0].kind == "ИМЕНОВАНИЕ"
    assert view.frames[0].predicate == "NAME_OF"
    assert [(role.role, role.value) for role in view.frames[0].roles] == [
        ("ENTITY", "Меня"),
        ("NAME", "Илья"),
    ]
    labels = {word.text: word.label for word in view.words}
    assert labels["Меня"] == "ENTITY"
    assert labels["зовут"] == "Именование"
    assert labels["Илья"] == "NAME"
    assert "«Илья» — имя сущности «Меня»" in view.interpretation


def test_event_set_query_is_shown_as_open_event_search_not_predicate_exists():
    source = "Что вчера делал Илья"
    perception = {
        "source_text": source,
        "queries": [
            {
                "local_id": "q1",
                "predicate": _predicate("делал", "делать"),
                "query_mode": "EXISTS",
                "event_set": True,
                "requested_roles": [],
                "actants": [
                    {
                        "role": "TIME",
                        "mention": "вчера",
                        "evidence": {"text": "вчера"},
                    },
                    {
                        "role": "SUBJECT",
                        "mention": "Илья",
                        "evidence": {"text": "Илья"},
                    },
                ],
            }
        ],
    }

    view = build_m1_formalization_view(perception)

    assert view.prompt_type == "ЗАПРОС"
    assert view.prompt_detail == "Найти события по заданным ограничениям"
    assert view.frames[0].kind == "ЗАПРОС СОБЫТИЙ"
    assert view.frames[0].predicate == "СОБЫТИЕ"
    labels = {word.text: word.label for word in view.words}
    assert labels["делал"] == "Открытый предикат"
    assert labels["вчера"] == "TIME"
    assert labels["Илья"] == "SUBJECT"
    assert "Нужно найти события" in view.interpretation