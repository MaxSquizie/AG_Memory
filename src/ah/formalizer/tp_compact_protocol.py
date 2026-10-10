"""TP-C1: indexed local syntax proposals without model-generated JSON.

The model supplies only request-local selections and attachments.  The codec
expands them into the *existing* Hypothesis representation and runs the same
deterministic validator before downstream code can use anything.  This is an
explicit protocol, never an auto-detected fallback for a malformed JSON reply.
The JSON in the input prompt is produced by code, not by the provider.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import re

from .selection_protocol import ProtocolError
from .tp_proposer import (
    Hypothesis, StructureProposalReply, StructureProposalRequest, TEdge, TNode,
    build_structure_prompt, validate_structure_reply,
)

COMPACT_TP_PROTOCOL = "TP-C1"
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z", re.ASCII)
_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)


def compact_structure_catalog(req: StructureProposalRequest) -> dict:
    """Return a stable, request-local, exhaustive reference dictionary."""
    features = [str(getattr(t, "hypothesis_id", t)) for t in req.token_hypotheses]
    if len(set(req.source_spans)) != len(req.source_spans):
        raise ProtocolError("TP-C1 request has duplicate source ids")
    if len(set(features)) != len(features):
        raise ProtocolError("TP-C1 request has duplicate feature ids")
    if not req.allowed_node_kinds or not req.allowed_edge_kinds:
        raise ProtocolError("TP-C1 requires explicit node and edge catalogs")
    return {
        "node_kinds": {"K" + str(i): value for i, value in enumerate(sorted(req.allowed_node_kinds))},
        "edge_kinds": {"E" + str(i): value for i, value in enumerate(sorted(req.allowed_edge_kinds))},
        "roles": {"R" + str(i): value for i, value in enumerate(sorted(req.allowed_role_ids))},
        "tokens": list(req.source_spans),
        "features": features,
    }


def build_compact_structure_prompt(req: StructureProposalRequest, tokens: list[dict]) -> str:
    """Publish the complete bounded request; ask only for indexed TP-C1 lines.

    Evidence is not pruned or replaced by a preselected semantic answer.  The
    original semantic rules are retained and apply after deterministic expansion.
    Replacing the verbose JSON response schema changes the wire, not the graph.
    """
    catalog = compact_structure_catalog(req)
    legacy = json.loads(build_structure_prompt(req, tokens))
    payload = {
        "protocol": COMPACT_TP_PROTOCOL,
        "catalog": catalog,
        "expanded_structure_rules": legacy["reply_rules"][2:],
        "request": asdict(req),
        "tokens": tokens,
    }
    instructions = """Propose bounded local syntax. Reply in TP-C1 only: no JSON, markdown, or explanation.
Output a single - to abstain, otherwise one or more complete hypothesis blocks:
H label token_indices [Acount]
N node_kind_code anchor_indices [@head_index] [^feature_indices]
E edge_kind_code from_node_index to_node_index [/role_code] [!]
.
Each record is one line. H opens a hypothesis, . closes it. Put all N lines before E lines. Node indices are their zero-based order within the block. Each hypothesis has a distinct short ASCII label (for example h0); labels are local, not memory IDs. There are no node IDs to generate.
Lists are comma-separated zero-based indices, for example 0,2,3. Token indices refer to catalog.tokens; feature indices refer to catalog.features. Kind and role codes refer to the supplied dictionaries. Do not output raw token IDs, token text, canonical IDs, undeclared codes, or new roles.
H token_indices is the nonempty alignment. N anchor_indices is nonempty and contained in that alignment. Acount represents alternatives (default 1); @head_index is the lexical head (default absent); ^feature_indices selects declared morphological hypotheses (default empty). Optional fields appear once, in the shown order. Preserve genuine alternatives, nodes, edges, features, heads and scope: never omit information to shorten the answer.
E /role_code is required for ARGUMENT, ATTITUDE and QUERY_SLOT; ! means scope=true (default false). OPERAND edge order is syntactic operand order, including [BOUND_VAR, body] and [BOUND_VAR, body, NUMERAL]. Follow all expanded_structure_rules below: those field names describe the deterministic expansion of these lines, not fields you should generate.
Use only positively supported structures; abstain when none is grounded. Preserve incompatible supported readings as separate hypothesis blocks.
The following input JSON, including all evidence and resource snapshot pins, is produced by code:
"""
    return instructions + json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
        default=lambda value: sorted(value) if isinstance(value, (set, frozenset)) else str(value))


def _index(raw: str, count: int, context: str) -> int:
    if not _INTEGER.fullmatch(raw):
        raise ProtocolError(f"TP-C1 invalid {context} index")
    # Reject unbounded decimal input before Python's integer conversion limit;
    # a protocol failure must not escape as an unrelated ValueError.
    if len(raw) > len(str(max(count - 1, 0))):
        raise ProtocolError(f"TP-C1 {context} index outside catalog")
    value = int(raw)
    if not 0 <= value < count:
        raise ProtocolError(f"TP-C1 {context} index outside catalog")
    return value


def _list(raw: str, values: list[str], context: str) -> tuple[str, ...]:
    indices = raw.split(",")
    if not raw or any(not index for index in indices):
        raise ProtocolError(f"TP-C1 empty {context} list")
    result = tuple(values[_index(index, len(values), context)] for index in indices)
    if len(set(result)) != len(result):
        raise ProtocolError(f"TP-C1 duplicate {context} reference")
    return result


def _lookup(catalog: dict, code: str, context: str) -> str:
    if code not in catalog:
        raise ProtocolError(f"TP-C1 undeclared {context} code {code!r}")
    return catalog[code]


def parse_compact_structure_reply(req: StructureProposalRequest, raw: str | None) -> list[Hypothesis]:
    """Expand TP-C1 selections, then validate the unchanged hypothesis contract.

    There is no JSON/prose/fence search, invented attachment or repair.  A missing
    reply remains an explicit miss.  Every complete returned reading is retained.
    """
    if raw is None:
        return []
    if not isinstance(raw, str) or not raw.strip():
        raise ProtocolError("TP-C1 empty or nontext reply")
    if not raw.isascii():
        raise ProtocolError("TP-C1 reply must use ASCII references")
    catalog = compact_structure_catalog(req)
    if raw.strip() == "-":
        return validate_structure_reply(req, StructureProposalReply(abstain=True))
    hypotheses = []
    current = None
    seen_labels = set()
    edges_started = False
    for line_number, line in enumerate(raw.strip().splitlines(), 1):
        fields = line.split()
        if not fields:
            raise ProtocolError(f"TP-C1 empty record at line {line_number}")
        tag = fields[0]
        if tag == "H":
            if current is not None or len(fields) not in {3, 4}:
                raise ProtocolError("TP-C1 malformed or nested hypothesis header")
            label = fields[1]
            if not _LABEL.fullmatch(label) or label in seen_labels:
                raise ProtocolError("TP-C1 invalid or duplicate hypothesis label")
            alternatives = 1
            if len(fields) == 4:
                if not fields[3].startswith("A") or not _INTEGER.fullmatch(fields[3][1:]):
                    raise ProtocolError("TP-C1 invalid alternatives field")
                try:
                    alternatives = int(fields[3][1:])
                except ValueError as exc:
                    raise ProtocolError("TP-C1 alternatives field exceeds integer decoding limit") from exc
                if alternatives < 1:
                    raise ProtocolError("TP-C1 invalid alternatives count")
            seen_labels.add(label)
            current = {"label": label, "alignment": _list(fields[2], catalog["tokens"], "alignment"),
                       "alternatives": alternatives, "nodes": [], "edges": []}
            edges_started = False
        elif tag == "N":
            if current is None or edges_started or not 3 <= len(fields) <= 5:
                raise ProtocolError("TP-C1 misplaced or malformed node record")
            kind = _lookup(catalog["node_kinds"], fields[1], "node kind")
            anchors = _list(fields[2], catalog["tokens"], "anchor")
            head = None
            features = ()
            optional = fields[3:]
            if optional and optional[0].startswith("@"):
                head = catalog["tokens"][_index(optional.pop(0)[1:], len(catalog["tokens"]), "head")]
            if optional and optional[0].startswith("^"):
                features = _list(optional.pop(0)[1:], catalog["features"], "feature")
            if optional:
                raise ProtocolError("TP-C1 duplicate, unknown or unordered node option")
            current["nodes"].append(TNode(kind, anchors, features, head))
            if len(current["nodes"]) > req.max_nodes:
                raise ProtocolError("PROPOSAL_BUDGET: nodes")
        elif tag == "E":
            if current is None or not 4 <= len(fields) <= 6:
                raise ProtocolError("TP-C1 misplaced or malformed edge record")
            edges_started = True
            kind = _lookup(catalog["edge_kinds"], fields[1], "edge kind")
            count = len(current["nodes"])
            from_idx = _index(fields[2], count, "node endpoint")
            to_idx = _index(fields[3], count, "node endpoint")
            role = None
            scope = False
            optional = fields[4:]
            if optional and optional[0].startswith("/"):
                role = _lookup(catalog["roles"], optional.pop(0)[1:], "role")
            if optional and optional[0] == "!":
                scope = True
                optional.pop(0)
            if optional:
                raise ProtocolError("TP-C1 duplicate, unknown or unordered edge option")
            current["edges"].append(TEdge(kind, from_idx, to_idx, role, scope))
            if len(current["edges"]) > req.max_edges:
                raise ProtocolError("PROPOSAL_BUDGET: edges")
        elif tag == ".":
            if current is None or len(fields) != 1:
                raise ProtocolError("TP-C1 misplaced hypothesis terminator")
            hypotheses.append(Hypothesis(current["label"], tuple(current["nodes"]),
                tuple(current["edges"]), current["alternatives"], current["alignment"]))
            current = None
        else:
            raise ProtocolError(f"TP-C1 unexpected record at line {line_number}")
    if current is not None or not hypotheses:
        raise ProtocolError("TP-C1 unterminated or missing hypothesis")
    return validate_structure_reply(req, StructureProposalReply(tuple(hypotheses)))


def serialize_compact_structure_reply(req: StructureProposalRequest,
                                     hypotheses: list[Hypothesis] | tuple[Hypothesis, ...]) -> str:
    """Code-owned formatter for fixtures and offline equivalence verification.

    It does not call a provider and is never a JSON fallback in live execution.
    """
    accepted = validate_structure_reply(req, StructureProposalReply(tuple(hypotheses)))
    if not accepted:
        return "-"
    catalog = compact_structure_catalog(req)
    kinds = {value: code for code, value in catalog["node_kinds"].items()}
    edge_kinds = {value: code for code, value in catalog["edge_kinds"].items()}
    roles = {value: code for code, value in catalog["roles"].items()}
    tokens = {value: index for index, value in enumerate(catalog["tokens"])}
    features = {value: index for index, value in enumerate(catalog["features"])}
    def indices(values, lookup):
        return ",".join(str(lookup[value]) for value in values)
    lines = []
    for hyp in accepted:
        if not _LABEL.fullmatch(hyp.local_id):
            raise ProtocolError("TP-C1 requires a short ASCII local hypothesis label")
        line = f"H {hyp.local_id} {indices(hyp.alignment, tokens)}"
        if hyp.alternatives != 1:
            line += " A" + str(hyp.alternatives)
        lines.append(line)
        for node in hyp.nodes:
            line = f"N {kinds[node.kind]} {indices(node.anchor_spans, tokens)}"
            if node.head_anchor is not None:
                line += " @" + str(tokens[node.head_anchor])
            if node.feature_refs:
                line += " ^" + indices(node.feature_refs, features)
            lines.append(line)
        for edge in hyp.edges:
            line = f"E {edge_kinds[edge.kind]} {edge.from_idx} {edge.to_idx}"
            if edge.role_id is not None:
                line += " /" + roles[edge.role_id]
            if edge.scope:
                line += " !"
            lines.append(line)
        lines.append(".")
    result = "\n".join(lines)
    # Formatting must never discard a field or produce a subtly different graph.
    if parse_compact_structure_reply(req, result) != accepted:
        raise ProtocolError("TP-C1 formatter changed a validated hypothesis")
    return result
