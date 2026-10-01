# -*- coding: utf-8 -*-
"""CandidateIR and the V5 §16/§15 semantic objects (Rev18).

These are the declared contracts of V5 rev14.1/rev13, now implemented as code so
the audit can prove expressiveness instead of assuming it:

- ArgumentSpec {slot_ref, arg_type, value} — argument types are a CLOSED set (§16.2);
  an unknown type is a contract violation (ValueError), not a silent string.
- PropositionNode {expr_id, head, arguments[], status TOP_LEVEL|EMBEDDED, epistemic_status}
  (§16.1): embedded propositions carry EpistemicStatus != ASSERTED; the pair
  'attitude -> epistemic status' is a declared resource mapping — undeclared stays UNKNOWN.
- EventFrame {frame_id, predicate, participants[], state, provenance} (§16.3).
- ScopeOperatorNode / ScopeTreeCandidate (§15.3): one representation for ALL operator
  types; nesting is a tree (node.operand may be another node); canonical render() gives
  the round-trippable serialization (Phase 2: N.meta["scope"] [B11]).
- SemanticGraphCandidate {graph_id, ir_ref, nodes[], edges[], ambiguity_sets[]} (§16.7) —
  competing graphs COEXIST as linked alternatives until an explicit discard (I29).
- CandidateIR (§2.1 line 126): IMMUTABLE assembly of all local structures; the ONLY
  exit of the formalizer into the Consolidator.

Nothing here creates identity links, memory facts or commits (I24/I25): the IR is a
frozen proposal bundle with provenance on every structure.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from ah.formalizer.state import ResourceProvenance

# §16.2 — closed set of argument types (Rev14.1: extension = new schema version).
ARGUMENT_TYPES = ("ENTITY", "EVENT", "PROPOSITION", "PROPERTY", "SET", "VALUE", "TIME", "LOCATION")

# §16.1 — epistemic statuses; the attitude->status mapping is a DECLARED resource,
# an undeclared attitude stays UNKNOWN (never silently ASSERTED).
EPISTEMIC_STATUSES = ("ASSERTED", "POSSIBLE", "NECESSARY", "EMBEDDED_UNKNOWN", "UNKNOWN")

# §1.3 — coverage levels, ORTHOGONAL to Decision.outcome. FULL_CANONICAL: fully covered structure with a
# verified canonical T; OPEN_LEXICAL: full structure with isolated open-T (no semantic-equivalence rule);
# PARTIAL: independent covered fragments plus uncovered links/regions; NONE: no useful candidate.
COVERAGE_LEVELS = ("FULL_CANONICAL", "OPEN_LEXICAL", "PARTIAL", "NONE")


@dataclass(frozen=True)
class CoverageStatus:
    """§1.3 — how much of the input is structurally covered, independent of any decision outcome."""

    level: str  # one of COVERAGE_LEVELS
    covered_span_ids: tuple[str, ...] = ()
    unresolved_span_ids: tuple[str, ...] = ()
    inference_restrictions: tuple[str, ...] = ()
    surface_role_count: int = 0

    def __post_init__(self):
        if self.level not in COVERAGE_LEVELS:
            raise ValueError(f"unknown coverage level {self.level!r}")
        overlap = set(self.covered_span_ids) & set(self.unresolved_span_ids)
        if overlap:
            raise ValueError(f"span(s) both covered and unresolved: {sorted(overlap)}")


@dataclass(frozen=True)
class ArgumentSpec:
    """§16.2 — a typed argument slot of an EventFrame/PropositionNode."""

    slot_ref: str  # role name (e.g. SUBJECT, OBJECT, PROPOSITION)
    arg_type: str  # one of ARGUMENT_TYPES (closed set)
    value: object = None  # mention span | PropositionNode | existential ref id

    def __post_init__(self):
        if self.arg_type not in ARGUMENT_TYPES:
            raise ValueError(f"unknown ArgumentType {self.arg_type!r} — closed set violation (§16.2)")


@dataclass(frozen=True)
class EventFrame:
    """§16.3 — the basic semantic model of a predicate event."""

    frame_id: str
    predicate: str  # surface lemma (PredicateSchema entry optional; absent -> KNOWLEDGE_ABSENT miss, §16.9)
    participants: tuple[ArgumentSpec, ...] = ()
    state: str = "PROPOSED"  # PROPOSED | CONFIRMED_BY_DECISION
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)

    def render(self) -> str:
        args = ", ".join(
            a.value.render() if isinstance(a.value, PropositionNode) else str(a.value)
            for a in self.participants
        )
        return f"{self.predicate.upper()}({args})"


@dataclass(frozen=True)
class PropositionNode:
    """§16.1 — an embedded proposition is NOT a fact of the observation."""

    expr_id: str
    head: object  # EventFrame | nested PropositionNode (composition, §16.8 example 1)
    status: str = "EMBEDDED"  # TOP_LEVEL | EMBEDDED
    epistemic_status: str = "UNKNOWN"  # EPISTEMIC_STATUSES; undeclared attitude -> UNKNOWN
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)

    def __post_init__(self):
        if self.status not in ("TOP_LEVEL", "EMBEDDED"):
            raise ValueError(f"unknown proposition status {self.status!r}")
        if self.epistemic_status not in EPISTEMIC_STATUSES:
            raise ValueError(f"unknown epistemic status {self.epistemic_status!r}")

    def render(self) -> str:
        return f"P({self.head.render()})"


@dataclass(frozen=True)
class ScopeOperatorNode:
    """§15.3 — the SINGLE representation of all scope operators (Rev13).

    ``operand`` is either another ScopeOperatorNode (nesting = tree) or a string ref
    to an EventFrame/PropositionNode (the EVENT the innermost operator scopes over).
    QUANT/RESTRICT carry the local binding: target_slot_ref + local_variable_id
    (interpretation-local — NOT a canonical BoundVar; Phase 2 NQ5 boundary holds)
    and restriction_ref (the quantification-domain expression, if any)."""

    operator_id: str
    operator_type: str  # declared set (§15.3 п.1): QUANT{EVERY,SOME,AT_LEAST_N} | NEG{NOT} | MODAL{POSSIBLE,NECESSARY} | COND{IF} | RESTRICT{ONLY}
    operand: object = None  # ScopeOperatorNode | str (frame ref)
    target_slot_ref: str | None = None  # required for QUANT/RESTRICT [Rev13]
    local_variable_id: str | None = None
    restriction_ref: str | None = None
    scope_span: tuple[str, ...] = ()  # surface trigger span(s)
    binding: object = None  # materialization reference (Phase 2)
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)

    def render(self) -> str:
        inner = self.operand.render() if isinstance(self.operand, ScopeOperatorNode) else str(self.operand or "?")
        local = ""
        if self.operator_type in ("EVERY", "SOME", "AT_LEAST_N", "ONLY"):
            local = f"{self.local_variable_id or 'x'}|{self.restriction_ref or '?'}"
        return f"{self.operator_type}{local}({inner})"


@dataclass(frozen=True)
class ScopeTreeCandidate:
    """§15.3 — one satisfying scope tree; several coexist as candidates (bounded
    selection or AMBIGUOUS), zero -> SCOPE_NOT_COVERED + miss."""

    tree_id: str
    graph_id: str
    root: ScopeOperatorNode  # the outermost operator; EVENT ref at the bottom of the chain
    nodes: tuple[ScopeOperatorNode, ...] = ()  # all operators, outer -> inner
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)

    def render(self) -> str:
        return self.root.render()


@dataclass(frozen=True)
class SemanticGraphCandidate:
    """§16.7 — unifies ALL local structures into one candidate graph; the only input
    to the Consolidator (§2.6). Competing graphs coexist (I29) until explicit discard."""

    graph_id: str
    ir_ref: str
    nodes: tuple[object, ...] = ()  # EventFrame | PropositionNode
    edges: tuple[tuple[str, str, str], ...] = ()  # (source, target, kind): dependency|scope|reference|constraint
    ambiguity_sets: tuple[tuple[str, ...], ...] = ()
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)

    def render(self) -> str:
        return " + ".join(n.render() for n in self.nodes if hasattr(n, "render"))


@dataclass(frozen=True)
class CandidateIR:
    """§2.1 (line 126) — the IMMUTABLE assembly of all local structures; the ONLY
    exit of the formalizer into the Consolidator. Rev14.1: frozen by contract."""

    ir_id: str
    observation_id: str
    interpretation_version: int
    lexical_units: tuple[str, ...] = ()
    clauses: tuple[str, ...] = ()
    mention_candidates: tuple[object, ...] = ()
    predicate_frames: tuple[str, ...] = ()
    dependency_candidates: tuple[object, ...] = ()
    operator_trees: tuple[ScopeTreeCandidate, ...] = ()
    coreference_candidates: tuple[object, ...] = ()
    structural_candidates: tuple[object, ...] = ()
    temporal_candidates: tuple[object, ...] = ()
    semantic_candidates: tuple[SemanticGraphCandidate, ...] = ()  # §16.7 graphs
    ambiguity_sets: tuple[tuple[str, ...], ...] = ()
    coverage: CoverageStatus | None = None  # §1.3 — orthogonal to Decision.outcome
    provenance: ResourceProvenance = field(default_factory=ResourceProvenance)


def assert_immutable(ir: CandidateIR) -> None:
    """Rev14.1 contract check: the IR is frozen — any mutation attempt raises."""
    try:
        ir.ir_id = "tampered"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("CandidateIR accepted a mutation — immutability violated")


def compute_coverage(
    covered_span_ids: tuple[str, ...],
    unresolved_span_ids: tuple[str, ...] = (),
    surface_role_count: int = 0,
    open_lexical: bool = False,
    useful_candidate: bool = True,
) -> CoverageStatus:
    """§1.3 — deterministic coverage level from the covered/unresolved span sets.

    NONE when there is no useful candidate and nothing is covered; PARTIAL when some region/link is
    unresolved while others are covered; OPEN_LEXICAL when fully covered but an isolated open-T remains;
    FULL_CANONICAL only for a fully covered, closed structure."""
    if not useful_candidate and not covered_span_ids:
        level = "NONE"
    elif unresolved_span_ids:
        level = "PARTIAL" if covered_span_ids else "NONE"
    elif open_lexical:
        level = "OPEN_LEXICAL"
    else:
        level = "FULL_CANONICAL"
    return CoverageStatus(
        level=level,
        covered_span_ids=tuple(covered_span_ids),
        unresolved_span_ids=tuple(unresolved_span_ids),
        surface_role_count=surface_role_count,
    )


def assemble_candidate_ir(state, ir_id: str = "ir0") -> CandidateIR:
    """WP1.5 — the immutable single exit of the formalizer into the Consolidator.

    Gathers span coverage from the sealed token evidence (covered = resolved non-OOV tokens,
    unresolved = OOV keep-as-is) and attaches a CoverageStatus orthogonal to every decision outcome.
    Pure: it reads ``state`` but changes nothing, so wiring it at the end of a run cannot alter any
    already-granted outcome."""
    evidence = getattr(state, "evidence", ()) or ()
    covered, unresolved = [], []
    for ev in evidence:
        (unresolved if getattr(ev, "is_oov", lambda: False)() else covered).append(ev.span)
    coverage = compute_coverage(
        tuple(covered), tuple(unresolved),
        open_lexical=bool(unresolved),  # an OOV keep-as-is token is an isolated open-T
    )
    return CandidateIR(
        ir_id=ir_id,
        observation_id=getattr(state, "observation_id", "obs"),
        interpretation_version=getattr(state, "interpretation_version", 1),
        lexical_units=tuple(ev.span for ev in evidence),
        coverage=coverage,
    )
