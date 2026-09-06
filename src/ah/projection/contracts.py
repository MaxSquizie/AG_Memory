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
class SourceScope:
    """Runtime provenance scope used for source-bounded recall/projection.

    The scope is reconstructed from canonical H provenance plus the semantic
    content refs attached to those H occurrences.  It is not a canonical node, is
    not persisted independently, and never grants arbitrary access to the graph.
    """

    source_ref: str
    experience_refs: tuple[Ref, ...]
    semantic_roots: tuple[Ref, ...]

    def __post_init__(self) -> None:
        if not self.source_ref.strip():
            raise ValueError("SourceScope.source_ref must be non-empty")


@dataclass(frozen=True, slots=True)
class SourceScopeActivation:
    source_scope: SourceScope
    seeded_refs: tuple[Ref, ...]
    tick_count: int
    workspace_after: tuple[Ref, ...]


@dataclass(frozen=True, slots=True)
class SourceScopedContextResult:
    activation: SourceScopeActivation
    context: "AgentContext"


class ProjectionBudgetExceeded(ValueError):
    """Fail-closed source/context overflow.

    Architecture v4 intentionally leaves iterative oversized-source projection
    open.  Until that protocol is specified, projection must never silently fall
    back to raw chunks or drop semantic blocks.
    """

    def __init__(self, estimated_tokens: int, budget_tokens: int) -> None:
        self.estimated_tokens = int(estimated_tokens)
        self.budget_tokens = int(budget_tokens)
        super().__init__(
            f"AgentContext requires about {self.estimated_tokens} tokens, "
            f"exceeding deterministic budget {self.budget_tokens}; "
            "no raw-chunk or silent-truncation fallback is permitted"
        )


@dataclass(frozen=True, slots=True)
class AgentContext:
    current_input: str
    workspace_blocks: tuple[ProjectionBlock, ...]
    inference_blocks: tuple[ProjectionBlock, ...]
    rendered: str
    # Exact cognitive Workspace roots captured before model-facing semantic
    # compression. Debug/operator only; never serialized into ``rendered``.
    source_workspace_refs: tuple[Ref, ...] = ()
    # Runtime-only provenance/budget diagnostics; never serialized into ``rendered``.
    source_scope_ref: str | None = None
    estimated_tokens: int = 0

    @property
    def all_blocks(self) -> tuple[ProjectionBlock, ...]:
        return self.workspace_blocks + self.inference_blocks
