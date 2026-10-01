# -*- coding: utf-8 -*-
"""Reader contract (V7 §7.4) — the guardrail every memory reader routes through.

A *fact-requiring* goal (one whose answer must be a settled world fact) may only be satisfied by
items that are actually facts. The formalizer emits several NON-fact item kinds that must never be
silently promoted to facts:

* ``HYPOTHETICAL`` — an explicit non-asserted attitude;
* ``EMBEDDED``     — reported / quoted / modal content (true of the report, not of the world);
* ``OBSERVATION_RECORD`` — an unresolved observation with open alternatives.

This module is the single seam that enforces §7.4: :func:`admit_for_fact_goal` admits only FACT
items by default and promotes each non-fact kind ONLY when its own explicit allowance flag is set.
Enabling one flag never leaks another (allowing hypotheticals does not admit embedded content).
Every reader answering a fact-requiring goal must call this — there is no other path in which a
non-fact becomes a fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class ItemStatus(str, Enum):
    FACT = "FACT"
    HYPOTHETICAL = "HYPOTHETICAL"
    EMBEDDED = "EMBEDDED"
    OBSERVATION_RECORD = "OBSERVATION_RECORD"


@dataclass(frozen=True)
class MemoryItem:
    uid: str
    status: ItemStatus
    payload: dict = field(default_factory=dict)


# Each non-fact status maps to the explicit flag that alone may admit it.
_FLAG_FOR = {
    ItemStatus.HYPOTHETICAL: "allow_hypothetical",
    ItemStatus.EMBEDDED: "allow_embedded",
    ItemStatus.OBSERVATION_RECORD: "allow_observation_record",
}


def is_fact_admissible(item: MemoryItem, *, allow_hypothetical=False, allow_embedded=False,
                       allow_observation_record=False) -> bool:
    """True iff ``item`` may satisfy a fact-requiring goal under the given explicit allowances."""
    if item.status == ItemStatus.FACT:
        return True
    flag = _FLAG_FOR.get(item.status)
    if flag is None:  # unknown status: never silently admitted as a fact
        return False
    return locals()[flag]


def admit_for_fact_goal(
    items: Iterable[MemoryItem], *, allow_hypothetical=False, allow_embedded=False,
    allow_observation_record=False,
) -> list[MemoryItem]:
    """The §7.4 gate: only FACT items pass by default; each non-fact kind needs its own flag."""
    return [it for it in items if is_fact_admissible(
        it, allow_hypothetical=allow_hypothetical, allow_embedded=allow_embedded,
        allow_observation_record=allow_observation_record)]
