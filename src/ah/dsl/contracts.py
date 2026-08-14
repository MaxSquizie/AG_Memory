from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DSLResult:
    command: str
    value: Any
    count: int | None = None


class DSLError(ValueError):
    pass
