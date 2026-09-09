from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from enum import Enum

from ah.model import ActantRole, Domain, Ref
if TYPE_CHECKING:
    from ah.perception.contracts import CommandCandidate, PredicateCandidate, QueryCandidate






@dataclass(frozen=True, slots=True)
class TemplateSenseOption:
    """One local, non-UID-facing sense option for a known canonical T.

    ``template_uid`` is consumed only by deterministic orchestration after the
    Perception layer chooses ``label``. The LLM receives label + description,
    never the UID itself.
    """

    label: str
    template_uid: str
    description: str

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("TemplateSenseOption.label must be non-empty")
        if not self.template_uid.strip():
            raise ValueError("TemplateSenseOption.template_uid must be non-empty")
        if not self.description.strip():
            raise ValueError("TemplateSenseOption.description must be non-empty")

@dataclass(frozen=True, slots=True)
class TemplateRequest:
    """Runtime request for explicit T schema and/or lexical-sense resolution.

    With no ``sense_options`` the predicate is unknown and Perception only packages
    the explicit roles already present in the semantic act. With options, each Cn
    label represents one existing canonical T through a UID-free usage profile;
    Perception returns only a local label and deterministic orchestration maps it
    back to the corresponding T or creates a NEW sense.
    """

    predicate: "PredicateCandidate"
    filled_roles: tuple[ActantRole, ...]
    source_context: str
    role_bindings: tuple[tuple[ActantRole, str], ...] = ()
    sense_options: tuple[TemplateSenseOption, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_context.strip():
            raise ValueError("TemplateRequest.source_context must be non-empty")
        for role, value in self.role_bindings:
            if role not in self.filled_roles:
                raise ValueError("TemplateRequest binding role must be in filled_roles")
            if not value.strip():
                raise ValueError("TemplateRequest role binding text must be non-empty")
        labels = tuple(option.label for option in self.sense_options)
        if len(set(labels)) != len(labels):
            raise ValueError("TemplateRequest sense option labels must be unique")

class SeedReason(str, Enum):
    NEW_FACT = "NEW_FACT"
    REACTIVATED_FACT = "REACTIVATED_FACT"
    EXPERIENCE = "EXPERIENCE"
    SENSORY_SYMBOL = "SENSORY_SYMBOL"
    RESOLVED_SYMBOL = "RESOLVED_SYMBOL"
    QUERY_RECALL = "QUERY_RECALL"
    CORRECTION = "CORRECTION"
    PACEMAKER = "PACEMAKER"
    CONFLICT = "CONFLICT"


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
class ClarificationOption:
    """One user-visible runtime option for a canonical ambiguity group."""

    index: int
    ref: Ref
    label: str

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("ClarificationOption.index must be positive")
        if not self.label.strip():
            raise ValueError("ClarificationOption.label must be non-empty")


@dataclass(frozen=True, slots=True)
class ClarificationUse:
    """A fact/role position currently pointing at k_AMBIGUOUS."""

    fact_ref: Ref
    roles: tuple[ActantRole, ...]


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    """Explicit clarification path produced after deterministic ambiguity handling.

    The LLM may verbalize this request, but it never receives authority to replace
    ``ambiguous_ref`` by an option. Canonical selection is performed later by the
    deterministic clarification resolver from the user's explicit answer.
    """

    ambiguous_ref: Ref
    mention: str
    options: tuple[ClarificationOption, ...]
    uses: tuple[ClarificationUse, ...] = ()
    kind: str = "ENTITY_REFERENCE"
    source_text: str | None = None

    def __post_init__(self) -> None:
        if self.ambiguous_ref.kind.value != "K":
            raise ValueError("ClarificationRequest.ambiguous_ref must be K")
        if len(self.options) < 2:
            raise ValueError("ClarificationRequest requires at least two options")
        if tuple(item.index for item in self.options) != tuple(range(1, len(self.options) + 1)):
            raise ValueError("ClarificationRequest option indexes must be contiguous from 1")


@dataclass(frozen=True, slots=True)
class ClarificationResolutionCommit:
    ambiguous_ref: Ref
    selected_ref: Ref
    affected_facts: tuple[Ref, ...]
    activation_seeds: tuple[ActivationSeedRequest, ...] = ()



@dataclass(frozen=True, slots=True)
class IdentityMergeResult:
    survivor: Ref
    removed: Ref
    rewired: tuple[tuple[Ref, Ref], ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.survivor.kind.value != "M" or self.removed.kind.value != "M":
            raise ValueError("IdentityMergeResult endpoints must be M")

@dataclass(frozen=True, slots=True)
class IntegratedAssertion:
    local_id: str
    ref: Ref
    domain: Domain
    created: bool
    ambiguous: bool = False
    semantic_scope: str | None = None
    nominal_relations: tuple["IntegratedRelation", ...] = ()






@dataclass(frozen=True, slots=True)
class IntegratedExistential:
    """One asserted existential formula built from scoped source propositions."""

    ref: Ref
    member_refs: tuple[Ref, ...]
    variable_ids: tuple[int, ...]
    created: bool

    def __post_init__(self) -> None:
        if self.ref.kind.value != "G":
            raise ValueError("IntegratedExistential.ref must be G")
        if not self.member_refs:
            raise ValueError("IntegratedExistential requires at least one member proposition")
        if not self.variable_ids:
            raise ValueError("IntegratedExistential requires at least one variable")


@dataclass(frozen=True, slots=True)
class IntegratedConditional:
    ref: Ref
    antecedent: Ref
    consequent: Ref
    created: bool
    member_refs: tuple[Ref, ...] = ()

@dataclass(frozen=True, slots=True)
class IntegratedRelation:
    relation_id: str
    source: Ref
    target: Ref
    ref: Ref
    created: bool


@dataclass(frozen=True, slots=True)
class IntegratedConflict:
    ref: Ref
    members: tuple[Ref, ...]
    kind: str
    created: bool

    def __post_init__(self) -> None:
        if self.ref.kind.value != "K":
            raise ValueError("IntegratedConflict.ref must be K")
        if len(self.members) < 2:
            raise ValueError("IntegratedConflict requires at least two members")


@dataclass(frozen=True, slots=True)
class IntegrationCommit:
    assertions: tuple[IntegratedAssertion, ...]
    experience_ref: Ref
    activation_seeds: tuple[ActivationSeedRequest, ...]
    refutations: tuple[RefutationRequest, ...] = ()
    unresolved_queries: tuple["QueryCandidate", ...] = ()
    unresolved_commands: tuple["CommandCandidate", ...] = ()
    clarification_required: bool = False
    clarifications: tuple[ClarificationRequest, ...] = ()
    relations: tuple[IntegratedRelation, ...] = ()
    conditionals: tuple[IntegratedConditional, ...] = ()
    existentials: tuple[IntegratedExistential, ...] = ()
    universals: tuple[IntegratedExistential, ...] = ()
    conflicts: tuple[IntegratedConflict, ...] = ()
