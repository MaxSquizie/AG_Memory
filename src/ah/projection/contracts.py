from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ah.model import Property, Ref


class ProjectionMode(str, Enum):
    ACTIVE = "ACTIVE"
    DEPENDENCY = "DEPENDENCY"
    INFERENCE = "INFERENCE"


@dataclass(frozen=True, slots=True)
class ProjectionBlock:
    root: Ref | None
    mode: ProjectionMode
    semantic: str
    properties: tuple[Property, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentContext:
    current_input: str
    workspace_blocks: tuple[ProjectionBlock, ...]
    inference_blocks: tuple[ProjectionBlock, ...]
    rendered: str

    @property
    def all_blocks(self) -> tuple[ProjectionBlock, ...]:
        return self.workspace_blocks + self.inference_blocks
