from .agent_context import ContextProjector as _BaseContextProjector
from .event_context import EventAwareContextProjector
from .set_valued_context import SetValuedContextProjector
from .association_context import AssociationContextProjector
from .contracts import (
    AgentContext,
    AgentContextDiagnostic,
    ProjectionBlock,
    ProjectionMode,
    ProjectionBudgetExceeded,
    SourceProjectionCursor,
    SourceScope,
    SourceScopeSlice,
    SourceScopeActivation,
    SourceScopedContextResult,
    WorkspaceContextDiagnostic,
)
from .function_registry import FunctionRegistry, FunctionSpec
from .semantic_projection import SemanticProjector
from .source_scope import (
    SourceScopeActivator, SourceScopeNotFound, SourceScopeResolver,
    SourceScopedContextService,
)

# Runtime construction imports ContextProjector from this package. Keep the base
# implementations available internally while exposing complete set-valued WH
# retrieval on top of the event/identity aware projector.
ContextProjector = SetValuedContextProjector

__all__ = [
    "AgentContext",
    "AgentContextDiagnostic",
    "AssociationContextProjector",
    "ContextProjector",
    "EventAwareContextProjector",
    "SetValuedContextProjector",
    "FunctionRegistry",
    "FunctionSpec",
    "ProjectionBlock",
    "ProjectionMode",
    "ProjectionBudgetExceeded",
    "SemanticProjector",
    "SourceProjectionCursor",
    "SourceScope",
    "SourceScopeSlice",
    "SourceScopeActivation",
    "SourceScopeActivator",
    "SourceScopedContextResult",
    "SourceScopedContextService",
    "SourceScopeNotFound",
    "SourceScopeResolver",
    "WorkspaceContextDiagnostic",
]
