from .agent_context import ContextProjector as _BaseContextProjector
from .event_context import EventAwareContextProjector
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
# implementation available internally while exposing the event-set aware extension.
ContextProjector = EventAwareContextProjector

__all__ = [
    "AgentContext",
    "AgentContextDiagnostic",
    "AssociationContextProjector",
    "ContextProjector",
    "EventAwareContextProjector",
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
