from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ah.model import ActantRole
from ah.temporal.contracts import TemporalCandidate, TemporalMode, TransitionOperator
from .lexical_recovery import TokenCandidate


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
    """Runtime-only reusable role schema proposed for a predicate.

    This is not canonical T and carries no UID. Perception proposes it only when
    the predicate has no canonical T; deterministic integration validates it before
    registration. In the production path the candidate contains only roles supported
    by explicit semantic evidence. Later validated occurrences may monotonically
    expand the canonical T.
    """

    roles: tuple[ActantRole, ...]

    def __post_init__(self) -> None:
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("TemplateCandidate.roles must be unique")


@dataclass(frozen=True, slots=True)
class TemplateSelection:
    """Runtime-only deterministic T selection for one predicate occurrence.

    The LLM never emits canonical UIDs. A Perception probe may choose a local
    option label (for example ``C1`` or ``NEW``); the orchestrator maps that
    label to a canonical T under the AH lock and stores the result here.
    ``create_new`` deliberately allows a second T with the same predicate S and
    the same role schema when the current lexical sense is distinct.
    """

    existing_template_uid: str | None = None
    create_new: bool = False

    def __post_init__(self) -> None:
        if bool(self.existing_template_uid) == bool(self.create_new):
            raise ValueError(
                "TemplateSelection requires exactly one of existing_template_uid or create_new"
            )


@dataclass(frozen=True, slots=True)
class PredicateCandidate:
    surface: str
    normalized_hint: str | None = None
    sense_hint: str | None = None
    evidence: EvidenceSpan | None = None
    template_candidate: TemplateCandidate | None = None
    template_selection: TemplateSelection | None = None

    @property
    def lookup_form(self) -> str:
        value = (self.normalized_hint or self.surface).strip()
        if not value:
            raise ValueError("PredicateCandidate must contain a non-empty form")
        return value



class PropositionOperator(str, Enum):
    REF = "REF"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    IMPLIES = "IMPLIES"
    FALSE = "FALSE"  # legacy runtime alias; canonical object negation is NOT


@dataclass(frozen=True, slots=True)
class PropositionExprCandidate:
    """Runtime-only proposition expression over local assertion refs.

    This is deliberately not a canonical AH type. Integration maps REF to the
    corresponding scoped N and AND/OR/NOT to the already-canonical g operators.
    """

    operator: PropositionOperator
    ref: str | None = None
    members: tuple["PropositionExprCandidate", ...] = ()

    def __post_init__(self) -> None:
        if self.operator is PropositionOperator.REF:
            if self.ref is None or not self.ref.strip() or self.members:
                raise ValueError("REF proposition requires exactly one non-empty ref")
            return
        if self.ref is not None:
            raise ValueError("non-REF proposition cannot carry ref")
        if self.operator in {PropositionOperator.NOT, PropositionOperator.FALSE}:
            if len(self.members) != 1:
                raise ValueError(f"{self.operator.value} proposition requires exactly one member")
            return
        if self.operator is PropositionOperator.IMPLIES:
            if len(self.members) != 2:
                raise ValueError("IMPLIES proposition requires exactly two members")
            return
        if len(self.members) < 2:
            raise ValueError(f"{self.operator.value} proposition requires at least two members")

    @classmethod
    def ref_expr(cls, ref: str) -> "PropositionExprCandidate":
        return cls(PropositionOperator.REF, ref=ref)

    def leaf_refs(self) -> tuple[str, ...]:
        if self.operator is PropositionOperator.REF:
            assert self.ref is not None
            return (self.ref,)
        out: list[str] = []
        for member in self.members:
            out.extend(member.leaf_refs())
        return tuple(dict.fromkeys(out))


@dataclass(frozen=True, slots=True)
class PropositionRootCandidate:
    """One source-asserted top-level logical formula before canonical Integration.

    expression references parser-local AssertionCandidate ids only. Leaf
    propositions can therefore be canonicalized with zero ordinary occurrence
    count, while the formula root itself receives the H assertion occurrence.
    operator_source_refs records matrix frames consumed purely as linguistic
    logical operators so they are not asserted as independent world facts.
    """

    local_id: str
    expression: PropositionExprCandidate
    evidence: EvidenceSpan | None = None
    operator_source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.local_id.strip():
            raise ValueError("PropositionRootCandidate.local_id must be non-empty")
        if self.expression.operator is PropositionOperator.REF:
            raise ValueError("Top-level logical root cannot be a bare REF")
        if any(not item.strip() for item in self.operator_source_refs):
            raise ValueError("operator_source_refs must contain non-empty local ids")
        if set(self.operator_source_refs) & set(self.expression.leaf_refs()):
            raise ValueError("logical operator source cannot also be a formula leaf")


class NominalRelationKind(str, Enum):
    """Runtime-only relation internal to one nominal phrase.

    These labels are deliberately structural and source-grounded. ``POSSESSOR``
    is used only when morphology explicitly marks possession/anaphoric
    possessive structure; ``GENITIVE_DEP`` preserves a genitive nominal
    dependency without pretending that every Russian genitive means ownership;
    ``NOMINAL_MODIFIER`` keeps an attributive adjective/participle/number attached
    to the nominal head without promoting it to a stronger world relation.
    Integration may materialize these as typed canonical L edges for asserted
    content.
    """

    POSSESSOR = "POSSESSOR"
    GENITIVE_DEP = "GENITIVE_DEP"
    NOMINAL_MODIFIER = "NOMINAL_MODIFIER"


@dataclass(frozen=True, slots=True)
class NominalRelationCandidate:
    kind: NominalRelationKind
    head_mention: str
    head_normalized_hint: str | None
    dependent_mention: str
    dependent_normalized_hint: str | None = None
    dependent_entity_ref: str | None = None
    evidence: EvidenceSpan | None = None

    def __post_init__(self) -> None:
        if not self.head_mention.strip():
            raise ValueError("NominalRelationCandidate.head_mention must be non-empty")
        if not self.dependent_mention.strip():
            raise ValueError("NominalRelationCandidate.dependent_mention must be non-empty")


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
    proposition: PropositionExprCandidate | None = None
    nominal_relations: tuple[NominalRelationCandidate, ...] = ()
    # Runtime grammatical cardinality of the source nominal head.  This is not
    # semantic truth about real-world multiplicity, but it is identity-relevant:
    # a singular ``матрос`` and a plural/group ``матросы`` must not collapse to
    # one canonical M merely because both lemmatize to ``матрос``.
    grammatical_number: str | None = None
    # Runtime-only normalized TIME descriptor. Canonical time remains ordinary m.
    temporal: TemporalCandidate | None = None

    def __post_init__(self) -> None:
        if (
            self.candidate_ref is None
            and self.entity_ref is None
            and self.composition is None
            and self.proposition is None
            and not (self.mention or self.normalized_hint)
        ):
            raise ValueError(
                "ActantCandidate needs mention/normalized_hint, candidate_ref, entity_ref, or composition"
            )
        if self.candidate_ref is not None and self.entity_ref is not None:
            raise ValueError("ActantCandidate cannot have both candidate_ref and entity_ref")
        if self.composition is not None and (self.candidate_ref is not None or self.entity_ref is not None or self.proposition is not None):
            raise ValueError("ActantCandidate composition cannot also use candidate_ref/entity_ref/proposition")
        if self.proposition is not None and (self.candidate_ref is not None or self.entity_ref is not None or self.composition is not None):
            raise ValueError("ActantCandidate proposition cannot also use candidate_ref/entity_ref/composition")
        if self.entity_ref is not None and not self.entity_ref.strip():
            raise ValueError("entity_ref must be non-empty when provided")
        if self.parser_confidence is not None and not 0.0 <= self.parser_confidence <= 1.0:
            raise ValueError("parser_confidence must be in [0, 1]")
        if self.grammatical_number is not None:
            # Morphology adapters are required to expose plain Python strings.
            # Normalize defensively here as well so library-specific grammeme
            # scalar subclasses can never leak into Integration.
            number = str(self.grammatical_number)
            if number not in {"sing", "plur"}:
                raise ValueError("grammatical_number must be sing, plur, or None")
            if type(self.grammatical_number) is not str:
                object.__setattr__(self, "grammatical_number", number)

    @property
    def lookup_text(self) -> str | None:
        value = self.normalized_hint or self.mention
        return value.strip() if value else None


class AssertionStatus(str, Enum):
    ASSERTED = "ASSERTED"
    EMBEDDED = "EMBEDDED"
    CONDITIONAL = "CONDITIONAL"
    HYPOTHETICAL = "HYPOTHETICAL"
    MODAL = "MODAL"


@dataclass(frozen=True, slots=True)
class AssertionCandidate:
    local_id: str
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...]
    evidence: EvidenceSpan | None = None
    alternatives: tuple["AssertionCandidate", ...] = ()
    negated: bool = False
    status: AssertionStatus = AssertionStatus.ASSERTED
    # Occurrence-level temporal interpretation. It is staging metadata, not a
    # global property of T. A predicate may be STATE in one occurrence and EVENT
    # in another.
    temporal_mode: TemporalMode | None = None
    transition_operator: TransitionOperator | None = None
    # Quotation is orthogonal to conditional/embedded proposition status.  A
    # quoted assertion is represented canonically as proposition content but is
    # never eligible for ordinary asserted-fact retrieval merely because it was
    # mentioned inside somebody's speech.
    quoted: bool = False

    def __post_init__(self) -> None:
        if self.transition_operator is not None and self.temporal_mode is not TemporalMode.TRANSITION:
            raise ValueError("transition_operator requires temporal_mode=TRANSITION")


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
    # ``requested_role`` is retained as a compatibility alias for older callers.
    # New perception code writes ``requested_roles`` so one query can represent
    # several WH gaps without being split into unrelated speech acts.
    requested_role: ActantRole | None = None
    requested_roles: tuple[ActantRole, ...] = ()
    query_mode: QueryMode = QueryMode.EXISTS
    local_id: str | None = None
    quoted: bool = False

    def __post_init__(self) -> None:
        roles = self.requested_roles
        if self.requested_role is not None:
            if roles and roles != (self.requested_role,):
                raise ValueError("requested_role conflicts with requested_roles")
            roles = (self.requested_role,)
        if len(set(roles)) != len(roles):
            raise ValueError("QueryCandidate.requested_roles must be unique")
        if self.query_mode is QueryMode.EXISTS and roles:
            raise ValueError("EXISTS query cannot request role fillers")
        if self.query_mode is QueryMode.FILL_ROLE and not roles:
            raise ValueError("FILL_ROLE query requires at least one requested role")
        object.__setattr__(self, "requested_roles", tuple(roles))
        # Preserve the old scalar view only when the query genuinely has one gap.
        object.__setattr__(self, "requested_role", roles[0] if len(roles) == 1 else None)


@dataclass(frozen=True, slots=True)
class CommandCandidate:
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...] = ()
    local_id: str | None = None
    negated: bool = False
    quoted: bool = False


@dataclass(frozen=True, slots=True)
class ActRelationCandidate:
    """Runtime-only typed structural relation inside one semantic act.

    The relation type is a bounded Perception decision; endpoint roles are local
    semantic roles, never canonical UIDs. Deterministic Integration/Inference later
    resolves those roles to canonical refs. This keeps relation typing out of
    lexical marker tables and out of the LLM agent.
    """

    relation_id: str
    act_ref: str
    source_role: ActantRole
    target_role: ActantRole

    def __post_init__(self) -> None:
        if not self.relation_id.strip() or not self.act_ref.strip():
            raise ValueError("ActRelationCandidate relation_id/act_ref must be non-empty")
        if self.source_role is self.target_role:
            raise ValueError("ActRelationCandidate endpoints must use different roles")

    @property
    def canonical_relation_id(self) -> str:
        return self.relation_id.strip().upper()


class ActDependencyKind(str, Enum):
    SUBORDINATE = "SUBORDINATE"
    NONFINITE = "NONFINITE"
    QUOTED = "QUOTED"


@dataclass(frozen=True, slots=True)
class ActDependencyCandidate:
    """Runtime structural dependency between locally parsed speech acts/frames.

    It preserves root/embedded orientation across different act types without
    pretending that the structural edge is already an AH semantic role.
    """

    parent_ref: str
    child_ref: str
    kind: ActDependencyKind

    def __post_init__(self) -> None:
        if not self.parent_ref.strip() or not self.child_ref.strip():
            raise ValueError("ActDependencyCandidate refs must be non-empty")
        if self.parent_ref == self.child_ref:
            raise ValueError("ActDependencyCandidate cannot be self-referential")


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
class DiscourseRelationDecision:
    """UID-free cross-turn semantic relation selected from local option lists.

    ``prior_index`` and ``current_index`` address the caller-provided semantic
    strings only.  They are never canonical UIDs and have no meaning outside one
    bounded perception probe.  Deterministic orchestration maps them back to refs
    and Integration remains the sole canonical write boundary.
    """

    relation_id: str
    prior_index: int
    current_index: int

    def __post_init__(self) -> None:
        relation = self.relation_id.strip().upper()
        if relation not in {"CAUSE", "FOLLOW"}:
            raise ValueError("DiscourseRelationDecision supports only CAUSE/FOLLOW")
        if self.prior_index < 0 or self.current_index < 0:
            raise ValueError("DiscourseRelationDecision indexes must be >= 0")

    @property
    def canonical_relation_id(self) -> str:
        return self.relation_id.strip().upper()




class SituationRelationHintKind(str, Enum):
    CAUSAL_CANDIDATE = "CAUSAL_CANDIDATE"
    TEMPORAL_CANDIDATE = "TEMPORAL_CANDIDATE"
    SIMULTANEOUS_CANDIDATE = "SIMULTANEOUS_CANDIDATE"


@dataclass(frozen=True, slots=True)
class SituationRelationHintCandidate:
    """Runtime-only non-canonical relation hypothesis between situations.

    Hints are deliberately weaker than ``SituationRelationCandidate``. They are
    useful for document diagnostics and later bounded reasoning, but Integration
    must never materialize them as canonical ``L`` merely because two narrated
    events are adjacent. This keeps narrative plausibility separate from asserted
    CAUSE/FOLLOW truth.
    """

    kind: SituationRelationHintKind
    source_ref: str
    target_ref: str
    evidence: EvidenceSpan | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.source_ref.strip() or not self.target_ref.strip():
            raise ValueError("SituationRelationHintCandidate endpoints must be non-empty")
        if self.source_ref == self.target_ref:
            raise ValueError("SituationRelationHintCandidate cannot be self-referential")
        if self.reason is not None and not self.reason.strip():
            raise ValueError("SituationRelationHintCandidate.reason must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class ConditionalCandidate:
    """Runtime-only conditional dependency between two recognized situations.

    The antecedent and consequent are semantic proposition candidates, but they are
    not ordinary asserted world facts. Integration canonicalizes them as scoped N
    operands and binds the two sides with deterministic g_IMPLIES / g_AND composition.
    Ordinary EXISTS/ROLE_FILL therefore cannot treat either branch as already true.
    """

    antecedent_refs: tuple[str, ...]
    consequent_refs: tuple[str, ...]
    evidence: EvidenceSpan | None = None
    antecedent_expr: PropositionExprCandidate | None = None
    consequent_expr: PropositionExprCandidate | None = None

    def __post_init__(self) -> None:
        if not self.antecedent_refs or not self.consequent_refs:
            raise ValueError("ConditionalCandidate requires antecedent and consequent situations")
        if any(not ref.strip() for ref in (*self.antecedent_refs, *self.consequent_refs)):
            raise ValueError("ConditionalCandidate endpoints must be non-empty")
        if set(self.antecedent_refs) & set(self.consequent_refs):
            raise ValueError("ConditionalCandidate branches must not overlap")
        if self.antecedent_expr is not None and set(self.antecedent_expr.leaf_refs()) != set(self.antecedent_refs):
            raise ValueError("Conditional antecedent expression refs mismatch")
        if self.consequent_expr is not None and set(self.consequent_expr.leaf_refs()) != set(self.consequent_refs):
            raise ValueError("Conditional consequent expression refs mismatch")




@dataclass(frozen=True, slots=True)
class StructuralClarificationOption:
    key: str
    label: str

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.label.strip():
            raise ValueError("Structural clarification option key/label must be non-empty")


@dataclass(frozen=True, slots=True)
class StructuralClarificationSpec:
    ambiguity_type: str
    mention: str
    source_text: str
    options: tuple[StructuralClarificationOption, ...]

    def __post_init__(self) -> None:
        if not self.ambiguity_type.strip() or not self.mention.strip() or not self.source_text.strip():
            raise ValueError("Structural clarification spec fields must be non-empty")
        if len(self.options) < 2:
            raise ValueError("Structural clarification requires at least two options")
        keys = [item.key for item in self.options]
        if len(set(keys)) != len(keys):
            raise ValueError("Structural clarification option keys must be unique")

@dataclass(frozen=True, slots=True)
class PerceptionResult:
    source_text: str
    assertions: tuple[AssertionCandidate, ...] = ()
    queries: tuple[QueryCandidate, ...] = ()
    commands: tuple[CommandCandidate, ...] = ()
    diagnostics: tuple[str, ...] = ()
    relations: tuple[SituationRelationCandidate, ...] = ()
    act_relations: tuple[ActRelationCandidate, ...] = ()
    conditionals: tuple[ConditionalCandidate, ...] = ()
    act_dependencies: tuple[ActDependencyCandidate, ...] = ()
    relation_hints: tuple[SituationRelationHintCandidate, ...] = ()
    # Runtime preprocessing diagnostics.  These are source-provenance decisions,
    # never canonical AH elements or authorization to write a fact.
    lexical_recovery: tuple[TokenCandidate, ...] = ()
    # Keep this field last so legacy positional PerceptionResult construction
    # preserves its historical argument layout.
    proposition_roots: tuple[PropositionRootCandidate, ...] = ()

    @property
    def acts_count(self) -> int:
        return len(self.assertions) + len(self.queries) + len(self.commands)
