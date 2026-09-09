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
class SourceProjectionCursor:
    """Runtime cursor over ordered semantic roots of one canonical source."""

    source_ref: str
    next_index: int = 0

    def __post_init__(self) -> None:
        if not self.source_ref.strip():
            raise ValueError("SourceProjectionCursor.source_ref must be non-empty")
        if self.next_index < 0:
            raise ValueError("SourceProjectionCursor.next_index must be >= 0")


@dataclass(frozen=True, slots=True)
class SourceScopeSlice:
    """One bounded source slice plus causal/temporal boundary overlap."""

    scope: SourceScope
    cursor: SourceProjectionCursor
    next_cursor: SourceProjectionCursor
    primary_refs: tuple[Ref, ...]
    overlap_refs: tuple[Ref, ...] = ()
    done: bool = False


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

    Normal Workspace projection never silently falls back to raw chunks or drops
    semantic blocks. Complete-source projection has a separate, explicit and
    deterministic compaction operator; it raises this exception if even one
    coherent semantic root plus its compression notice cannot fit.
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
