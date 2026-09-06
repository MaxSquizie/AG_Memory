from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from ah.inference.bindings import BindingEnvironment
from ah.inference.context import ProofContext

from ah.model import ActantRole, Domain, Ref


class LogicalStatus(str, Enum):
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    UNKNOWN = "UNKNOWN"


class GoalMode(str, Enum):
    FACTUAL = "FACTUAL"
    PROOF = "PROOF"
    ASSOCIATION = "ASSOCIATION"
    EVIDENCE = "EVIDENCE"


class CognitiveEventKind(str, Enum):
    GOAL_START = "GOAL_START"
    FOCUS = "FOCUS"
    MEMORY_QUERY = "MEMORY_QUERY"
    SUBGOAL = "SUBGOAL"
    RULE_SELECTED = "RULE_SELECTED"
    GOAL_STOP = "GOAL_STOP"


@dataclass(frozen=True, slots=True)
class CognitiveTraceEvent:
    """One runtime cognition event produced while solving a GoalSpec.

    This is diagnostic runtime state only: it is not canonical AH and never
    becomes a proof premise merely because it appears in the trace.
    """

    kind: CognitiveEventKind
    logical_depth: int = 0
    ref: Ref | None = None
    query_kind: str | None = None
    query_key: str | None = None
    candidate_count: int | None = None
    rule_id: str | None = None
    detail: str = ""
    workspace_refs: tuple[Ref, ...] = ()


class StopReason(str, Enum):
    GOAL_SATISFIED = "GOAL_SATISFIED"
    GOAL_REFUTED = "GOAL_REFUTED"
    CONFLICTED = "CONFLICTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"
    DEPTH_EXHAUSTED = "DEPTH_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


@dataclass(frozen=True, slots=True)
class RoleFillGoal:
    template_ref: Ref
    known_roles: Mapping[ActantRole, Ref]
    requested_role: ActantRole


@dataclass(frozen=True, slots=True)
class MultiRoleFillGoal:
    template_ref: Ref
    known_roles: Mapping[ActantRole, Ref]
    requested_roles: tuple[ActantRole, ...]

    def __post_init__(self) -> None:
        if len(self.requested_roles) < 2:
            raise ValueError("MultiRoleFillGoal requires at least two requested roles")
        if len(set(self.requested_roles)) != len(self.requested_roles):
            raise ValueError("MultiRoleFillGoal.requested_roles must be unique")


@dataclass(frozen=True, slots=True)
class ExistsGoal:
    template_ref: Ref
    known_roles: Mapping[ActantRole, Ref]


@dataclass(frozen=True, slots=True)
class RelationGoal:
    relation_id: str
    source: Ref
    target: Ref


@dataclass(frozen=True, slots=True)
class CauseEntailmentGoal:
    effect: Ref




@dataclass(frozen=True, slots=True)
class FormulaGoal:
    """Prove/refute one canonical ground proposition/formula root (N or g)."""

    expression: Ref

    def __post_init__(self) -> None:
        if self.expression.kind.value not in {"N", "G"}:
            raise ValueError("FormulaGoal.expression must reference N or G")



@dataclass(frozen=True, slots=True)
class AssociationGoal:
    """Find a runtime associative convergence between two excitable AH refs.

    This is a GoalSpec target but deliberately not an InferenceGoal: the result is
    representation intersection, not entailment. Execution belongs to
    AssociationCoordinator rather than InferenceEngine.
    """

    left: Ref
    right: Ref

    def __post_init__(self) -> None:
        for name, ref in (("left", self.left), ("right", self.right)):
            if ref.kind.value == "L":
                raise ValueError(
                    f"AssociationGoal.{name} cannot be L because L has no excitation state"
                )


@dataclass(frozen=True, slots=True)
class CounterfactualGoal:
    """Evaluate one formula under explicit temporary assumptions.

    Assumptions are canonical N/g proposition references used only by a runtime
    CounterfactualContext. They never mutate, duplicate or replace canonical AH.
    """

    assumptions: tuple[Ref, ...]
    target: FormulaGoal

    def __post_init__(self) -> None:
        if not self.assumptions:
            raise ValueError("CounterfactualGoal requires at least one assumption")
        for ref in self.assumptions:
            if ref.kind.value not in {"N", "G"}:
                raise ValueError("Counterfactual assumptions must reference N or G")

@dataclass(frozen=True, slots=True)
class AllOfGoal:
    """Conjunctive proof target for typed rule composition.

    Every child goal keeps its own inference semantics. The conjunction is proved
    only when all children are proved. This allows one proof to compose CAUSE,
    FOLLOW, IS-A and future rule families without treating an arbitrary mixed graph
    path as a valid inference rule. Child order is the intended dependency/audit
    order and is preserved in the proof trace.
    """

    goals: tuple["InferenceGoal", ...]

    def __post_init__(self) -> None:
        if len(self.goals) < 2:
            raise ValueError("AllOfGoal requires at least two child goals")


InferenceGoal = RoleFillGoal | MultiRoleFillGoal | ExistsGoal | RelationGoal | CauseEntailmentGoal | FormulaGoal | CounterfactualGoal | AllOfGoal
GoalTarget = InferenceGoal | AssociationGoal


@dataclass(frozen=True, slots=True)
class GoalSpec:
    """Explicit runtime inference target and query mode.

    The goal exists before search starts, controls admissible narrow memory
    queries and is the semantic stop condition. ``request_all_proofs`` is false by
    default: ordinary cognition stops at the first valid proof instead of walking
    the graph "just in case".
    """

    target: GoalTarget
    mode: GoalMode = GoalMode.PROOF
    request_all_proofs: bool = False


@dataclass(frozen=True, slots=True)
class InferenceQuery:
    """Goal-directed bounded inference request.

    ``premise_refs`` are explicit starting propositions for rule systems that need
    them (notably multi-step CAUSE/MP). For backwards compatibility, callers may
    still pass a bare InferenceGoal to InferenceEngine.solve(); the engine wraps it
    in GoalSpec with no explicit premises.
    """

    goal: GoalSpec
    premise_refs: tuple[Ref, ...] = ()
    max_depth: int | None = None
    max_expanded_states: int | None = None
    proof_context: ProofContext | None = None

    def __post_init__(self) -> None:
        if self.max_depth is not None and self.max_depth < 1:
            raise ValueError("InferenceQuery.max_depth must be >= 1")
        if self.max_expanded_states is not None and self.max_expanded_states < 1:
            raise ValueError("InferenceQuery.max_expanded_states must be >= 1")


@dataclass(frozen=True, slots=True)
class ExistingRefConclusion:
    ref: Ref


@dataclass(frozen=True, slots=True)
class RoleBindingConclusion:
    role: ActantRole
    value: Ref
    fact: Ref


@dataclass(frozen=True, slots=True)
class MultiRoleBindingConclusion:
    bindings: tuple[tuple[ActantRole, Ref], ...]
    fact: Ref

    def __post_init__(self) -> None:
        if len(self.bindings) < 2:
            raise ValueError("MultiRoleBindingConclusion requires at least two bindings")
        roles = tuple(role for role, _ in self.bindings)
        if len(set(roles)) != len(roles):
            raise ValueError("MultiRoleBindingConclusion roles must be unique")


@dataclass(frozen=True, slots=True)
class DerivedLinkConclusion:
    relation_id: str
    source: Ref
    target: Ref


SemanticConclusion = ExistingRefConclusion | RoleBindingConclusion | MultiRoleBindingConclusion | DerivedLinkConclusion


@dataclass(frozen=True, slots=True)
class CompositeConclusion:
    conclusions: tuple["SemanticConclusion", ...]

    def __post_init__(self) -> None:
        if len(self.conclusions) < 2:
            raise ValueError("CompositeConclusion requires at least two conclusions")


SemanticConclusion = SemanticConclusion | CompositeConclusion


@dataclass(frozen=True, slots=True)
class ProofSupport:
    """Runtime dependency record for a derived conclusion.

    Does not represent truth strength. It records which runtime proof context
    produced a derived result and is used later for lifecycle handling.
    """

    premise_refs: tuple[Ref, ...]
    rule_id: str | None = None
    relation_id: str | None = None


@dataclass(frozen=True, slots=True)
class InferenceOutcome:
    status: LogicalStatus
    stop_reason: StopReason
    conclusion: SemanticConclusion | None
    premise_refs: tuple[Ref, ...]
    uid_trace: tuple[Ref, ...]
    conclusion_domain: Domain | None
    expanded_states: int
    diagnostics: tuple[str, ...] = ()
    goal_spec: GoalSpec | None = None
    logical_depth: int = 0
    proof_support: tuple[ProofSupport, ...] = ()
    bindings: BindingEnvironment | None = None
    proof_context: ProofContext | None = None
    cognitive_trace: tuple[CognitiveTraceEvent, ...] = ()
