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

# Public runtime composes the independent GoalCompiler extensions in one inheritance
# chain.  The mature base implementations remain in engine.py/query_builder.py;
# counterfactual and modal layers add only their typed runtime boundaries.
InferenceEngine = ModalInferenceEngine
SemanticGoalCompiler = ModalSemanticGoalCompiler
TurnGoalBuilder = ModalSemanticGoalCompiler

__all__ = [
    "AttentionFocusEvent",
    "AllOfGoal",
    "AssociationGoal",
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
