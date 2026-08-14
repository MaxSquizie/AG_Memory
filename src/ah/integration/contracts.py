from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from enum import Enum

from ah.model import Domain, Ref
if TYPE_CHECKING:
    from ah.perception.contracts import CommandCandidate, QueryCandidate


class SeedReason(str, Enum):
    NEW_FACT = "NEW_FACT"
    REACTIVATED_FACT = "REACTIVATED_FACT"
    EXPERIENCE = "EXPERIENCE"
    SENSORY_SYMBOL = "SENSORY_SYMBOL"
    CORRECTION = "CORRECTION"
    PACEMAKER = "PACEMAKER"


@dataclass(frozen=True, slots=True)
class ActivationSeedRequest:
    ref: Ref
    reason: SeedReason


@dataclass(frozen=True, slots=True)
class RefutationRequest:
    target: Ref

    def __post_init__(self) -> None:
        if self.target.kind.value != "N":
            raise ValueError("RefutationRequest.target must be N")


@dataclass(frozen=True, slots=True)
class IntegratedAssertion:
    local_id: str
    ref: Ref
    domain: Domain
    created: bool
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class IntegrationCommit:
    assertions: tuple[IntegratedAssertion, ...]
    experience_ref: Ref
    activation_seeds: tuple[ActivationSeedRequest, ...]
    refutations: tuple[RefutationRequest, ...] = ()
    unresolved_queries: tuple["QueryCandidate", ...] = ()
    unresolved_commands: tuple["CommandCandidate", ...] = ()
    clarification_required: bool = False
