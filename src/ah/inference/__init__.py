from .attention import AttentionFocusEvent, IgnitionInferenceAttention, InferenceAttention
from .contracts import (
    AllOfGoal,
    AnyOfGoal,
    AssociationGoal,
    CauseEntailmentGoal,
    CounterfactualGoal,
    CognitiveEventKind,
    CognitiveTraceEvent,
    CompositeConclusion,
    DerivedLinkConclusion,
    ExistingRefConclusion,
    ExistsGoal,
    ExactlyOneOfGoal,
    FormulaGoal,
    GoalMode,
    GoalSpec,
    InferenceGoal,
    InferenceOutcome,
    InferenceQuery,
    LogicalStatus,
    MultiRoleBindingConclusion,
    MultiRoleFillGoal,
    RelationGoal,
    RoleBindingConclusion,
    RoleFillGoal,
    StopReason,
    ProofSupport,
)
from .bindings import BindingEnvironment
from .runtime import GoalRuntime
from .context import BranchContext, CounterfactualContext, ProofContext
from .schema import InferenceSchema, InferenceSchemaRegistry
from .materialization import InferenceMaterializer, MaterializationResult
from .query_builder import QueryBuildResult, QueryGoalBuilder as _BaseQueryGoalBuilder
from .counterfactual_goal import CounterfactualSemanticGoalCompiler
from .modal_goal import (
    FormulaPattern,
    FormulaPatternGoal,
    MatrixFormulaPatternGoal,
    ModalInferenceEngine,
    ModalSemanticGoalCompiler,
)
from .event_query import EventMatchGoal, EventQueryGoalBuilder, EventSetInferenceEngine
from .modal_dispatch import ModalTurnGoalCompiler
from .association_goal import AssociationQueryBuildResult, AssociationTurnGoalCompiler

# Public runtime composes independent GoalCompiler/Inference extensions.  Open-event
# retrieval is an InferenceEngine extension, while association execution itself
# remains outside InferenceEngine and is routed to AssociationCoordinator by the
# agent orchestrator.
InferenceEngine = EventSetInferenceEngine
QueryGoalBuilder = EventQueryGoalBuilder
SemanticGoalCompiler = AssociationTurnGoalCompiler
TurnGoalBuilder = AssociationTurnGoalCompiler

__all__ = [
    "AttentionFocusEvent",
    "AllOfGoal",
    "AnyOfGoal",
    "AssociationGoal",
    "AssociationQueryBuildResult",
    "AssociationTurnGoalCompiler",
    "CauseEntailmentGoal",
    "CounterfactualGoal",
    "CounterfactualSemanticGoalCompiler",
    "CognitiveEventKind",
    "CognitiveTraceEvent",
    "CompositeConclusion",
    "DerivedLinkConclusion",
    "EventMatchGoal",
    "EventQueryGoalBuilder",
    "EventSetInferenceEngine",
    "ExistingRefConclusion",
    "ExistsGoal",
    "ExactlyOneOfGoal",
    "FormulaGoal",
    "FormulaPattern",
    "FormulaPatternGoal",
    "MatrixFormulaPatternGoal",
    "GoalMode",
    "GoalSpec",
    "GoalRuntime",
    "InferenceEngine",
    "InferenceAttention",
    "InferenceGoal",
    "InferenceMaterializer",
    "IgnitionInferenceAttention",
    "InferenceOutcome",
    "InferenceQuery",
    "LogicalStatus",
    "MaterializationResult",
    "ModalInferenceEngine",
    "ModalSemanticGoalCompiler",
    "ModalTurnGoalCompiler",
    "MultiRoleBindingConclusion",
    "MultiRoleFillGoal",
    "QueryBuildResult",
    "QueryGoalBuilder",
    "SemanticGoalCompiler",
    "TurnGoalBuilder",
    "RelationGoal",
    "RoleBindingConclusion",
    "RoleFillGoal",
    "StopReason",
    "ProofSupport",
    "BindingEnvironment",
    "ProofContext",
    "BranchContext",
    "CounterfactualContext",
    "InferenceSchema",
    "InferenceSchemaRegistry",
]
