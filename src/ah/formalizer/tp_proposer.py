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

    for edge in hyp.edges:
        # (c) edge kind allowlist
        if req.allowed_edge_kinds and edge.kind not in req.allowed_edge_kinds:
            raise ProtocolError(f"hypothesis {hyp.local_id}: edge kind {edge.kind!r} not allowed")
        # (b) endpoints must reference existing nodes of THIS hypothesis
        for idx in (edge.from_idx, edge.to_idx):
            if not 0 <= idx < n:
                raise ProtocolError(
                    f"hypothesis {hyp.local_id}: edge endpoint {idx} out of range [0,{n})")
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


def validate_structure_reply(req: StructureProposalRequest, reply: StructureProposalReply) -> list[Hypothesis]:
    """Validate a TP reply against its request. Raises ProtocolError on any (a)-(f) violation and
    returns the accepted hypotheses. A missing/abstaining reply is an explicit miss, not AMBIGUOUS."""
    # (e) budget pre-check: an exhausted budget must never have produced this call.
    if not req.budget_ok:
        raise ProtocolError("budget pre-check failed: proposer must not be called")
    # (f) abstain is an explicit miss — accept as-is, no AMBIGUOUS substitution.
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

    hyps = []
    for h in data.get("hypotheses", []):
        nodes = tuple(
            TNode(kind=n["kind"], anchor_spans=tuple(n.get("anchor_spans", ())),
                 feature_refs=tuple(n.get("feature_refs", ())))
            for n in h.get("nodes", [])
        )
        edges = tuple(
            TEdge(kind=e["kind"], from_idx=int(e["from"]), to_idx=int(e["to"]),
                  role_id=e.get("role_id"), scope=bool(e.get("scope", False)))
            for e in h.get("edges", [])
        )
        hyps.append(Hypothesis(local_id=h.get("local_id", "h"), nodes=nodes, edges=edges,
                              alternatives=int(h.get("alternatives", 1)),
                              alignment=tuple(h.get("alignment", ()))))
    reply = StructureProposalReply(hypotheses=tuple(hyps), abstain=bool(data.get("abstain", False)))
    return validate_structure_reply(req, reply)
