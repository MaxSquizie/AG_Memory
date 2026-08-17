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
class WorkspaceContextDiagnostic:
    """Debug-only explanation of one ACTIVE memory block.

    These fields are never serialized into ``AgentContext.rendered`` and therefore
    are not visible to the Agent LLM. They exist solely so the operator can inspect
    why a semantic block was present in the model input.
    """

    position: int
    root: Ref
    semantic: str
    kind: str
    domain: str | None
    excitation: float
    output: float
    decay_age: int
    lifecycle_state: str | None


@dataclass(frozen=True, slots=True)
class AgentContextDiagnostic:
    """Exact projection-time debug snapshot for one AgentContext."""

    tick_index: int
    workspace_threshold: float
    workspace: tuple[WorkspaceContextDiagnostic, ...]
    settle_ticks: int = 0


@dataclass(frozen=True, slots=True)
class AgentContext:
    current_input: str
    workspace_blocks: tuple[ProjectionBlock, ...]
    inference_blocks: tuple[ProjectionBlock, ...]
    rendered: str
    # Exact cognitive Workspace roots captured before model-facing semantic
    # compression. Debug/operator only; never serialized into ``rendered``.
    source_workspace_refs: tuple[Ref, ...] = ()

    @property
    def all_blocks(self) -> tuple[ProjectionBlock, ...]:
        return self.workspace_blocks + self.inference_blocks
