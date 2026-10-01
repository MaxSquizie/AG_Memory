# -*- coding: utf-8 -*-
"""InterpretationRunBinding — CAS ownership of an interpretation version (§0.8, WP0.1).

Guarantees that a given (observation_id, interpretation_version) is owned by at most one run
at a time, so concurrent runs on the same observation are serialized and exactly one wins.
``acquire`` is compare-and-set: it fails if another owner already holds the key; re-acquiring
the same key with the same owner is idempotent. When a :class:`JournalChannel` is supplied each
transition is also appended durably (audit + crash visibility).
"""

from __future__ import annotations

from typing import Optional


class InterpretationRunBinding:
    def __init__(self, journal=None) -> None:
        self._journal = journal
        # key=(observation_id, version) -> owner
        self._bindings: dict[tuple[str, int], str] = {}

    def acquire(self, owner: str, observation_id: str, version: int) -> bool:
        """Claim ownership. Returns False if a DIFFERENT owner already holds the key."""
        key = (observation_id, version)
        current = self._bindings.get(key)
        if current is not None and current != owner:
            return False  # CAS failure: another run owns this interpretation version
        self._bindings[key] = owner
        if self._journal is not None:
            self._journal.append(
                "resolution_log",
                {"kind": "run_bind", "observation_id": observation_id, "version": version, "owner": owner},
                run_id=owner,
            )
        return True

    def release(self, owner: str, observation_id: str, version: int) -> bool:
        key = (observation_id, version)
        if self._bindings.get(key) == owner:
            del self._bindings[key]
            if self._journal is not None:
                self._journal.append(
                    "resolution_log",
                    {"kind": "run_release", "observation_id": observation_id, "version": version, "owner": owner},
                    run_id=owner,
                )
            return True
        return False

    def holder(self, observation_id: str, version: int) -> Optional[str]:
        return self._bindings.get((observation_id, version))
