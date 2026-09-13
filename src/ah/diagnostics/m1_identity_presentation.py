from __future__ import annotations

"""Presentation-only adapter for typed entity identity queries.

The base M1 renderer intentionally never reinterprets source text.  Identity query
semantics arrived later as a typed Perception contract, so this module maps only
that explicit contract into M1 display objects.  It does not inspect words to decide
whether a query is about identity and cannot repair an untyped parse.
"""

from dataclasses import replace
from typing import Any, Mapping

from . import m1_presentation as _base


_BASE_BUILD = _base.build_m1_formalization_view
_BASE_RENDER = _base.render_m1_formalization_html


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _items(value: Any, name: str) -> tuple[Any, ...]:
    raw = _get(value, name, ()) or ()
    if isinstance(raw, (str, bytes, Mapping)):
        return ()
    return tuple(raw)


def _identity_query(value: Any) -> bool:
    return bool(_get(value, "identity_query", False))


def _actant_text(value: Any) -> str:
    return str(
        _get(value, "mention", "")
        or _get(value, "normalized_hint", "")
        or "?"
    ).strip()


def _span(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    start = _get(value, "start")
    end = _get(value, "end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end:
        return start, end
    evidence = _get(value, "evidence")
    if evidence is None:
        return None
    start = _get(evidence, "start")
    end = _get(evidence, "end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end:
        return start, end
    return None


def _rewrite_words(view, queries):
    words = list(view.words)

    def mark(span: tuple[int, int] | None, label: str, detail: str) -> None:
        if span is None:
            return
        left, right = span
        for index, word in enumerate(words):
            if word.start < right and left < word.end:
                words[index] = replace(word, label=label, detail=detail)

    for query in queries:
        target = _get(query, "target")
        mark(_span(target), "ENTITY", "идентифицируемая сущность")
        for evidence in _items(query, "query_operator_evidence"):
            mark(_span(evidence), "Оператор запроса", "IDENTITY")
    return tuple(words)


def build_m1_formalization_view(perception: Any, *, source_text: str | None = None):
    view = _BASE_BUILD(perception, source_text=source_text)
    queries = tuple(
        query for query in _items(perception, "queries") if _identity_query(query)
    )
    if not queries:
        return view

    replacement_frames = {}
    for index, query in enumerate(queries, start=1):
        target = _get(query, "target")
        local_id = str(_get(query, "local_id", "") or f"identity_{index}")
        replacement_frames[local_id] = _base.M1FrameView(
            local_id=local_id,
            kind="ЗАПРОС ИДЕНТИЧНОСТИ",
            predicate="IDENTITY_OF",
            roles=(
                _base.M1RoleView("ENTITY", _actant_text(target)),
                _base.M1RoleView("NAME", "?", requested=True),
            ),
            negated=False,
            status="ASSERTED",
        )

    frames = tuple(
        replacement_frames.get(frame.local_id, frame)
        for frame in view.frames
    )
    # A typed query can theoretically be introduced without a corresponding generic
    # base frame in serialized legacy data. Keep the presentation complete without
    # fabricating source semantics.
    present = {frame.local_id for frame in frames}
    frames = frames + tuple(
        frame
        for local_id, frame in replacement_frames.items()
        if local_id not in present
    )

    assertions = _items(perception, "assertions")
    commands = _items(perception, "commands")
    all_queries = _items(perception, "queries")
    identity_only = (
        not assertions
        and not commands
        and all_queries
        and all(_identity_query(query) for query in all_queries)
    )
    if identity_only:
        prompt_type = "ЗАПРОС"
        prompt_detail = "Найти имя / идентичность сущности"
        descriptions = []
        for query in queries:
            descriptions.append(
                f"Нужно определить имя/идентичность сущности «{_actant_text(_get(query, 'target'))}»."
            )
        interpretation = " ".join(descriptions)
    else:
        prompt_type = view.prompt_type
        prompt_detail = view.prompt_detail
        identity_text = " ".join(
            f"Нужно определить имя/идентичность сущности «{_actant_text(_get(query, 'target'))}»."
            for query in queries
        )
        interpretation = (view.interpretation + " " + identity_text).strip()

    return replace(
        view,
        prompt_type=prompt_type,
        prompt_detail=prompt_detail,
        words=_rewrite_words(view, queries),
        frames=frames,
        interpretation=interpretation,
    )


def render_m1_formalization_html(view):
    return _BASE_RENDER(view)


def install_identity_m1_presentation() -> None:
    """Install typed-contract presentation before GUI imports the base functions."""

    _base.build_m1_formalization_view = build_m1_formalization_view
    _base.render_m1_formalization_html = render_m1_formalization_html
