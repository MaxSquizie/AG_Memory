from __future__ import annotations

from ah.core import AHCore
from ah.model import Ref


_HISTORY_ATTR = "_runtime_association_result_history"


def pair_key(left: Ref, right: Ref) -> tuple[str, str]:
    return tuple(sorted((left.uid, right.uid)))


def constraint_key(constraints=()) -> tuple[tuple[str, str, str], ...]:
    """Canonical runtime key for typed association search restrictions.

    ``constraints`` intentionally uses a structural protocol (``role`` + ``value``)
    instead of importing the inference-layer dataclass.  Association history is a
    low-level runtime service and must not introduce an association<->inference
    import cycle.
    """

    rows: list[tuple[str, str, str]] = []
    for item in constraints or ():
        role = getattr(item, "role", None)
        value = getattr(item, "value", None)
        if role is None or value is None:
            try:
                role, value = item
            except Exception as exc:  # pragma: no cover - defensive contract guard
                raise TypeError("Association constraint must expose role and value") from exc
        rows.append((str(getattr(role, "value", role)), value.kind.value, value.uid))
    rows.sort()
    return tuple(rows)


def scope_key(left: Ref, right: Ref, constraints=()) -> tuple[tuple[str, str], tuple[tuple[str, str, str], ...]]:
    return pair_key(left, right), constraint_key(constraints)


def _history(core: AHCore) -> dict[tuple, list[str]]:
    value = getattr(core, _HISTORY_ATTR, None)
    if not isinstance(value, dict):
        value = {}
        setattr(core, _HISTORY_ATTR, value)
    return value


def emitted_signatures(core: AHCore, left: Ref, right: Ref, constraints=()) -> tuple[str, ...]:
    return tuple(_history(core).get(scope_key(left, right, constraints), ()))


def clear_signatures(core: AHCore, left: Ref, right: Ref, constraints=()) -> None:
    _history(core).pop(scope_key(left, right, constraints), None)


def remember_signature(
    core: AHCore,
    left: Ref,
    right: Ref,
    signature: str | None,
    constraints=(),
) -> None:
    value = (signature or "").strip()
    if not value:
        return
    rows = _history(core).setdefault(scope_key(left, right, constraints), [])
    if value not in rows:
        rows.append(value)
