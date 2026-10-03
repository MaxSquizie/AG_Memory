# -*- coding: utf-8 -*-
"""Deterministic composition layer (Rev18) — the audit's expressiveness core.

Two DECLARED versioned resources (the two-tier invariant: structural rules are
allowed when declared + corpus-tested; nothing here is per-sentence knowledge):

- CONNECTIVES_V1 = {"что"}  [connectives_v1] — subordinator connective pattern for
  OP4_NESTED clause attachment. A new connective = a new resource version (I13).
- SCOPE_LEXICON_V1 [(pos, lemma) -> operator_type]  [scope_lexicon_v1] — the demo v1
  scope lexicon (§5.2 п.10 / §15.3): PRCL 'не' -> NOT; ADJF 'каждый' -> EVERY;
  VERB 'мочь' -> POSSIBLE. A new trigger = a resource declaration, never core code.

OperatorCompositionEngine (V5 §15.3 п.2, Rev13a) — ONE generic nesting rule for ALL
operator types: depth_rank of a trigger = the number of tokens between its end and the
start of the NEAREST rightward predicate center (finite VERB or INFN); equal ranks are
resolved by surface order left-to-right. The operator with the LARGER rank attaches
OUTER; the innermost operator scopes over the EVENT node (the frame anchored at the
rightmost predicate center). No per-operator special cases: 'Не каждый студент мог не
сдать экзамен.' yields NOT(EVERY(POSSIBLE(NOT(F)))) purely from positions.

Graph derivations (§16.7, I29): a subordinator with several admissible matrix centers
yields the PRIMARY derivation (nearest center) plus ONE alternative per non-nearest
choice (bounded enumeration — not a cross product). Competing SemanticGraphCandidates
coexist as linked alternatives until an explicit discard; nothing is deleted silently.

assemble_ir() freezes everything into the immutable CandidateIR (§2.1 line 126) —
the ONLY exit of the formalizer. No identity links, no memory facts, no commits (I24/I25).
"""
from __future__ import annotations

from ah.formalizer.candidate_ir import (
    ArgumentSpec,
    CandidateIR,
    EventFrame,
    PropositionNode,
    ScopeOperatorNode,
    ScopeTreeCandidate,
    SemanticGraphCandidate,
)
from ah.formalizer.state import FormalizationState, LinkedAlternative, ResourceProvenance

# ---------------------------------------------------------------- declared resources

CONNECTIVES_V1: dict[str, str] = {"что": "SUBORDINATE"}  # lemma -> construction label
_CONNECTIVES_VERSION = "connectives_v1"

SCOPE_LEXICON_V1: dict[tuple[str, str], str] = {
    ("PRCL", "не"): "NOT",
    ("ADJF", "каждый"): "EVERY",
    ("VERB", "мочь"): "POSSIBLE",
}
_SCOPE_LEX_VERSION = "scope_lexicon_v1"

_QUANT_TYPES = {"EVERY", "SOME", "AT_LEAST_N", "ONLY"}


def _top(ev) -> tuple[str | None, str | None]:
    """(pos, lemma) of the top-scored variant — R1 features only."""
    if not ev.variants:
        return (None, None)
    v = max(ev.variants, key=lambda x: x.score)
    return (v.pos, (v.lemma or "").lower() or None)


def _is_nominal(ev) -> bool:
    pos, _ = _top(ev)
    return pos in ("NOUN", "ADJF") and not ev.is_oov()


def _predicate_centers(evs) -> list[int]:
    """Declared predicate centers for scope depth: finite verbs + infinitives."""
    out = []
    for i, e in enumerate(evs):
        if not e.variants or e.is_oov():
            continue
        v = max(e.variants, key=lambda x: x.score)
        if v.pos == "VERB" and v.tense in ("past", "present", "future"):
            out.append(i)
        elif v.pos == "INFN":
            out.append(i)
    return out


# ---------------------------------------------------------------- scope engine (§15.3)

def build_scope_trees(state: FormalizationState) -> list[ScopeTreeCandidate]:
    """OperatorCompositionEngine [Rev13a]: one generic depth rule for all types.

    A trigger without a rightward predicate center is NOT silently dropped — it yields
    SCOPE_NOT_COVERED and stays a modifier (§5.2 п.10)."""
    evs = state.evidence
    prov = ResourceProvenance(
        pattern_ids=("OperatorCompositionEngine",),
        resource_versions={"scope_lexicon": _SCOPE_LEX_VERSION},
    )
    centers = _predicate_centers(evs)
    triggers: list[tuple[int, str]] = []  # (token index, operator type)
    for i, e in enumerate(evs):
        key = _top(e)
        otype = SCOPE_LEXICON_V1.get(key)
        if otype is None:
            continue
        right = [c for c in centers if c > i]
        if not right:
            state.diag("SCOPE_NOT_COVERED", f"scope trigger '{e.span}' has no rightward predicate center")
            continue  # the token stays a modifier — never silently lost
        triggers.append((i, otype))

    if not triggers:
        return []

    # depth_rank = tokens between the trigger's end and the nearest rightward center.
    ranked = sorted(
        ((c - i - 1, i, t) for i, t in triggers for c in [min(x for x in centers if x > i)]),
        key=lambda x: (-x[0], x[1]),  # outer first; equal ranks -> surface order L->R (Rev13a)
    )

    # EVENT node = the frame anchored at the rightmost predicate center of the unit.
    event_ref = "EVENT?"
    if state.frames:
        anchor_idx = max(
            (evs.index(next(e for e in evs if e.span == f.anchor_span))
             for f in state.frames if any(e.span == f.anchor_span for e in evs)),
            default=None,
        )
        rightmost = max(state.frames, key=lambda f: next(
            (j for j, e in enumerate(evs) if e.span == f.anchor_span), 0))
        event_ref = rightmost.frame_id

    # Local binding for QUANT/RESTRICT [Rev13]: the nearest nominal between the trigger
    # and its center is the quantification domain (declared structural rule).
    chain: list[ScopeOperatorNode] = []
    x_count = 0
    operand: object = event_ref
    for _depth, i, otype in reversed(ranked):  # innermost first
        target = None
        if otype in _QUANT_TYPES:
            center = min(c for c in centers if c > i)
            for j in range(i + 1, center):
                if _is_nominal(evs[j]):
                    target = evs[j].span
                    break
            x_count += 1
        node = ScopeOperatorNode(
            operator_id=f"OP{i}",
            operator_type=otype,
            operand=operand,
            target_slot_ref=(f"slot:{target}" if otype in _QUANT_TYPES else None),
            local_variable_id=(f"x{x_count}" if otype in _QUANT_TYPES else None),
            restriction_ref=target,
            scope_span=(evs[i].span,),
            provenance=prov,
        )
        chain.append(node)
        operand = node
    chain.reverse()  # outer -> inner
    return [ScopeTreeCandidate(
        tree_id="ST1", graph_id="G1", root=chain[0], nodes=tuple(chain), provenance=prov,
    )]


# ---------------------------------------------------------------- graphs (§16.7)

def _clause_ranges(evs) -> list[tuple[int, int]]:
    """Matrix clause + one subclause per declared connective (inclusive token ranges)."""
    conns = [i for i, e in enumerate(evs) if _top(e)[0] == "CONJ" and _top(e)[1] in CONNECTIVES_V1]
    if not conns:
        return [(0, len(evs) - 1)]
    ranges = [(0, conns[0] - 1)]
    for k, c in enumerate(conns):
        end = (conns[k + 1] - 1) if k + 1 < len(conns) else len(evs) - 1
        ranges.append((c + 1, end))
    return [(a, b) for a, b in ranges if a <= b]


def _clause_event(state: FormalizationState, rng: tuple[int, int]) -> EventFrame | None:
    """The clause's event: its finite-verb center + the clause's OWN nominal mentions.
    Declared slot rule: the first nominal before the center is SUBJECT, the rest OBJECT."""
    evs = state.evidence
    prov = ResourceProvenance(
        pattern_ids=("OP4_nested",),
        resource_versions={"grammar": "op1-op5-v2", _CONNECTIVES_VERSION: "v1"},
    )
    lo, hi = rng  # inclusive token range
    center_i = None
    for i in range(lo, hi + 1):
        v = max(evs[i].variants, key=lambda x: x.score) if evs[i].variants else None
        if v is not None and v.pos == "VERB" and v.tense in ("past", "present", "future"):
            center_i = i
            break
    if center_i is None:
        return None
    parts: list[ArgumentSpec] = []
    subject_seen = False
    for i in range(lo, hi + 1):
        e = evs[i]
        if not _is_nominal(e):
            continue
        if i < center_i and not subject_seen:
            slot, subject_seen = "SUBJECT", True
        else:
            slot = "OBJECT"
        parts.append(ArgumentSpec(slot_ref=slot, arg_type="ENTITY", value=e.span))
    v = max(evs[center_i].variants, key=lambda x: x.score)
    return EventFrame(
        frame_id=f"G-{evs[center_i].span}", predicate=(v.lemma or evs[center_i].span),
        participants=tuple(parts), state="PROPOSED", provenance=prov,
    )


def _flat_participants(evs, frame) -> tuple[ArgumentSpec, ...]:
    """Apply the SAME declared slot rule as ``_clause_event`` to a FLAT frame (no per-word rules):
    in surface order, the first nominal mention before the predicate anchor is SUBJECT, the rest OBJECT.

    This closes the historical 'ARG' gap: flat frames now carry role-typed participants exactly like
    clause events do, so downstream materialization can bind them as actants."""

    def pos(span: str) -> int | None:
        for i, e in enumerate(evs):
            if e.span == span:
                return i
        return None

    center = pos(frame.anchor_span)
    ordered = sorted(((pos(p), p) for p in frame.participants if pos(p) is not None), key=lambda t: t[0])
    parts: list[ArgumentSpec] = []
    subject_seen = False
    for i, span in ordered:
        if center is not None and i < center and not subject_seen:
            slot, subject_seen = "SUBJECT", True
        else:
            slot = "OBJECT"
        parts.append(ArgumentSpec(slot_ref=slot, arg_type="ENTITY", value=span))
    return tuple(parts)


def build_graphs(state: FormalizationState) -> list[SemanticGraphCandidate]:
    """Competing SemanticGraphCandidates (§16.7). With declared connectives: the PRIMARY
    derivation (each subclause attaches to its NEAREST matrix center) plus ONE alternative
    per non-nearest admissible center (bounded, declared — not a cross product).
    Without connectives: one graph over all FLAT frames.
    Non-primary graphs are registered as LinkedAlternatives (I29)."""
    evs = state.evidence
    prov = ResourceProvenance(
        pattern_ids=("OP4_nested",),
        resource_versions={"grammar": "op1-op5-v2", _CONNECTIVES_VERSION: "v1"},
    )
    conns = [i for i, e in enumerate(evs) if _top(e)[0] == "CONJ" and _top(e)[1] in CONNECTIVES_V1]

    if not conns:
        nodes = tuple(
            EventFrame(frame_id=f.frame_id, predicate=_lemma_of(evs, f.anchor_span),
                       participants=_flat_participants(evs, f),
                       state="PROPOSED", provenance=prov)
            for f in state.frames if f.kind == "FLAT"
        )
        return [SemanticGraphCandidate(graph_id="G1", ir_ref=f"IR-{state.source_uid}",
                                      nodes=nodes, edges=(), ambiguity_sets=(), provenance=prov)]

    # Clause events (matrix + subclauses), in surface order.
    ranges = _clause_ranges(evs)
    clause_events: list[EventFrame | None] = [_clause_event(state, r) for r in ranges]

    def centers_before(i: int) -> list[int]:
        return [c for c in _predicate_centers(evs)
                if c < i and evs[c].pos == "VERB"
                and any(v.tense in ("past", "present", "future") for v in evs[c].variants)]

    # Admissible attachments per connective: nearest first, then the rest (surface order).
    choices: list[list[int]] = []
    for c in conns:
        before = centers_before(c)
        if not before:
            state.diag("SCOPE_NOT_COVERED", f"connective '{evs[c].span}' has no matrix center")
            continue
        nearest = max(before)
        choices.append([nearest] + sorted(b for b in before if b != nearest))

    # Bounded derivations: primary (all-nearest) + one alternative per non-nearest choice.
    base = [ch[0] for ch in choices]
    derivations = [list(base)]
    for k, ch in enumerate(choices):
        for alt in ch[1:]:
            d = list(base)
            d[k] = alt
            if d not in derivations:
                derivations.append(d)

    def derive(attach: list[int]) -> SemanticGraphCandidate:
        """One derivation: rebuild clause events, attaching subclause k (ranges[k+1]) to
        the clause containing attach[k]. Innermost first so nested P nodes compose."""
        import dataclasses as _dc
        events = list(clause_events)
        edges: list[tuple[str, str, str]] = []
        for k in range(len(ranges) - 1, 0, -1):  # innermost subclause first
            ev = events[k]
            if ev is None:
                continue
            center = attach[k - 1] if k - 1 < len(attach) else None
            host_idx = next((r for r in range(len(ranges))
                             if ranges[r][0] <= (center or -1) <= ranges[r][1]), 0)
            host = events[host_idx]
            pnode = PropositionNode(expr_id=f"P{k}", head=ev, status="EMBEDDED",
                                    epistemic_status="UNKNOWN", provenance=prov)
            if host is not None:
                events[host_idx] = _dc.replace(host, participants=host.participants + (
                    ArgumentSpec(slot_ref="PROPOSITION", arg_type="PROPOSITION", value=pnode),))
                edges.append((host.frame_id, pnode.expr_id, "dependency"))
        nodes = tuple(e for e in events if e is not None)
        return SemanticGraphCandidate(
            graph_id="", ir_ref=f"IR-{state.source_uid}",
            nodes=nodes, edges=tuple(edges), ambiguity_sets=(), provenance=prov,
        )

    graphs = []
    for gi, attach in enumerate(derivations):
        g = derive(attach)
        import dataclasses as _dc
        graphs.append(_dc.replace(g, graph_id=f"G{gi + 1}"))

    if len(graphs) > 1:
        for g in graphs[1:]:  # I29: linked alternatives until explicit discard
            state.linked_alternatives.append(LinkedAlternative(
                alt_id=f"alt-{g.graph_id}", kind="SEMANTIC_GRAPH",
                description=g.render(), source_candidate_id=g.graph_id, provenance=prov,
            ))
    return graphs


def _lemma_of(evs, span: str) -> str:
    for e in evs:
        if e.span == span and e.variants:
            v = max(e.variants, key=lambda x: x.score)
            return v.lemma or span
    return span


# ---------------------------------------------------------------- journal window

def journal_mentions_from(obs_state: FormalizationState) -> tuple[str, ...]:
    """Declared NQ7 default window content: the nominal mentions of a prior observation.
    These enter TD as GENERATION-channel candidates (W evidence), never as facts."""
    out = []
    for e in obs_state.evidence:
        pos, _ = _top(e)
        if pos in ("NOUN", "ADJF") and not e.is_oov():
            out.append(e.span)
    return tuple(out)


# ---------------------------------------------------------------- IR assembly (§2.1)

def assemble_ir(state: FormalizationState) -> CandidateIR:
    """Freeze ALL local structures into the immutable CandidateIR — the ONLY exit of
    the formalizer (Rev14.1). No identity links, no memory facts, no commits here."""
    prov = ResourceProvenance(
        pattern_ids=("assemble_ir",), resource_versions={"candidate_ir": "v1"},
    )
    trees = build_scope_trees(state)
    graphs = build_graphs(state)
    ambiguous: list[tuple[str, ...]] = []
    for dec in state.decisions.values():
        if dec.outcome == "AMBIGUOUS" and len(dec.selected) > 1:
            ambiguous.append(tuple(dec.selected))
    if len(graphs) > 1:
        ambiguous.append(tuple(g.graph_id for g in graphs))
    structural = (
        *state.token_hypotheses, *state.boundary_candidates, *state.clause_candidates,
        *state.ellipsis_candidates, *state.missing_argument_candidates,
    )
    return CandidateIR(
        ir_id=f"IR-{state.source_uid}",
        observation_id=state.source_uid,
        interpretation_version=state.interpretation_version,
        lexical_units=tuple(e.span for e in state.evidence),
        clauses=tuple(c.candidate_id for c in state.clause_candidates),
        predicate_frames=tuple(f.frame_id for f in state.frames),
        operator_trees=tuple(trees),
        coreference_candidates=tuple(state.reference_candidates),
        structural_candidates=structural,
        semantic_candidates=tuple(graphs),
        ambiguity_sets=tuple(ambiguous),
        provenance=prov,
    )
