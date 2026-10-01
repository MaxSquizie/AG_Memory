# -*- coding: utf-8 -*-
"""Temporal ledger and time-bounded assertions (V7 §6.3).

A fact is not just true/false but true *over an interval*. :class:`TimeAssertion` carries a
half-open validity interval ``[valid_from, valid_until)`` where ``valid_until=None`` means the
fact is still open (currently true). The ledger answers "was X true at time t?" and "what was
the state of the world at t?" — the temporal queries the rest of the architecture needs when a
later observation supersedes an earlier one.

Time is a monotonic integer ordinal (not wall-clock), which keeps the mechanism deterministic
and testable; a concrete clock can be mapped onto it by the caller. When a store is supplied,
open/close transitions are appended durably so a crash cannot lose the temporal history.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .store_interface import JournalRecord, Store


@dataclass(frozen=True)
class TimeAssertion:
    assertion_id: str
    valid_from: int
    valid_until: int | None = None  # None => still open (currently true)
    tags: frozenset[str] = frozenset()

    def covers(self, t: int) -> bool:
        """Half-open interval: true at ``t`` iff from <= t and (open or t < until)."""
        return self.valid_from <= t and (self.valid_until is None or t < self.valid_until)


class TemporalLedger:
    def __init__(self, store: Store | None = None) -> None:
        self._store = store
        # assertion_id -> chronological list of intervals
        self._intervals: dict[str, list[TimeAssertion]] = {}

    def assert_true(self, assertion_id: str, at: int, tags: frozenset[str] = frozenset()) -> TimeAssertion:
        """Open a new interval ``[at, ∞)`` for the fact."""
        ta = TimeAssertion(assertion_id, at, None, frozenset(tags))
        self._intervals.setdefault(assertion_id, []).append(ta)
        if self._store is not None:
            self._store.append_journal(
                "resolution_log", JournalRecord("resolution_log", "", {"kind": "time_open", "id": assertion_id, "at": at})
            )
        return ta

    def close(self, assertion_id: str, at: int) -> bool:
        """Close the most recent still-open interval at ``at``. False if none is open."""
        ivs = self._intervals.get(assertion_id)
        if not ivs:
            return False
        for i in range(len(ivs) - 1, -1, -1):
            if ivs[i].valid_until is None:
                self._intervals[assertion_id][i] = replace(ivs[i], valid_until=at)
                if self._store is not None:
                    self._store.append_journal(
                        "resolution_log", JournalRecord("resolution_log", "", {"kind": "time_close", "id": assertion_id, "at": at})
                    )
                return True
        return False

    def is_true_at(self, assertion_id: str, t: int) -> bool:
        return any(iv.covers(t) for iv in self._intervals.get(assertion_id, []))

    def state_at(self, t: int) -> set[str]:
        """All facts true at time ``t``."""
        out = set()
        for aid, ivs in self._intervals.items():
            if any(iv.covers(t) for iv in ivs):
                out.add(aid)
        return out

    def intervals(self, assertion_id: str) -> tuple[TimeAssertion, ...]:
        return tuple(self._intervals.get(assertion_id, ()))


def assert_true_at(ledger: TemporalLedger, facts: Sequence[tuple[str, int]]) -> None:
    """Convenience: open several facts at their respective times."""
    for aid, t in facts:
        ledger.assert_true(aid, t)
