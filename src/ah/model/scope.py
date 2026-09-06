from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ScopeType(str, Enum):
    NORMAL = "NORMAL"
    NEGATED = "NEGATED"
    REPORTED = "REPORTED"
    QUOTED = "QUOTED"
    HYPOTHETICAL = "HYPOTHETICAL"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    MODAL = "MODAL"


@dataclass(frozen=True, slots=True)
class ScopeFrame:
    scope_type: ScopeType = ScopeType.NORMAL


@dataclass(slots=True)
class ScopeStack:
    frames: list[ScopeFrame] = field(default_factory=list)

    def push(self, frame: ScopeFrame) -> None:
        self.frames.append(frame)

    def pop(self) -> ScopeFrame:
        if not self.frames:
            raise IndexError("ScopeStack is empty")
        return self.frames.pop()

    def copy(self) -> "ScopeStack":
        return ScopeStack(list(self.frames))

    def types(self) -> tuple[ScopeType, ...]:
        return tuple(frame.scope_type for frame in self.frames)
