from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from ah.model import ActantRole, Domain, Ref


class LogicalStatus(str, Enum):
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    UNKNOWN = "UNKNOWN"


class StopReason(str, Enum):
    GOAL_SATISFIED = "GOAL_SATISFIED"
    SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"
    DEPTH_EXHAUSTED = "DEPTH_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


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


InferenceGoal = RoleFillGoal | MultiRoleFillGoal | ExistsGoal | RelationGoal | CauseEntailmentGoal | AllOfGoal


@dataclass(frozen=True, slots=True)
class GoalSpec:
    """Explicit runtime inference target.

    The goal exists before search starts and is the semantic stop condition. Search
    is therefore not an instruction to walk a graph until an endpoint: every rule
    application is evaluated against this target and successful proof stops at the
    first goal-satisfying derivation.
    """

    target: InferenceGoal


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
