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
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class RoleFillGoal:
    template_ref: Ref
    known_roles: Mapping[ActantRole, Ref]
    requested_role: ActantRole


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


InferenceGoal = RoleFillGoal | ExistsGoal | RelationGoal | CauseEntailmentGoal


@dataclass(frozen=True, slots=True)
class ExistingRefConclusion:
    ref: Ref


@dataclass(frozen=True, slots=True)
class RoleBindingConclusion:
    role: ActantRole
    value: Ref
    fact: Ref


@dataclass(frozen=True, slots=True)
class DerivedLinkConclusion:
    relation_id: str
    source: Ref
    target: Ref


SemanticConclusion = ExistingRefConclusion | RoleBindingConclusion | DerivedLinkConclusion


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
