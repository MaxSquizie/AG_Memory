# -*- coding: utf-8 -*-
"""FormalizationState and decision model (Phase 1, V4 freeze rev2-8).

Two INDEPENDENT state systems (§1.1) — never mixed:
- lifecycle:   OPEN -> PROVISIONAL -> COMMITTED   (degree of fixation; Phase 1 stops at PROVISIONAL)
- outcome:     RESOLVED | AMBIGUOUS | INSUFFICIENT_CONTEXT | NO_CANDIDATE | UNRESOLVED

RESOLVED != COMMITTED: T4 grants the semantic outcome; COMMITTED appears only after T5.

Ground types (closed set): R / C / D / M / A.
- M is a MODEL JUDGMENT with recorded inputs and output (the bounded-selection trace,
  stored on the Decision as last_prompt + raw_response — replayable). For ONE_SELECTED
  it is bound to that value; a MULTIPLE_ADMISSIBLE trace is slot-level and grounds no
  individual value. What M is NOT: (a) a NEW independent ground for revision — repeating
  an identical M adds no evidentiality and never re-arms the oscillation detector (§6.3);
  (b) a disguise for D — model guesses must be labeled M, not renamed into algorithmic
  inferences.

rev8: a positive ground for a VALUE is value-specific (Ground.value == that value).
Slot-level grounds (value=None) are declared inputs or traces; they license the slot
but do not ground any individual candidate on their own.

V5 rev16: W joins the closed set — world-knowledge / memory-channel evidence (§15.5,
§17.4): a mention from the journal window grounds an antecedent candidate with its
channel provenance; it is EVIDENCE, never a structural generator (I28).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

LIFECYCLE = ("OPEN", "PROVISIONAL", "COMMITTED")
OUTCOMES = ("RESOLVED", "AMBIGUOUS", "INSUFFICIENT_CONTEXT", "NO_CANDIDATE", "UNRESOLVED")
GROUND_TYPES = ("R", "C", "D", "M", "A", "W")


@dataclass(frozen=True)
class ResourceProvenance:
    """Rev16/H6: the traceability half of every candidate and decision.

    ``pattern_ids`` — declared structural/selection patterns that fired (B1, E1, L1,
    OP1-OP5, bounded_selection, coref_policy_v1); ``resource_versions`` — versions of
    the versioned resources consulted (dictionary, grammar, schema, policies). The
    chain Raw token -> SRL candidate -> CandidateIR -> Decision -> Canonical Memory is
    reconstructable from these fields alone (§18.2)."""

    pattern_ids: tuple[str, ...] = ()
    resource_versions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Ground:
    type: str  # R | C | D | M | A
    text: str
    value: str | None = None  # candidate this ground specifically supports; None = slot-level

    def __post_init__(self):
        if self.type not in GROUND_TYPES:
            raise ValueError(f"unknown ground type: {self.type!r}")


def real_ground_signature(grounds) -> tuple:
    """Content-based signature of REAL grounds (R/C/D/A).

    Compares the CONTENT of grounds ((type, text, value)), not their type letters —
    two R grounds with different texts are different information. M answers are
    traces and count as none (§6.3 rev8)."""
    return tuple(sorted((g.type, g.text, g.value) for g in grounds if g.type != "M"))


@dataclass(frozen=True)
class MorphVariant:
    """ONE whole dictionary parse of a token (R1 output contract, §T1 rev7/rev8).

    Linked features (lemma, POS, case set, number, gender, person, tense, mood and the
    remaining tagset/dictionary features such as SUBX) stay together inside the variant;
    they are never recombined across parses. ``cases`` is this parse's own case set —
    a shared-form parse may legitimately carry both abl and ins."""

    lemma: str | None
    pos: str | None  # OpenCorpora POS code or None for OOV
    cases: frozenset[str] = frozenset()  # normalized codes (nom/gen/dat/acc/abl/ins/loc/voc)
    number: str | None = None  # sing | plur
    gender: str | None = None  # masc | femn | neut
    person: str | None = None  # 1st | 2nd | 3rd
    tense: str | None = None  # past | present | future
    mood: str | None = None  # indicative | imperative
    features: frozenset[str] = frozenset()  # remaining tagset/dictionary codes (e.g. SUBX, ASPT)
    score: float = 1.0


@dataclass
class TokenEvidence:
    """Evidence carries WHOLE morphological variants, not a flattened verdict.

    ``variants`` preserves each dictionary parse intact (linked features stay linked);
    ``cases`` is a DERIVED INDEX — the strict union of the variants' own case sets.
    Nothing may appear in the index without variant support; declared corrections
    (e.g. the -ами/-ями shared-form rule) are applied to the VARIANT's case set, so
    the index stays a pure derivation. Unresolved case ambiguity stays a decision."""

    span: str
    lemma: str | None = None  # top variant (convenience mirror)
    pos: str | None = None  # top variant POS
    cases: frozenset[str] = frozenset()  # INDEX only: strict union over variants
    variants: tuple[MorphVariant, ...] = ()  # whole parses; the authoritative record
    score: float = 1.0  # top variant score
    lex_status: str = "OK"  # OK | OOV_KEEP_AS_IS (first-class candidate, D-provenance)

    def is_oov(self) -> bool:
        return self.lex_status == "OOV_KEEP_AS_IS"


@dataclass
class FrameCandidate:
    """T2 output. I30 [Rev16]: the structural set is CLOSED after TD+T2 — T3/T4 may
    only DECIDE over existing frames, never create new ones (missing structure ->
    NOT_COVERED diagnostic, not silent generation)."""

    frame_id: str
    kind: str  # FLAT | NESTED | COORD
    anchor_span: str
    participants: tuple[str, ...]  # mention spans in surface order (prepositions/copula excluded)
    arguments: tuple[str, ...] = ()  # argument mentions (verbal frame: minus the predicate itself)
    construction: str = ""  # e.g. "u+GEN+NOM", "NOM+V+ACC"
    copula_ellipsis: bool = False
    rank: int = 0
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)  # Rev16/H6


@dataclass(frozen=True)
class ConstraintEdge:
    """Declared inter-decision constraint (cluster validity, §T4 rev8): the pair of
    values (slot_a's value, slot_b's value) is forbidden. Phase 1 ships none; the
    mechanism is present and tested."""

    slot_a: str  # decision key
    slot_b: str  # decision key
    forbidden: frozenset  # of (value_a, value_b) pairs


# --------------------------------------------------------------------------- SRL (V5 §17)
# Structural Reconstruction Layer objects. Registry fields per V5 rev16 §2.1.
# SRL proposes structural HYPOTHESES with pattern provenance; it creates no
# ReferenceCandidate, no identity links, no memory facts, no final ClauseUnit/Frame
# decisions (I24/I26). Downstream confirms or rejects via the decision mechanism.


@dataclass
class TokenHypothesis:
    """Orthographic-level variants for one token. keep_as_is is a FIRST-CLASS variant;
    dictionary distance may rank later but never proves a correction (V5 §17.3/§17.5)."""

    hypothesis_id: str
    span_ref: str  # the raw token this hypothesis is about
    variants: tuple[str, ...]  # includes "keep_as_is" as first-class member
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


@dataclass
class BoundaryCandidate:
    candidate_id: str
    position: int  # token index the proposed boundary opens before
    kind: str = "CLAUSE_BOUNDARY"  # CLAUSE_BOUNDARY | SENTENCE_BOUNDARY | PUNCT_RESTORED
    evidence: list[str] = field(default_factory=list)
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


@dataclass
class ClauseCandidate:
    """One alternative segmentation of the unit into clause groups (token-index ranges).
    Survivors stay linked alternatives until an explicit discard (I29) — never deleted."""

    candidate_id: str
    segmentation: tuple[tuple[int, int], ...]  # inclusive [start, end] token-index pairs
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


@dataclass
class EllipsisCandidate:
    """A structural gap. SRL proposes gaps only; MissingArgumentCandidate (valency) is a
    separate T2/T3 object [Rev16/H3]."""

    candidate_id: str
    gap_ref: str  # span the gap hangs off
    kind: str = "PREDICATE_GAP"  # PREDICATE_GAP | ARGUMENT_GAP | SUBORDINATOR_GAP
    antecedent_ref: str | None = None  # structural antecedent (previous predicate), if any
    evidence: list[str] = field(default_factory=list)
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


@dataclass
class MissingArgumentCandidate:
    """Created by T2/T3 AFTER the valency check (V5 §17.3 [Rev16/H3]) — never by SRL."""

    candidate_id: str
    frame_ref: str
    role: str = "ARGUMENT"
    status: str = "UNRESOLVED"  # UNRESOLVED | RESOLVED_BY_ELLIPSIS | UNFILLED
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


@dataclass
class ReferenceCandidate:
    """TD object [Rev16/H2] — NOT an SRL product. Holds the candidate SET for one
    anaphoric mention plus per-candidate evidence (category, detail). The pair
    'mention = antecedent' exists ONLY inside a RESOLVED reference decision; no
    identity link is created here or anywhere before consolidation (I24)."""

    mention_id: str  # the anaphoric span ('он')
    candidates: tuple[str, ...]  # admissible antecedent spans (observation + memory window)
    evidence: list[tuple[str, str]] = field(default_factory=list)  # (category, detail), per candidate
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


@dataclass
class LinkedAlternative:
    """I29 [Rev15]: a surviving structural alternative, addressable until explicit
    discard. Carries its own provenance — silent deletion is an audit violation."""

    alt_id: str
    kind: str  # CLAUSE_SEGMENTATION | ELLIPSIS | REFERENCE ...
    description: str
    source_candidate_id: str
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


@dataclass
class Decision:
    slot_id: str
    frame_id: str
    candidates: tuple[str, ...]  # admissible closed set for THIS decision (schema rule, rev8)
    selected: tuple[str, ...] = ()  # selector pick; PROVISIONAL until T4 joint validation
    selector_outcome: str | None = None  # protocol outcome (NONE_FIT vs INSUFFICIENT_CONTEXT both select nothing)
    lifecycle: str = "OPEN"  # OPEN -> PROVISIONAL -> COMMITTED (T5 grants COMMITTED)
    outcome: str | None = None  # semantic outcome; granted by T4 only
    grounds: list[Ground] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    last_prompt: str | None = None  # rev8: recorded I/O of the bounded selection (replayable)
    raw_response: str | None = None  # rev8: the verified raw response, verbatim
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)  # Rev16/H6


@dataclass(frozen=True)
class Diagnostic:
    code: str  # PROTOCOL_ERROR | PROVIDER_UNAVAILABLE | SEARCH_INCOMPLETE | BUDGET_EXHAUSTED | OSCILLATION_FROZEN | OOV_KEEP_AS_IS | STRUCTURE_NOT_COVERED | NO_GROUNDED_CANDIDATE | CLUSTER_CONFLICT
    detail: str


@dataclass
class Budget:
    llm_limit: int = 8
    search_step_limit: int = 200
    llm_calls: int = 0
    llm_failed: int = 0
    search_steps: int = 0

    def spend_llm(self, failed: bool = False) -> None:
        self.llm_calls += 1
        if failed:
            self.llm_failed += 1

    @property
    def llm_exhausted(self) -> bool:
        return self.llm_calls >= self.llm_limit


@dataclass
class FormalizationState:
    source_uid: str
    context_version: int
    text: str
    evidence: list[TokenEvidence] = field(default_factory=list)
    # SRL structural hypotheses (V5 §17) — proposals only, never facts (I26):
    token_hypotheses: list[TokenHypothesis] = field(default_factory=list)
    boundary_candidates: list[BoundaryCandidate] = field(default_factory=list)
    clause_candidates: list[ClauseCandidate] = field(default_factory=list)
    ellipsis_candidates: list[EllipsisCandidate] = field(default_factory=list)
    missing_argument_candidates: list[MissingArgumentCandidate] = field(default_factory=list)  # T2/T3 [H3]
    reference_candidates: list[ReferenceCandidate] = field(default_factory=list)  # TD [H2]
    linked_alternatives: list[LinkedAlternative] = field(default_factory=list)  # I29
    memory_mentions: tuple[str, ...] = ()  # journal window input (V5 §17.4/H5): declared, versioned
    structural_closed: bool = False  # I30 [Rev16]: set after TD+T2; T3/T4 must not add structure
    frames: list[FrameCandidate] = field(default_factory=list)
    decisions: dict[str, Decision] = field(default_factory=dict)  # key f"{frame_id}|{slot}"
    diagnostics: list[Diagnostic] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)
    context_facts: tuple[str, ...] = ()  # declared contextual statements (C grounds); baseline passes none
    constraints: list[ConstraintEdge] = field(default_factory=list)  # declared cluster edges (§T4 rev8)
    miss_reports: list[str] = field(default_factory=list)

    @classmethod
    def new(cls, text: str, context_facts: tuple[str, ...] = ()) -> "FormalizationState":
        uid = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        return cls(source_uid=uid, context_version=1, text=text, context_facts=context_facts)

    def diag(self, code: str, detail: str) -> None:
        self.diagnostics.append(Diagnostic(code=code, detail=detail))

    def has_diag(self, code: str) -> bool:
        return any(d.code == code for d in self.diagnostics)

    def close_structures(self) -> None:
        """I30 [Rev16]: called after TD+T2. From this point T3/T4 may only DECIDE over
        existing structural objects; creating new ones is a contract violation."""
        self.structural_closed = True

    def require_structures_open(self, stage: str) -> None:
        if self.structural_closed:
            raise RuntimeError(f"I30 violated: {stage} created structure after closure")
