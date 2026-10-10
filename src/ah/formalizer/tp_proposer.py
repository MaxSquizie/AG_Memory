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
from dataclasses import asdict, dataclass, field

from ah.formalizer.selection_protocol import ProtocolError, _strip_code_fence

# The only role ids a TP reply may name without inventing new registry entries: the two roles that
# MUST exist (EXPERIENCER) plus the syntactic-only SURFACE_ARG. Anything else is a protocol error (a).
DEFAULT_ALLOWED_ROLES = frozenset({"EXPERIENCER", "SURFACE_ARG"})
PROPOSITION_NODE_KINDS = frozenset({'PREDICATE','NOT','AND','OR','XOR','IMPLIES','FORALL','EXISTS',
                                   'POSSIBLE','NECESSARY','COUNTERFACTUAL','BEFORE','AFTER','DURING','ASSOCIATION',
                                   'AT_LEAST_N','EXACTLY_N','AT_MOST_N'})


@dataclass(frozen=True)
class TNode:
    kind: str                          # must be in request.allowed_node_kinds (c)
    anchor_spans: tuple[str, ...]      # must be a subset of request.source_spans (b)
    feature_refs: tuple[str, ...] = ()
    head_anchor: str | None = None      # lexical head must be one of the captured raw token IDs


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


def build_structure_prompt(req: StructureProposalRequest, tokens: list[dict]) -> str:
    """Describe the actual wire format, without supplying a semantic answer.

    Request dataclasses alone do not tell a model the reply's mandatory keys,
    node-index convention or alignment requirements. Keep the response contract
    beside its validator; all enums/references come from this bounded request.
    """
    def obj(properties, required):
        return {'type': 'object', 'properties': properties,
                'required': list(required), 'additionalProperties': False}

    source_id = {'type': 'string', 'enum': list(req.source_spans)}
    source_ids = {'type': 'array', 'items': source_id, 'minItems': 1}
    features = [str(getattr(t, 'hypothesis_id', t)) for t in req.token_hypotheses]
    feature_refs = {'type': 'array', 'items': {'type': 'string', 'enum': features}}
    if not features:
        feature_refs = {'type': 'array', 'maxItems': 0}
    node = obj({
        'kind': {'type': 'string', 'enum': sorted(req.allowed_node_kinds)},
        'anchor_spans': source_ids,
        'feature_refs': feature_refs,
        'head_anchor': {'anyOf': [source_id, {'type': 'null'}]},
    }, ('kind', 'anchor_spans'))
    node['allOf'] = [
        {'if': {'properties': {'kind': {'enum': ['PREDICATE', 'ENTITY']}}},
         'else': {'properties': {'head_anchor': {'type': 'null'}}}},
        {'if': {'properties': {'kind': {'enum': ['PREDICATE', 'ENTITY']},
                               'anchor_spans': {'minItems': 2}}},
         'then': {'required': ['head_anchor'], 'properties': {'head_anchor': source_id}}},
    ]
    edge = obj({
        'kind': {'type': 'string', 'enum': sorted(req.allowed_edge_kinds)},
        'from': {'type': 'integer', 'minimum': 0},
        'to': {'type': 'integer', 'minimum': 0},
        'role_id': {'anyOf': [{'type': 'string', 'enum': sorted(req.allowed_role_ids)},
                              {'type': 'null'}]},
        'scope': {'type': 'boolean'},
    }, ('kind', 'from', 'to'))
    edge['allOf'] = [{
        'if': {'properties': {'kind': {'enum': ['ARGUMENT', 'ATTITUDE', 'QUERY_SLOT']}}},
        'then': {'required': ['role_id'],
                 'properties': {'role_id': {'type': 'string', 'enum': sorted(req.allowed_role_ids)}}},
    }]
    hypothesis = obj({
        'local_id': {'type': 'string', 'minLength': 1},
        'nodes': {'type': 'array', 'items': node, 'minItems': 1, 'maxItems': req.max_nodes},
        'edges': {'type': 'array', 'items': edge, 'maxItems': req.max_edges},
        'alternatives': {'type': 'integer', 'minimum': 1},
        'alignment': source_ids,
    }, ('local_id', 'nodes', 'alignment'))
    schema = obj({
        'hypotheses': {'type': 'array', 'items': hypothesis},
        'abstain': {'type': 'boolean'},
    }, ())
    payload = {
        'task': 'Propose bounded local syntax. Return exactly one JSON object conforming to response_schema; no markdown or explanation.',
        'response_schema': schema,
        'reply_rules': [
            'Return {"hypotheses": [...]} or {"abstain": true}. Never abstain with hypotheses.',
            'Every hypothesis must have its own nonempty local_id, nodes, and nonempty alignment. local_id is a local label, not a canonical memory ID.',
            'alignment contains supplied token IDs covering this hypothesis; every node anchor_spans is a nonempty subset of alignment. Use token IDs, never token text or character offsets.',
            'Nodes have no id field. Edge from/to are zero-based INTEGER positions in that hypothesis nodes array, not local_id strings or token IDs.',
            'For ARGUMENT/ATTITUDE/QUERY_SLOT, role_id is REQUIRED and must be a non-null supplied role. Never use null or omit it. For ARGUMENT/ATTITUDE, from is a PREDICATE and to is an ENTITY/proposition; ATTITUDE targets a proposition.',
            'OPERAND edges run from an operator to its operands. Preserve their syntactic order. Unary NOT/POSSIBLE/NECESSARY have one operand; AND/OR/XOR have at least two; IMPLIES/COUNTERFACTUAL/ASSOCIATION have two.',
            'FORALL/EXISTS operands are [BOUND_VAR, proposition body]. Numeric scope operands are [BOUND_VAR, proposition body, NUMERAL]. BIND connects BOUND_VAR to its body ENTITY argument.',
            'TIME_SCOPE runs from a proposition to an anchored TIME. BEFORE/AFTER/DURING operands are TIME or proposition nodes. TIME/NUMERAL carry raw anchors only; never supply model-generated numeric values.',
            'QUERY_SLOT runs from PREDICATE to WH/COUNT_REQUEST and uses a registered role_id.',
            'head_anchor is ONLY for PREDICATE/ENTITY. On operators, TIME, WH, COUNT_REQUEST, BOUND_VAR and NUMERAL omit head_anchor or use null; never supply a token ID there. For multi-token PREDICATE/ENTITY, head_anchor is required and must be from its own anchor_spans. feature_refs must name declared token hypotheses; otherwise omit it or use [].',
            'Keep the graph acyclic and within the supplied budgets. Preserve every required_operators scope. Never add fields, canonical IDs or invented roles.',
            'Propose only positively supported structures. Preserve genuine alternative readings or abstain when no grounded structure can be supplied.',
        ],
        'request': asdict(req),
        'tokens': tokens,
    }
    return json.dumps(payload, ensure_ascii=False,
                      default=lambda x: sorted(x) if isinstance(x, (set, frozenset)) else str(x))


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

    for ni, node in enumerate(hyp.nodes):
        # (c) node kind allowlist
        if req.allowed_node_kinds and node.kind not in req.allowed_node_kinds:
            raise ProtocolError(f"hypothesis {hyp.local_id}: node kind {node.kind!r} not allowed")
        # (b) bounded region: every anchor span must lie inside the declared local region
        for span in node.anchor_spans:
            if span not in src or span not in hyp.alignment:
                raise ProtocolError(
                    f"hypothesis {hyp.local_id}: anchor span {span!r} outside the bounded region")
        if node.head_anchor is not None:
            if node.kind not in {'PREDICATE','ENTITY'}:
                raise ProtocolError(f'hypothesis {hyp.local_id}: node[{ni}] kind={node.kind} forbids head_anchor')
            if not isinstance(node.head_anchor,str) or node.head_anchor not in node.anchor_spans:
                raise ProtocolError(f'hypothesis {hyp.local_id}: node[{ni}] lexical head is outside its own anchors')
        if node.kind in {'PREDICATE','ENTITY'} and len(node.anchor_spans)>1 and node.head_anchor is None:
            raise ProtocolError('multi-head lexical unit requires an explicit morphological head')

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
        proposition = b in PROPOSITION_NODE_KINDS
        if edge.kind in {'ARGUMENT','ATTITUDE','QUERY_SLOT'} and not edge.role_id:
            raise ProtocolError(f'hypothesis {hyp.local_id}: {edge.kind} requires a non-null registered role_id')
        if edge.kind in {'ARGUMENT','ATTITUDE'} and (a!='PREDICATE' or b!='ENTITY' and not proposition or not edge.role_id):
            raise ProtocolError('invalid typed argument edge')
        if edge.kind=='ATTITUDE' and not proposition:
            raise ProtocolError('attitude target must be a proposition')
        if edge.kind=='BIND' and (a!='BOUND_VAR' or b!='ENTITY'):
            raise ProtocolError('invalid bound-variable edge')
        if edge.kind=='TIME_SCOPE' and (a not in PROPOSITION_NODE_KINDS or b!='TIME'):
            raise ProtocolError('temporal scope requires proposition -> anchored TIME')
        if edge.kind=='QUERY_SLOT' and (a!='PREDICATE' or b not in {'WH','COUNT_REQUEST'} or not edge.role_id):
            raise ProtocolError('query slot requires predicate -> anchored interrogative and a registered role')
        if edge.kind=='OPERAND' and (a in {'PREDICATE','ENTITY','BOUND_VAR','TIME','NUMERAL'} or b=='ENTITY'):
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

    proposition_roles=set()
    temporal_owners=set()
    for edge in hyp.edges:
        if edge.kind=='TIME_SCOPE':
            if edge.from_idx in temporal_owners: raise ProtocolError('temporal scope is not unique')
            temporal_owners.add(edge.from_idx)
        if edge.kind not in {'ARGUMENT','ATTITUDE'} or hyp.nodes[edge.to_idx].kind not in PROPOSITION_NODE_KINDS: continue
        slot=(edge.from_idx,edge.role_id)
        if slot in proposition_roles: raise ProtocolError('proposition argument cardinality not closed')
        proposition_roles.add(slot)

    arities={'NOT':(1,1),'POSSIBLE':(1,1),'NECESSARY':(1,1),
             'AND':(2,None),'OR':(2,None),'XOR':(2,None),
             'IMPLIES':(2,2),'COUNTERFACTUAL':(2,2),'ASSOCIATION':(2,2),
             'FORALL':(2,2),'EXISTS':(2,2),'BEFORE':(2,2),'AFTER':(2,2),'DURING':(2,2),
             'AT_LEAST_N':(3,3),'EXACTLY_N':(3,3),'AT_MOST_N':(3,3)}
    for idx,node in enumerate(hyp.nodes):
        operands=[hyp.nodes[e.to_idx] for e in hyp.edges if e.from_idx==idx and e.kind=='OPERAND']
        if node.kind in arities:
            lo,hi=arities[node.kind]
            if len(operands)<lo or hi is not None and len(operands)>hi:
                raise ProtocolError('operator arity mismatch:'+node.kind)
            if node.kind in {'AT_LEAST_N','EXACTLY_N','AT_MOST_N'}:
                if operands[0].kind!='BOUND_VAR' or operands[1].kind not in PROPOSITION_NODE_KINDS or operands[2].kind!='NUMERAL':
                    raise ProtocolError('numeric scope requires [bound_var, body, numeral]')
            elif node.kind in {'FORALL','EXISTS'}:
                if operands[0].kind!='BOUND_VAR' or operands[1].kind not in PROPOSITION_NODE_KINDS:
                    raise ProtocolError('quantifier requires [bound_var, body]')
            elif node.kind in {'BEFORE','AFTER','DURING'}:
                if any(x.kind!='TIME' and x.kind not in PROPOSITION_NODE_KINDS for x in operands):
                    raise ProtocolError('temporal operator requires typed time/proposition operands')
            elif any(x.kind=='BOUND_VAR' for x in operands):
                raise ProtocolError('bound_var outside quantifier slot')
            elif any(x.kind not in PROPOSITION_NODE_KINDS for x in operands):
                raise ProtocolError('operator requires proposition operands')

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
        # Same transport-only normalization as bounded selection. Do not search
        # for JSON inside prose or accept extra/malformed semantic fields.
        data = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"malformed TP reply JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("TP reply must be a JSON object")

    def fields(obj,allowed,required=(),path='$'):
        if not isinstance(obj,dict):
            raise ProtocolError(f"unknown/missing TP fields at {path}: expected object")
        missing=sorted(set(required)-set(obj)); unknown=sorted(set(obj)-set(allowed))
        if missing or unknown:
            raise ProtocolError(f"unknown/missing TP fields at {path}: missing={missing}, unknown={unknown}")
    fields(data,{"hypotheses","abstain"})
    if not isinstance(data.get("abstain",False),bool) or not isinstance(data.get("hypotheses",[]),list):
        raise ProtocolError("invalid TP scalar/list type")
    hyps=[]
    try:
        for hi,h in enumerate(data.get("hypotheses",[])):
            path=f'$.hypotheses[{hi}]'
            fields(h,{"local_id","nodes","edges","alternatives","alignment"},{"local_id","nodes","alignment"},path)
            nodes=[]; edges=[]
            for ni,v in enumerate(h["nodes"]):
                fields(v,{"kind","anchor_spans","feature_refs","head_anchor"},{"kind","anchor_spans"},f'{path}.nodes[{ni}]')
                if not isinstance(v["anchor_spans"],list) or not all(isinstance(x,str) for x in v["anchor_spans"]):
                    raise ProtocolError("anchor_spans must be a list of source ids")
                nodes.append(TNode(v["kind"],tuple(v["anchor_spans"]),tuple(v.get("feature_refs",())),v.get('head_anchor')))
            for ei,e in enumerate(h.get("edges",[])):
                fields(e,{"kind","from","to","role_id","scope"},{"kind","from","to"},f'{path}.edges[{ei}]')
                if type(e["from"]) is not int or type(e["to"]) is not int or type(e.get("scope",False)) is not bool:
                    raise ProtocolError("invalid TP endpoint/scope type")
                edges.append(TEdge(e["kind"],e["from"],e["to"],e.get("role_id"),e.get("scope",False)))
            if type(h.get("alternatives",1)) is not int or not isinstance(h["alignment"],list):
                raise ProtocolError("invalid alternative/alignment type")
            hyps.append(Hypothesis(h["local_id"],tuple(nodes),tuple(edges),h.get("alternatives",1),tuple(h["alignment"])))
    except (KeyError,TypeError,ValueError) as exc:
        raise ProtocolError("malformed TP hypothesis") from exc
    return validate_structure_reply(req,StructureProposalReply(tuple(hyps),data.get("abstain",False)))
