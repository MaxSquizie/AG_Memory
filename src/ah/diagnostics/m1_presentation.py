from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class M1WordView:
    """One source token annotated only from source-grounded M1 candidates."""

    text: str
    label: str
    detail: str = ""
    start: int = 0
    end: int = 0


@dataclass(frozen=True, slots=True)
class M1RoleView:
    role: str
    value: str
    operator: str | None = None
    requested: bool = False
    modifiers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class M1FrameView:
    local_id: str
    kind: str
    predicate: str
    roles: tuple[M1RoleView, ...]
    negated: bool = False
    status: str = "ASSERTED"


@dataclass(frozen=True, slots=True)
class M1FormalizationView:
    """Human-facing summary of the final PerceptionResult.

    This is presentation data only. It never repairs Perception and never writes AH.
    Word annotations come from EvidenceSpan / candidate surface material; ungrounded
    source tokens deliberately remain unclassified instead of being guessed from a
    private marker dictionary.
    """

    prompt_type: str
    prompt_detail: str
    source_text: str
    words: tuple[M1WordView, ...]
    frames: tuple[M1FrameView, ...]
    logic_operator: str | None = None
    interpretation: str = ""
    formula: str = ""


_ROLE_RU = {
    "SUBJECT": "субъект",
    "OBJECT": "объект",
    "RECIPIENT": "адресат",
    "AUXILLIARY": "соучастник",
    "ABSENTEE": "отсутствующий участник",
    "LOCATION": "место",
    "TIME": "время",
    "DURATION": "длительность",
    "TOOL": "инструмент",
    "INSTRUMENT": "инструмент",
    "MATERIAL": "материал",
    "SOURCE": "источник",
    "DESTINATION": "направление",
    "CAUSE": "причина",
    "PURPOSE": "цель",
    "AMOUNT": "количество",
    "HOW-TO": "способ",
    "MANNER": "способ",
    "STATE": "состояние",
    "ENTITY": "именуемая сущность",
    "NAME": "имя",
}

_OPERATOR_RU = {
    "AND": "И",
    "OR": "ИЛИ",
    "XOR": "РОВНО ОДНО",
    "NOT": "НЕ",
    "FALSE": "НЕ",
    "IMPLIES": "ЕСЛИ → ТО",
    "POSSIBLE": "ВОЗМОЖНО",
    "REQUIRED": "НЕОБХОДИМО",
    "PERMITTED": "РАЗРЕШЕНО",
    "FORALL": "ДЛЯ КАЖДОГО",
    "NOT_FORALL": "НЕ ДЛЯ КАЖДОГО",
    "EXISTS": "СУЩЕСТВУЕТ",
    "NOT_EXISTS": "НЕ СУЩЕСТВУЕТ",
}

_TOKEN_RE = re.compile(r"[\wА-Яа-яЁё]+(?:-[\wА-Яа-яЁё]+)*|[^\w\s]", re.UNICODE)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _items(value: Any, name: str) -> tuple[Any, ...]:
    raw = _get(value, name, ()) or ()
    if isinstance(raw, (str, bytes, Mapping)):
        return ()
    return tuple(raw)


def _enum(value: Any, default: str = "") -> str:
    if value is None:
        return default
    raw = getattr(value, "value", value)
    return str(raw)


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().casefold().replace("ё", "е"))


def _evidence(value: Any) -> tuple[str, int | None, int | None] | None:
    evidence = _get(value, "evidence")
    if evidence is None:
        return None
    text = str(_get(evidence, "text", "") or "").strip()
    if not text:
        return None
    start = _get(evidence, "start")
    end = _get(evidence, "end")
    return text, start if isinstance(start, int) else None, end if isinstance(end, int) else None


def _locate_text(
    source: str,
    text: str,
    start: int | None = None,
    end: int | None = None,
) -> tuple[int, int] | None:
    """Locate already-grounded source material without inferring its semantics."""
    if start is not None and end is not None and 0 <= start <= end <= len(source):
        if _norm(source[start:end]) == _norm(text):
            return start, end
        if end < len(source) and _norm(source[start : end + 1]) == _norm(text):
            return start, end + 1
    folded_source = source.casefold().replace("ё", "е")
    folded_text = text.casefold().replace("ё", "е")
    position = folded_source.find(folded_text)
    if position < 0:
        return None
    return position, position + len(text)


def _predicate_text(candidate: Any) -> str:
    predicate = _get(candidate, "predicate")
    normalized = str(_get(predicate, "normalized_hint", "") or "").strip()
    surface = str(_get(predicate, "surface", "") or "").strip()
    return normalized or surface or "?"


def _actant_value(actant: Any) -> str:
    mention = str(_get(actant, "mention", "") or "").strip()
    normalized = str(_get(actant, "normalized_hint", "") or "").strip()
    if mention or normalized:
        return mention or normalized
    composition = _get(actant, "composition")
    if composition is not None:
        operator = _enum(_get(composition, "operator"), "AND")
        members = []
        for member in _items(composition, "members"):
            members.append(
                str(
                    _get(member, "mention", "")
                    or _get(member, "normalized_hint", "")
                    or "?"
                ).strip()
            )
        return f" {operator} ".join(item for item in members if item)
    if _get(actant, "proposition") is not None:
        return "вложенное высказывание"
    entity_ref = str(
        _get(actant, "entity_ref", "")
        or _get(actant, "candidate_ref", "")
        or ""
    ).strip()
    return entity_ref or "?"


def _is_naming(candidate: Any) -> bool:
    return (
        _get(candidate, "owner") is not None
        and bool(str(_get(candidate, "name_value", "") or "").strip())
    )


def _is_event_set_query(candidate: Any) -> bool:
    return bool(_get(candidate, "event_set", False))


def _role_view(actant: Any) -> M1RoleView:
    role = _enum(_get(actant, "role"), "?")
    quantifier = _get(actant, "quantifier")
    operator = None if quantifier is None else _enum(_get(quantifier, "kind"))
    modifiers: list[str] = []
    for relation in _items(actant, "nominal_relations"):
        dependent = str(_get(relation, "dependent_mention", "") or "").strip()
        if dependent:
            kind = _enum(_get(relation, "kind"), "модификатор")
            modifiers.append(f"{dependent} · {kind}")
    return M1RoleView(
        role=role,
        value=_actant_value(actant),
        operator=operator or None,
        modifiers=tuple(modifiers),
    )


def _frame_from_act(candidate: Any, kind: str, index: int) -> M1FrameView:
    local_id = str(_get(candidate, "local_id", "") or f"{kind.lower()}_{index}")
    status = _enum(_get(candidate, "status"), "ASSERTED")

    if _is_naming(candidate):
        owner = _get(candidate, "owner")
        name_value = str(_get(candidate, "name_value", "") or "").strip()
        return M1FrameView(
            local_id=local_id,
            kind="ИМЕНОВАНИЕ",
            predicate="NAME_OF",
            roles=(
                M1RoleView("ENTITY", _actant_value(owner)),
                M1RoleView("NAME", name_value),
            ),
            negated=False,
            status=status,
        )

    if kind == "ЗАПРОС" and _is_event_set_query(candidate):
        return M1FrameView(
            local_id=local_id,
            kind="ЗАПРОС СОБЫТИЙ",
            predicate="СОБЫТИЕ",
            roles=tuple(_role_view(item) for item in _items(candidate, "actants")),
            negated=False,
            status=status,
        )

    roles = [_role_view(item) for item in _items(candidate, "actants")]
    if kind == "ЗАПРОС":
        requested = {
            _enum(item)
            for item in (_get(candidate, "requested_roles", ()) or ())
        }
        scalar = _get(candidate, "requested_role")
        if scalar is not None:
            requested.add(_enum(scalar))
        present = {role.role for role in roles}
        for role in sorted(requested):
            if role and role not in present:
                roles.append(M1RoleView(role=role, value="?", requested=True))
            elif role:
                roles = [
                    M1RoleView(r.role, r.value, r.operator, True, r.modifiers)
                    if r.role == role
                    else r
                    for r in roles
                ]
    return M1FrameView(
        local_id=local_id,
        kind=kind,
        predicate=_predicate_text(candidate),
        roles=tuple(roles),
        negated=bool(_get(candidate, "negated", False)),
        status=status,
    )


def _source_assignments(
    perception: Any,
    source: str,
) -> list[tuple[int, int, str, str, int]]:
    assignments: list[tuple[int, int, str, str, int]] = []

    def add_surface(text: str, label: str, detail: str, priority: int) -> None:
        if not text.strip():
            return
        located = _locate_text(source, text)
        if located is not None:
            assignments.append((*located, label, detail, priority))

    def add_evidence(owner: Any, label: str, detail: str, priority: int) -> None:
        evidence = _evidence(owner)
        if evidence is None:
            return
        text, start, end = evidence
        located = _locate_text(source, text, start, end)
        if located is not None:
            assignments.append((*located, label, detail, priority))

    def add_span(evidence: Any, label: str, detail: str, priority: int) -> None:
        if evidence is None:
            return
        text = str(_get(evidence, "text", "") or "").strip()
        if not text:
            return
        start = _get(evidence, "start")
        end = _get(evidence, "end")
        located = _locate_text(
            source,
            text,
            start if isinstance(start, int) else None,
            end if isinstance(end, int) else None,
        )
        if located is not None:
            assignments.append((*located, label, detail, priority))

    acts = (
        [(item, "ФАКТ") for item in _items(perception, "assertions")]
        + [(item, "ЗАПРОС") for item in _items(perception, "queries")]
        + [(item, "КОМАНДА") for item in _items(perception, "commands")]
    )
    for act, kind in acts:
        predicate = _get(act, "predicate")
        pred_detail = str(
            _get(predicate, "normalized_hint", "")
            or _get(predicate, "surface", "")
            or ""
        ).strip()

        if _is_naming(act):
            owner = _get(act, "owner")
            add_evidence(owner, "ENTITY", "именуемая сущность", 100)
            add_evidence(predicate, "Именование", "NAME_OF", 95)
            add_surface(
                str(_get(predicate, "surface", "") or ""),
                "Именование",
                "NAME_OF",
                96,
            )
            name_value = str(_get(act, "name_value", "") or "").strip()
            selected = [
                item
                for item in _items(act, "actants")
                if _norm(_actant_value(item)) == _norm(name_value)
            ]
            if len(selected) == 1:
                add_evidence(selected[0], "NAME", "имя", 110)
            else:
                add_surface(name_value, "NAME", "имя", 105)
            continue

        if kind == "ЗАПРОС" and _is_event_set_query(act):
            for query_evidence in _items(act, "query_operator_evidence"):
                add_span(query_evidence, "Оператор запроса", "QUERY", 115)
            add_evidence(
                predicate,
                "Открытый предикат",
                "запрашивается событие",
                90,
            )
            add_surface(
                str(_get(predicate, "surface", "") or ""),
                "Открытый предикат",
                "запрашивается событие",
                92,
            )
        else:
            add_evidence(predicate, "Предикат", pred_detail, 70)
            add_surface(
                str(_get(predicate, "surface", "") or ""),
                "Предикат",
                pred_detail,
                72,
            )

        for actant in _items(act, "actants"):
            role = _enum(_get(actant, "role"), "Роль")
            role_detail = _ROLE_RU.get(role, "семантическая роль")
            add_evidence(actant, role, role_detail, 40)
            quantifier = _get(actant, "quantifier")
            if quantifier is not None:
                qkind = _enum(_get(quantifier, "kind"))
                add_evidence(quantifier, "Квантор", qkind, 90)
                add_surface(
                    str(_get(quantifier, "surface", "") or ""),
                    "Квантор",
                    qkind,
                    95,
                )
            for relation in _items(actant, "nominal_relations"):
                dependent = str(
                    _get(relation, "dependent_mention", "") or ""
                ).strip()
                relation_kind = _enum(
                    _get(relation, "kind"), "NOMINAL_MODIFIER"
                )
                if dependent:
                    add_surface(
                        dependent,
                        "Модификатор",
                        relation_kind,
                        80,
                    )
    return assignments


def _word_views(perception: Any, source: str) -> tuple[M1WordView, ...]:
    assignments = _source_assignments(perception, source)
    out: list[M1WordView] = []
    for match in _TOKEN_RE.finditer(source):
        start, end = match.span()
        candidates = [
            item
            for item in assignments
            if item[0] < end and start < item[1]
        ]
        if candidates:
            chosen = max(
                candidates,
                key=lambda item: (item[4], -(item[1] - item[0])),
            )
            label, detail = chosen[2], chosen[3]
        else:
            label, detail = "—", "не выделено M1"
        out.append(M1WordView(match.group(0), label, detail, start, end))
    return tuple(out)


def _expr_formula(expr: Any, frame_names: Mapping[str, str]) -> str:
    if expr is None:
        return ""
    operator = _enum(_get(expr, "operator"))
    ref = str(_get(expr, "ref", "") or "")
    if operator == "REF":
        return frame_names.get(ref, ref or "?")
    members = [_expr_formula(item, frame_names) for item in _items(expr, "members")]
    members = [item for item in members if item]
    if operator in {"NOT", "FALSE", "POSSIBLE", "REQUIRED", "PERMITTED"} and members:
        return f"{operator}({members[0]})"
    if operator == "IMPLIES" and len(members) == 2:
        return f"{members[0]} → {members[1]}"
    joiner = f" {operator or '?'} "
    return "(" + joiner.join(members) + ")" if members else operator


def _prompt_type(perception: Any) -> tuple[str, str]:
    assertions = _items(perception, "assertions")
    queries = _items(perception, "queries")
    commands = _items(perception, "commands")
    conditionals = _items(perception, "conditionals")
    roots = _items(perception, "proposition_roots")
    asserted = [
        item
        for item in assertions
        if _enum(_get(item, "status"), "ASSERTED") == "ASSERTED"
    ]

    if queries and not asserted and not commands:
        if all(_is_event_set_query(query) for query in queries):
            return "ЗАПРОС", "Найти события по заданным ограничениям"
        requested: list[str] = []
        modes: list[str] = []
        for query in queries:
            modes.append(_enum(_get(query, "query_mode"), "EXISTS"))
            for role in (_get(query, "requested_roles", ()) or ()):
                name = _enum(role)
                if name and name not in requested:
                    requested.append(name)
        if requested:
            return "ЗАПРОС", "Найти: " + ", ".join(requested)
        if modes and all(mode == "EXISTS" for mode in modes):
            return "ЗАПРОС", "Проверить существование / истинность"
        return "ЗАПРОС", "Получить значение"
    if commands and not asserted and not queries:
        return "КОМАНДА", "Выполнить действие"
    if conditionals and not queries and not commands:
        return "УСЛОВИЕ", "ЕСЛИ → ТО"
    if roots and not queries and not commands:
        op = _enum(_get(_get(roots[0], "expression"), "operator"))
        return (
            "ФАКТ · ЛОГИЧЕСКОЕ ВЫРАЖЕНИЕ",
            _OPERATOR_RU.get(op, op),
        )
    if asserted and not queries and not commands:
        if all(_is_naming(item) for item in asserted):
            return "ФАКТ · ИМЕНОВАНИЕ", "Задаёт имя существующей сущности"
        return "ФАКТ", "Утверждение о мире"
    if assertions or queries or commands:
        return "СОСТАВНОЙ ПРОМПТ", "Несколько речевых актов"
    return "НЕ ФОРМАЛИЗОВАНО", "M1 не выделил семантический акт"


def _human_interpretation(
    prompt_type: str,
    frames: Sequence[M1FrameView],
    logic: str | None,
) -> str:
    if not frames:
        return "M1 не построил предикатно-ролевую формализацию."
    parts: list[str] = []
    for frame in frames:
        known = [role for role in frame.roles if not role.requested]
        requested = [role.role for role in frame.roles if role.requested]
        role_text = (
            "; ".join(f"{role.role} = {role.value}" for role in known)
            or "без заполненных ролей"
        )
        if frame.kind == "ИМЕНОВАНИЕ":
            entity = next(
                (role.value for role in frame.roles if role.role == "ENTITY"),
                "?",
            )
            name = next(
                (role.value for role in frame.roles if role.role == "NAME"),
                "?",
            )
            parts.append(f"«{name}» — имя сущности «{entity}».")
        elif frame.kind == "ЗАПРОС СОБЫТИЙ":
            parts.append(
                f"Нужно найти события; ограничения: {role_text}."
            )
        elif frame.kind == "ЗАПРОС":
            target = ", ".join(requested) or "истинность события"
            parts.append(
                f"Нужно найти {target} для «{frame.predicate}»; "
                f"известно: {role_text}."
            )
        elif frame.kind == "КОМАНДА":
            parts.append(f"Команда «{frame.predicate}»: {role_text}.")
        else:
            prefix = "Отрицается факт" if frame.negated else "Факт"
            parts.append(f"{prefix} «{frame.predicate}»: {role_text}.")
        for role in frame.roles:
            if role.operator:
                parts.append(
                    f"Квантор {role.operator} относится к "
                    f"{role.role} «{role.value}»."
                )
    if logic:
        parts.append(
            "Логическая связь между частями: "
            f"{_OPERATOR_RU.get(logic, logic)} ({logic})."
        )
    return " ".join(parts)


def build_m1_formalization_view(
    perception: Any,
    *,
    source_text: str | None = None,
) -> M1FormalizationView:
    """Build a deterministic human-readable view from PerceptionResult or its JSON form."""
    source = str(
        source_text
        if source_text is not None
        else _get(perception, "source_text", "")
        or ""
    )
    prompt_type, prompt_detail = _prompt_type(perception)

    frames: list[M1FrameView] = []
    for index, item in enumerate(_items(perception, "assertions"), 1):
        frames.append(_frame_from_act(item, "ФАКТ", index))
    for index, item in enumerate(_items(perception, "queries"), 1):
        frames.append(_frame_from_act(item, "ЗАПРОС", index))
    for index, item in enumerate(_items(perception, "commands"), 1):
        frames.append(_frame_from_act(item, "КОМАНДА", index))

    roots = _items(perception, "proposition_roots")
    logic = None
    formula = ""
    if roots:
        expression = _get(roots[0], "expression")
        logic = _enum(_get(expression, "operator")) or None
        names = {frame.local_id: frame.predicate for frame in frames}
        formula = _expr_formula(expression, names)
    elif _items(perception, "conditionals"):
        logic = "IMPLIES"
        formula = "ЕСЛИ → ТО"

    return M1FormalizationView(
        prompt_type=prompt_type,
        prompt_detail=prompt_detail,
        source_text=source,
        words=_word_views(perception, source),
        frames=tuple(frames),
        logic_operator=logic,
        interpretation=_human_interpretation(prompt_type, frames, logic),
        formula=formula,
    )


def _role_title(role: str) -> str:
    human = _ROLE_RU.get(role)
    return role if not human else f"{role} · {human}"


def render_m1_formalization_html(view: M1FormalizationView) -> str:
    """Render the compact M1 meaning view with fixed tables and no crossing edges."""
    chunks = [
        f"<h2>{escape(view.prompt_type)}</h2>",
        (
            f"<p><b>{escape(view.prompt_detail)}</b></p>"
            if view.prompt_detail
            else ""
        ),
        f"<p style='font-size:16px'><b>{escape(view.source_text)}</b></p>",
        "<h3>Что означает каждый фрагмент</h3>",
    ]

    if view.words:
        columns = 4
        chunks.append(
            "<table border='0' cellspacing='6' cellpadding='6' width='100%'>"
        )
        for start in range(0, len(view.words), columns):
            chunks.append("<tr>")
            batch = view.words[start : start + columns]
            for word in batch:
                label = escape(word.label)
                detail = escape(word.detail)
                chunks.append(
                    "<td valign='top' style='border:1px solid; min-width:120px'>"
                    f"<div style='font-size:15px'><b>{escape(word.text)}</b></div>"
                    f"<div>{label}</div><small>{detail}</small></td>"
                )
            for _ in range(columns - len(batch)):
                chunks.append("<td></td>")
            chunks.append("</tr>")
        chunks.append("</table>")

    chunks.append("<h3>Итоговая схема смысла</h3>")
    if view.logic_operator:
        chunks.append(
            "<p align='center'><b>"
            + escape(_OPERATOR_RU.get(view.logic_operator, view.logic_operator))
            + f" ({escape(view.logic_operator)})</b></p>"
        )
    if not view.frames:
        chunks.append("<p>Предикатно-ролевая схема не построена.</p>")
    for frame in view.frames:
        state = []
        if frame.negated:
            state.append("NOT")
        if frame.status and frame.status != "ASSERTED":
            state.append(frame.status)
        state_text = " · ".join(state)
        chunks.append(
            "<table border='1' cellspacing='0' cellpadding='8' width='100%'>"
        )
        chunks.append(
            "<tr><td colspan='4' align='center'>"
            f"<small>{escape(frame.kind)}</small><br>"
            f"<b style='font-size:16px'>{escape(frame.predicate)}</b>"
            + (f"<br><b>{escape(state_text)}</b>" if state_text else "")
            + "</td></tr>"
        )
        roles = list(frame.roles)
        if roles:
            for start in range(0, len(roles), 4):
                chunks.append("<tr>")
                batch = roles[start : start + 4]
                for role in batch:
                    operator = (
                        f"<b>{escape(_OPERATOR_RU.get(role.operator, role.operator))} "
                        f"({escape(role.operator)})</b><br>"
                        if role.operator
                        else ""
                    )
                    value = "?" if role.requested else role.value
                    mods = "".join(
                        f"<br><small>↳ {escape(item)}</small>"
                        for item in role.modifiers
                    )
                    chunks.append(
                        "<td align='center' valign='top'>"
                        f"{operator}<small>{escape(_role_title(role.role))}</small><br>"
                        f"<b>{escape(value)}</b>{mods}</td>"
                    )
                for _ in range(4 - len(batch)):
                    chunks.append("<td></td>")
                chunks.append("</tr>")
        chunks.append("</table><br>")

    chunks.append("<h3>Человеческое прочтение</h3>")
    chunks.append(f"<p>{escape(view.interpretation)}</p>")
    if view.formula:
        chunks.append("<h4>Структура формулы</h4>")
        chunks.append(f"<p><code>{escape(view.formula)}</code></p>")
    chunks.append(
        "<p><small>Слова с пометкой «не выделено M1» намеренно не "
        "классифицируются интерфейсом: экран показывает результат "
        "формализации, а не достраивает его собственными эвристиками.</small></p>"
    )
    return "".join(chunks)