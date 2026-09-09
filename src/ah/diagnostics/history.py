from __future__ import annotations

from collections import deque
from typing import Generic, Iterable, TypeVar


T = TypeVar("T")


class BoundedHistory(Generic[T]):
    """Small insertion-ordered diagnostic history with explicit eviction."""

    def __init__(self, limit: int = 20) -> None:
        if limit <= 0:
            raise ValueError("history limit must be positive")
        self.limit = int(limit)
        self._items: deque[T] = deque(maxlen=self.limit)

    def append(self, item: T) -> None:
        self._items.append(item)

    def extend(self, items: Iterable[T]) -> None:
        self._items.extend(items)

    def clear(self) -> None:
        self._items.clear()

    @property
    def items(self) -> tuple[T, ...]:
        return tuple(self._items)

    @property
    def latest(self) -> T | None:
        return self._items[-1] if self._items else None

    def __len__(self) -> int:
        return len(self._items)
