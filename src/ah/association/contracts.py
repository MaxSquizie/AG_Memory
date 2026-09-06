from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ah.inference.contracts import AssociationGoal
from ah.model import Ref


class AssociationStatus(str, Enum):
    """Termination state for associative search.

    These statuses deliberately do not reuse LogicalStatus: an association is a
    convergence of activated representations, not a logical proof.
    """

    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    DEPTH_EXHAUSTED = "DEPTH_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class AssociationDomainPolicy(str, Enum):
    """Runtime policy for the still-open H-domain architecture decision.

    ``ALL`` allows H to participate like C/P. ``EXCLUDE_H`` keeps episodic H out
    of the search. The choice is runtime-only and never changes canonical AH.
    """

    ALL = "ALL"
    EXCLUDE_H = "EXCLUDE_H"


@dataclass(frozen=True, slots=True)
class AssociationBudget:
    max_depth: int = 6
    max_expanded_states: int = 5000
    max_ticks: int = 24

    def __post_init__(self) -> None:
        if self.max_depth < 1:
            raise ValueError("AssociationBudget.max_depth must be >= 1")
        if self.max_expanded_states < 2:
            raise ValueError("AssociationBudget.max_expanded_states must be >= 2")
        if self.max_ticks < 1:
            raise ValueError("AssociationBudget.max_ticks must be >= 1")


class AssociationHopKind(str, Enum):
    PROPAGATION = "PROPAGATION"
    MEMORY_QUERY = "MEMORY_QUERY"


@dataclass(frozen=True, slots=True)
class AssociationHop:
    """One provenance edge of one associative expansion front.

    ``via_uid`` is the canonical L/N/T/g/k UID that explains the transition when
    there is one. For a goal-generated reverse/index query it remains diagnostic
    provenance; it never becomes a proof rule or canonical relation.
    """

    source: Ref
    target: Ref
    kind: AssociationHopKind
    relation: str
    tick: int
    via_uid: str | None = None


@dataclass(frozen=True, slots=True)
class AssociationPath:
    origin: Ref
    common: Ref
    refs: tuple[Ref, ...]
    hops: tuple[AssociationHop, ...]

    @property
    def depth(self) -> int:
        return len(self.hops)


class AssociationTraceKind(str, Enum):
    GOAL_START = "GOAL_START"
    SEED = "SEED"
    ACTIVATION = "ACTIVATION"
    MEMORY_QUERY = "MEMORY_QUERY"
    CONVERGENCE = "CONVERGENCE"
    GOAL_STOP = "GOAL_STOP"


@dataclass(frozen=True, slots=True)
class AssociationTraceEvent:
    kind: AssociationTraceKind
    tick: int
    front: str | None = None
    ref: Ref | None = None
    source: Ref | None = None
    query_kind: str | None = None
    candidate_count: int | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class AssociationOutcome:
    status: AssociationStatus
    goal: AssociationGoal
    common_ref: Ref | None
    left_path: AssociationPath | None
    right_path: AssociationPath | None
    common_candidates: tuple[Ref, ...]
    left_activated: tuple[Ref, ...]
    right_activated: tuple[Ref, ...]
    expanded_states: int
    ticks_executed: int
    trace: tuple[AssociationTraceEvent, ...]
    domain_policy: AssociationDomainPolicy

    @property
    def found(self) -> bool:
        return self.status is AssociationStatus.FOUND and self.common_ref is not None
