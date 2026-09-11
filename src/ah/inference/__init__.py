from .attention import AttentionFocusEvent, IgnitionInferenceAttention, InferenceAttention
from .contracts import (
    AllOfGoal,
    AssociationGoal,
    CauseEntailmentGoal,
    CounterfactualGoal,
    CognitiveEventKind,
    CognitiveTraceEvent,
    CompositeConclusion,
    DerivedLinkConclusion,
    ExistingRefConclusion,
    ExistsGoal,
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
from .query_builder import QueryBuildResult, QueryGoalBuilder
from .counterfactual_goal import CounterfactualSemanticGoalCompiler
from .modal_goal import (
    FormulaPattern,
    FormulaPatternGoal,
    ModalInferenceEngine,
    ModalSemanticGoalCompiler,
)
from .modal_dispatch import ModalTurnGoalCompiler
from .association_goal import AssociationQueryBuildResult, AssociationTurnGoalCompiler

# Public runtime composes independent GoalCompiler extensions in one inheritance
# chain. Association execution itself remains outside InferenceEngine and is routed
# to AssociationCoordinator by the agent orchestrator.
InferenceEngine = ModalInferenceEngine
SemanticGoalCompiler = AssociationTurnGoalCompiler
TurnGoalBuilder = AssociationTurnGoalCompiler

__all__ = [
    "AttentionFocusEvent",
    "AllOfGoal",
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
    "ExistingRefConclusion",
    "ExistsGoal",
    "FormulaGoal",
    "FormulaPattern",
    "FormulaPatternGoal",
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
