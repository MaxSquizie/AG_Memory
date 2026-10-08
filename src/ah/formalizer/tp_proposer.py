# -*- coding: utf-8 -*-
"""TP protocol: the general typed local-structure hypothesis contract (V7 §4.5 / WP1.3).

When deterministic candidates do not cover a structural gap, TP proposes a BOUNDED local region
(a clause plus affected attachments) — never the whole canonical graph. The reply is validated by a
deterministic validator BEFORE anything downstream may use it; a rejected or missing reply is an
explicit miss, never silently substituted by AMBIGUOUS.

This module formalizes the protocol that was previously implicit in the pipeline's structural pass.
It is pure (no store, no LLM): the proposer is injected and returns raw JSON, exactly like the
bounded-selection micro-shot; all model traffic still goes through ProviderCallLog (§0.8).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ah.formalizer.selection_protocol import ProtocolError

# The only role ids a TP reply may name without inventing new registry entries: the two roles that
# MUST exist (EXPERIENCER) plus the syntactic-only SURFACE_ARG. Anything else is a protocol error (a).
DEFAULT_ALLOWED_ROLES = frozenset({"EXPERIENCER", "SURFACE_ARG"})


@dataclass(frozen=True)
class TNode:
    kind: str                          # must be in request.allowed_node_kinds (c)
    anchor_spans: tuple[str, ...]      # must be a subset of request.source_spans (b)
    feature_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class TEdge:
    kind: str                          # must be in request.allowed_edge_kinds (c)
    from_idx: int                      # 0-based index into the hypothesis' nodes (b)
    to_idx: int                        # 0-based index into the hypothesis' nodes (b)
    role_id: str | None = None         # a PROVEN semantic role, SURFACE_ARG, or None — never invented (a/d)
    scope: bool = False


@dataclass(frozen=True)
class Hypothesis:
    local_id: str
    nodes: tuple[TNode, ...]
    edges: tuple[TEdge, ...] = ()
    alternatives: int = 1              # number of alternative readings offered (>=1); several allowed
    alignment: tuple[str, ...] = ()


@dataclass(frozen=True)
class StructureProposalRequest:
    request_id: str
    structural_hash_pre: str           # pre-seal hash of deterministic structures (ties to WP1.1 seal)
    source_spans: tuple[str, ...]      # the bounded local region TP may touch
    token_hypotheses: tuple = ()
    deterministic_candidates: tuple = ()
    uncovered_spans: tuple[str, ...] = ()
    allowed_node_kinds: frozenset = field(default_factory=frozenset)
    allowed_edge_kinds: frozenset = field(default_factory=frozenset)
    allowed_role_ids: frozenset = DEFAULT_ALLOWED_ROLES
    declared_reads: tuple[str, ...] = ()
    policy_version: str = "tp_policy_v1"
    budget_ok: bool = True             # result of budget_precheck; a False request must not be sent
    schema_version: str = ""
    max_nodes: int = 64
    max_edges: int = 128
    max_depth: int = 16
    required_operators: tuple = ()  # (operator kind, anchored trigger token IDs)


@dataclass(frozen=True)
class StructureProposalReply:
    hypotheses: tuple[Hypothesis, ...] = ()
    abstain: bool = False              # explicit miss — never substituted by AMBIGUOUS (f)


def budget_precheck(budget) -> bool:
    """§4.5/§0.8: if the LLM budget is exhausted the proposer must NOT be called."""
    return not getattr(budget, "llm_exhausted", False)


# -- deterministic validator (a–f) ------------------------------------------ #
def _validate_hypothesis(req: StructureProposalRequest, hyp: Hypothesis) -> None:
    if not hyp.nodes:
        raise ProtocolError(f"hypothesis {hyp.local_id}: no nodes")
    n = len(hyp.nodes)
    if n > req.max_nodes or len(hyp.edges) > req.max_edges or hyp.alternatives < 1:
        raise ProtocolError("PROPOSAL_BUDGET")
    if not hyp.local_id or not hyp.alignment or not set(hyp.alignment) <= set(req.source_spans):
        raise ProtocolError("invalid hypothesis identity/alignment")
    features = {str(getattr(t, "hypothesis_id", t)) for t in req.token_hypotheses}
    for node in hyp.nodes:
        if not node.anchor_spans or not set(node.feature_refs) <= features:
            raise ProtocolError("unanchored node or undeclared feature ref")
    src = set(req.source_spans)

    for node in hyp.nodes:
        # (c) node kind allowlist
        if req.allowed_node_kinds and node.kind not in req.allowed_node_kinds:
            raise ProtocolError(f"hypothesis {hyp.local_id}: node kind {node.kind!r} not allowed")
        # (b) bounded region: every anchor span must lie inside the declared local region
        for span in node.anchor_spans:
            if span not in src:
                raise ProtocolError(
                    f"hypothesis {hyp.local_id}: anchor span {span!r} outside the bounded region")

    graph = {i:[] for i in range(n)}
    for edge in hyp.edges:
        # (c) edge kind allowlist
        if req.allowed_edge_kinds and edge.kind not in req.allowed_edge_kinds:
            raise ProtocolError(f"hypothesis {hyp.local_id}: edge kind {edge.kind!r} not allowed")
        # (b) endpoints must reference existing nodes of THIS hypothesis
        for idx in (edge.from_idx, edge.to_idx):
            if not 0 <= idx < n:
                raise ProtocolError(
                    f"hypothesis {hyp.local_id}: edge endpoint {idx} out of range [0,{n})")
        graph[edge.from_idx].append(edge.to_idx)
        a,b=hyp.nodes[edge.from_idx].kind,hyp.nodes[edge.to_idx].kind
        if edge.kind in {'ARGUMENT','ATTITUDE'} and (a!='PREDICATE' or b not in {'PREDICATE','ENTITY'} or not edge.role_id):
            raise ProtocolError('invalid typed argument edge')
        if edge.kind=='ATTITUDE' and b!='PREDICATE':
            raise ProtocolError('attitude target must be a proposition')
        if edge.kind=='BIND' and (a!='BOUND_VAR' or b!='ENTITY'):
            raise ProtocolError('invalid bound-variable edge')
        if edge.kind=='OPERAND' and (a in {'PREDICATE','ENTITY','BOUND_VAR'} or b=='ENTITY'):
            raise ProtocolError('invalid operator operand type')
        # (a) no invented role ids; (d) SURFACE_ARG is syntactic-only and cannot swallow the whole region
        if edge.role_id is not None:
            if edge.role_id not in req.allowed_role_ids:
                raise ProtocolError(
                    f"hypothesis {hyp.local_id}: role {edge.role_id!r} not a registered role")
            if edge.role_id == "SURFACE_ARG":
                target = hyp.nodes[edge.to_idx]
                anchors = set(target.anchor_spans)
                # (d) SURFACE_ARG must bind a real, proper sub-region — never the entire bounded region.
                if not anchors or not anchors < src:
                    raise ProtocolError(
                        f"hypothesis {hyp.local_id}: SURFACE_ARG must anchor a proper sub-region")

    for kind,spans in req.required_operators:
        if not any(node.kind==kind and set(node.anchor_spans)&set(spans) for node in hyp.nodes):
            raise ProtocolError('source operator scope silently lost:'+kind)

    arities={'NOT':(1,1),'POSSIBLE':(1,1),'NECESSARY':(1,1),
             'AND':(2,None),'OR':(2,None),'XOR':(2,None),
             'IMPLIES':(2,2),'COUNTERFACTUAL':(2,2),'ASSOCIATION':(2,2),
             'FORALL':(2,2),'EXISTS':(2,2),'BEFORE':(2,2),'AFTER':(2,2),'DURING':(2,2)}
    for idx,node in enumerate(hyp.nodes):
        operands=[hyp.nodes[e.to_idx] for e in hyp.edges if e.from_idx==idx and e.kind=='OPERAND']
        if node.kind in arities:
            lo,hi=arities[node.kind]
            if len(operands)<lo or hi is not None and len(operands)>hi:
                raise ProtocolError('operator arity mismatch:'+node.kind)
            if node.kind in {'FORALL','EXISTS'}:
                if operands[0].kind!='BOUND_VAR' or operands[1].kind in {'BOUND_VAR','ENTITY'}:
                    raise ProtocolError('quantifier requires [bound_var, body]')
            elif any(x.kind=='BOUND_VAR' for x in operands):
                raise ProtocolError('bound_var outside quantifier slot')

    active=set(); done=set()
    def visit(i, depth):
        if i in active: raise ProtocolError("cyclic local structure")
        if depth > req.max_depth: raise ProtocolError("PROPOSAL_BUDGET: depth")
        if i in done: return
        active.add(i)
        for j in graph[i]: visit(j,depth+1)
        active.remove(i); done.add(i)
    for i in graph: visit(i,1)


def validate_structure_reply(req: StructureProposalRequest, reply: StructureProposalReply) -> list[Hypothesis]:
    """Validate a TP reply against its request. Raises ProtocolError on any (a)-(f) violation and
    returns the accepted hypotheses. A missing/abstaining reply is an explicit miss, not AMBIGUOUS."""
    # (e) budget pre-check: an exhausted budget must never have produced this call.
    if not req.budget_ok:
        raise ProtocolError("budget pre-check failed: proposer must not be called")
    # (f) abstain is an explicit miss — accept as-is, no AMBIGUOUS substitution.
    if reply.abstain and reply.hypotheses:
        raise ProtocolError("abstain with hypotheses")
    if len({h.local_id for h in reply.hypotheses}) != len(reply.hypotheses):
        raise ProtocolError("duplicate local hypothesis id")
    if reply.abstain or not reply.hypotheses:
        return []
    for hyp in reply.hypotheses:
        _validate_hypothesis(req, hyp)
    return list(reply.hypotheses)


def parse_and_validate(req: StructureProposalRequest, raw: str | None) -> list[Hypothesis]:
    """Parse a proposer's raw JSON reply and validate it. ``raw is None`` (no reply) is an explicit
    miss — returned as [] with NO AMBIGUOUS substitution (f). Malformed JSON / unknown fields raise."""
    if raw is None:
        return []  # missing reply -> explicit miss, never AMBIGUOUS
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"malformed TP reply JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("TP reply must be a JSON object")

    def fields(obj,allowed,required=()):
        if not isinstance(obj,dict) or set(obj)-set(allowed) or not set(required)<=set(obj):
            raise ProtocolError("unknown/missing TP fields")
    fields(data,{"hypotheses","abstain"})
    if not isinstance(data.get("abstain",False),bool) or not isinstance(data.get("hypotheses",[]),list):
        raise ProtocolError("invalid TP scalar/list type")
    hyps=[]
    try:
        for h in data.get("hypotheses",[]):
            fields(h,{"local_id","nodes","edges","alternatives","alignment"},{"local_id","nodes","alignment"})
            nodes=[]; edges=[]
            for v in h["nodes"]:
                fields(v,{"kind","anchor_spans","feature_refs"},{"kind","anchor_spans"})
                if not isinstance(v["anchor_spans"],list) or not all(isinstance(x,str) for x in v["anchor_spans"]):
                    raise ProtocolError("anchor_spans must be a list of source ids")
                nodes.append(TNode(v["kind"],tuple(v["anchor_spans"]),tuple(v.get("feature_refs",()))))
            for e in h.get("edges",[]):
                fields(e,{"kind","from","to","role_id","scope"},{"kind","from","to"})
                if type(e["from"]) is not int or type(e["to"]) is not int or type(e.get("scope",False)) is not bool:
                    raise ProtocolError("invalid TP endpoint/scope type")
                edges.append(TEdge(e["kind"],e["from"],e["to"],e.get("role_id"),e.get("scope",False)))
            if type(h.get("alternatives",1)) is not int or not isinstance(h["alignment"],list):
                raise ProtocolError("invalid alternative/alignment type")
            hyps.append(Hypothesis(h["local_id"],tuple(nodes),tuple(edges),h.get("alternatives",1),tuple(h["alignment"])))
    except (KeyError,TypeError,ValueError) as exc:
        raise ProtocolError("malformed TP hypothesis") from exc
    return validate_structure_reply(req,StructureProposalReply(tuple(hyps),data.get("abstain",False)))
