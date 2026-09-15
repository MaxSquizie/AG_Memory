from __future__ import annotations

from ah.core import AHCore
from ah.model import Ref


_HISTORY_ATTR = "_runtime_association_result_history"


def pair_key(left: Ref, right: Ref) -> tuple[str, str]:
    return tuple(sorted((left.uid, right.uid)))


def _history(core: AHCore) -> dict[tuple[str, str], list[str]]:
    value = getattr(core, _HISTORY_ATTR, None)
    if not isinstance(value, dict):
        value = {}
        setattr(core, _HISTORY_ATTR, value)
    return value


def emitted_signatures(core: AHCore, left: Ref, right: Ref) -> tuple[str, ...]:
    return tuple(_history(core).get(pair_key(left, right), ()))


def clear_signatures(core: AHCore, left: Ref, right: Ref) -> None:
    _history(core).pop(pair_key(left, right), None)


def remember_signature(core: AHCore, left: Ref, right: Ref, signature: str | None) -> None:
    value = (signature or "").strip()
    if not value:
        return
    rows = _history(core).setdefault(pair_key(left, right), [])
    if value not in rows:
        rows.append(value)
