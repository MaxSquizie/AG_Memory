from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ah.model import ActantRole


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    text: str
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if (self.start is None) != (self.end is None):
            raise ValueError("EvidenceSpan.start/end must be both set or both None")
        if self.start is not None and (self.start < 0 or self.end < self.start):
            raise ValueError("Invalid evidence span")


@dataclass(frozen=True, slots=True)
class TemplateCandidate:
    """Runtime-only role schema proposed for one predicate use.

    This is not canonical T and carries no UID.  Perception may propose it;
    deterministic integration validates it before a new Template is created.
    Concrete N filling is checked against this schema but does not define it.
    """

    roles: tuple[ActantRole, ...]

    def __post_init__(self) -> None:
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("TemplateCandidate.roles must be unique")


@dataclass(frozen=True, slots=True)
class PredicateCandidate:
    surface: str
    normalized_hint: str | None = None
    sense_hint: str | None = None
    evidence: EvidenceSpan | None = None
    template_candidate: TemplateCandidate | None = None

    @property
    def lookup_form(self) -> str:
        value = (self.normalized_hint or self.surface).strip()
        if not value:
            raise ValueError("PredicateCandidate must contain a non-empty form")
        return value


@dataclass(frozen=True, slots=True)
class ActantCandidate:
    role: ActantRole
    mention: str | None = None
    normalized_hint: str | None = None
    semantic_hint: str | None = None
    candidate_ref: str | None = None
    entity_ref: str | None = None
    evidence: EvidenceSpan | None = None
    parser_confidence: float | None = None
    composition: ActantCompositionCandidate | None = None

    def __post_init__(self) -> None:
        if (
            self.candidate_ref is None
            and self.entity_ref is None
            and self.composition is None
            and not (self.mention or self.normalized_hint)
        ):
            raise ValueError(
                "ActantCandidate needs mention/normalized_hint, candidate_ref, entity_ref, or composition"
            )
        if self.candidate_ref is not None and self.entity_ref is not None:
            raise ValueError("ActantCandidate cannot have both candidate_ref and entity_ref")
        if self.composition is not None and (self.candidate_ref is not None or self.entity_ref is not None):
            raise ValueError("ActantCandidate composition cannot also use candidate_ref/entity_ref")
        if self.entity_ref is not None and not self.entity_ref.strip():
            raise ValueError("entity_ref must be non-empty when provided")
        if self.parser_confidence is not None and not 0.0 <= self.parser_confidence <= 1.0:
            raise ValueError("parser_confidence must be in [0, 1]")

    @property
    def lookup_text(self) -> str | None:
        value = self.normalized_hint or self.mention
        return value.strip() if value else None


class AssertionStatus(str, Enum):
    ASSERTED = "ASSERTED"
    CONDITIONAL = "CONDITIONAL"


@dataclass(frozen=True, slots=True)
class AssertionCandidate:
    local_id: str
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...]
    evidence: EvidenceSpan | None = None
    alternatives: tuple["AssertionCandidate", ...] = ()
    negated: bool = False
    status: AssertionStatus = AssertionStatus.ASSERTED


class CompositionOperator(str, Enum):
    AND = "AND"
    OR = "OR"


@dataclass(frozen=True, slots=True)
class CompositionMemberCandidate:
    mention: str
    normalized_hint: str | None = None
    semantic_hint: str | None = None
    evidence: EvidenceSpan | None = None

    @property
    def lookup_text(self) -> str:
        value = (self.normalized_hint or self.mention).strip()
        if not value:
            raise ValueError("Composition member must be non-empty")
        return value


@dataclass(frozen=True, slots=True)
class ActantCompositionCandidate:
    operator: CompositionOperator
    members: tuple[CompositionMemberCandidate, ...]

    def __post_init__(self) -> None:
        if len(self.members) < 2:
            raise ValueError("Actant composition requires at least two members")


class QueryMode(str, Enum):
    FILL_ROLE = "FILL_ROLE"
    EXISTS = "EXISTS"


@dataclass(frozen=True, slots=True)
class QueryCandidate:
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...] = ()
    requested_role: ActantRole | None = None
    query_mode: QueryMode = QueryMode.EXISTS


@dataclass(frozen=True, slots=True)
class CommandCandidate:
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...] = ()




@dataclass(frozen=True, slots=True)
class SituationRelationCandidate:
    """Runtime relation between two locally recognized situations.

    `source_ref` and `target_ref` refer to AssertionCandidate.local_id values.
    This keeps directional semantics such as BEFORE/AFTER out of entity actants.
    The canonical integration layer materializes supported relation IDs as L.
    """

    relation_id: str
    source_ref: str
    target_ref: str
    evidence: EvidenceSpan | None = None

    def __post_init__(self) -> None:
        if not self.relation_id.strip():
            raise ValueError("SituationRelationCandidate.relation_id must be non-empty")
        if not self.source_ref.strip() or not self.target_ref.strip():
            raise ValueError("SituationRelationCandidate endpoints must be non-empty")
        if self.source_ref == self.target_ref:
            raise ValueError("SituationRelationCandidate cannot be self-referential")

    @property
    def canonical_relation_id(self) -> str:
        return self.relation_id.strip().upper()




@dataclass(frozen=True, slots=True)
class ConditionalCandidate:
    """Runtime-only conditional dependency between two recognized situations.

    The antecedent and consequent remain semantic candidates for diagnostics and
    composition, but they are not ordinary asserted world facts. Integration uses
    their AssertionStatus to avoid committing either branch to C/P/H as a fact.
    """

    antecedent_refs: tuple[str, ...]
    consequent_refs: tuple[str, ...]
    evidence: EvidenceSpan | None = None

    def __post_init__(self) -> None:
        if not self.antecedent_refs or not self.consequent_refs:
            raise ValueError("ConditionalCandidate requires antecedent and consequent situations")
        if any(not ref.strip() for ref in (*self.antecedent_refs, *self.consequent_refs)):
            raise ValueError("ConditionalCandidate endpoints must be non-empty")
        if set(self.antecedent_refs) & set(self.consequent_refs):
            raise ValueError("ConditionalCandidate branches must not overlap")


@dataclass(frozen=True, slots=True)
class PerceptionResult:
    source_text: str
    assertions: tuple[AssertionCandidate, ...] = ()
    queries: tuple[QueryCandidate, ...] = ()
    commands: tuple[CommandCandidate, ...] = ()
    diagnostics: tuple[str, ...] = ()
    relations: tuple[SituationRelationCandidate, ...] = ()
    conditionals: tuple[ConditionalCandidate, ...] = ()

    @property
    def acts_count(self) -> int:
        return len(self.assertions) + len(self.queries) + len(self.commands)
