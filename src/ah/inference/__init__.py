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
from .materialization import MaterializationResult
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
from .identity_query import (
    EntityIdentityGoal,
    EntityIdentityInferenceEngine,
    EntityIdentityQueryGoalBuilder,
)
from .quantified_exists import (
    DerivedAtomConclusion,
    QuantifiedExistsInferenceEngine,
    QuantifiedInferenceMaterializer,
)
from .modal_dispatch import ModalTurnGoalCompiler
from .association_goal import AssociationQueryBuildResult
from .association_session_goal import (
    AssociationContinuationGoal,
    AssociationSessionTurnGoalCompiler,
)

# Public runtime composes independent GoalCompiler/Inference extensions. Open-event
# retrieval, identity/description lookup and quantified ground-atom derivation are
# InferenceEngine extensions. Association execution remains outside InferenceEngine
# and is routed to AssociationCoordinator by the agent orchestrator.
InferenceEngine = QuantifiedExistsInferenceEngine
InferenceMaterializer = QuantifiedInferenceMaterializer
QueryGoalBuilder = EntityIdentityQueryGoalBuilder
AssociationTurnGoalCompiler = AssociationSessionTurnGoalCompiler
SemanticGoalCompiler = AssociationSessionTurnGoalCompiler
TurnGoalBuilder = AssociationSessionTurnGoalCompiler

__all__ = [
    "AttentionFocusEvent",
    "AllOfGoal",
    "AnyOfGoal",
    "AssociationGoal",
    "AssociationContinuationGoal",
    "AssociationQueryBuildResult",
    "AssociationSessionTurnGoalCompiler",
    "AssociationTurnGoalCompiler",
    "CauseEntailmentGoal",
    "CounterfactualGoal",
    "CounterfactualSemanticGoalCompiler",
    "CognitiveEventKind",
    "CognitiveTraceEvent",
    "CompositeConclusion",
    "DerivedAtomConclusion",
    "DerivedLinkConclusion",
    "EventMatchGoal",
    "EventQueryGoalBuilder",
    "EventSetInferenceEngine",
    "EntityIdentityGoal",
    "EntityIdentityInferenceEngine",
    "EntityIdentityQueryGoalBuilder",
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
    "QuantifiedExistsInferenceEngine",
    "QuantifiedInferenceMaterializer",
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
