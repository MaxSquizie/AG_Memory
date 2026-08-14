from __future__ import annotations

from collections import defaultdict
from typing import Protocol
from uuid import uuid4

from ah.model import RefKind


class UidGenerator(Protocol):
    def new(self, kind: RefKind) -> str: ...


class UuidUidGenerator:
    def new(self, kind: RefKind) -> str:
        return f"{kind.value}_{uuid4().hex}"


class SequentialUidGenerator:
    """Deterministic UID generator for tests and reproducible fixtures."""

    def __init__(self) -> None:
        self._counters: dict[RefKind, int] = defaultdict(int)

    def new(self, kind: RefKind) -> str:
        self._counters[kind] += 1
        return f"{kind.value}_{self._counters[kind]}"
