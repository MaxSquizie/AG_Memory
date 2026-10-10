"""TP-C2: readable indexed local proposals, with disjoint reference spaces.

Only the wire changes: code expands every field to the existing Hypothesis
contract and validates it before any structural use.  JSON in the input is
code-owned evidence.  Output is a strict line protocol, with no JSON fallback,
guessing, repair, dropped alternatives or sentence-specific machinery.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import re
import unicodedata
from urllib.parse import quote

from .canonical_ledger import digest
from .selection_protocol import ProtocolError
from .tp_proposer import (
    Hypothesis, StructureProposalReply, StructureProposalRequest, TEdge, TNode,
    validate_structure_reply,
)

READABLE_TP_PROTOCOL = "TP-C2"
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z", re.ASCII)
_NUMBER = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)


def _features(req):
    return [str(getattr(value, "hypothesis_id", value)) for value in req.token_hypotheses]


def _role_tokens(req):
    """Registered names stay readable; whitespace/control roles have exact tokens.

    This is a closed request-local table, not permissive percent decoding: only
    its exact keys can occur on the wire. Escaping '%' also prevents collisions
    between an escaped role and a literal percent-containing registered name.
    """
    result = {}
    for role in sorted(req.allowed_role_ids):
        encode = any(c.isspace() or unicodedata.category(c).startswith("C") or c == "%"
                     for c in role)
        token = quote(role, safe="-._~", errors="surrogatepass") if encode else role
        if token in result:
            raise ProtocolError("TP-C2 role token collision")
        result[token] = role
    return result


def readable_structure_catalog(req: StructureProposalRequest) -> dict:
    """Build the complete, deterministic request-local reference space."""
    features = _features(req)
    if len(set(req.source_spans)) != len(req.source_spans):
        raise ProtocolError("TP-C2 request has duplicate source ids")
    if len(set(features)) != len(features):
        raise ProtocolError("TP-C2 request has duplicate feature ids")
    if not req.allowed_node_kinds or not req.allowed_edge_kinds:
        raise ProtocolError("TP-C2 requires explicit node and edge catalogs")
    return {
        "node_kinds": sorted(req.allowed_node_kinds),
        "edge_kinds": sorted(req.allowed_edge_kinds),
        "roles": sorted(req.allowed_role_ids),
        "role_tokens": _role_tokens(req),
        "token_refs": ["t" + str(i) for i in range(len(req.source_spans))],
        "feature_refs": ["f" + str(i) for i in range(len(features))],
    }


_TOKEN_REFERENCE_FIELDS = frozenset({
    "source_spans", "uncovered_spans", "anchor_spans", "anchor_refs", "anchor_ref",
    "alignment", "head_anchor", "head_ref", "token_id", "token_ref",
    "predicate_token_ref", "argument_token_refs", "region_token_refs",
})
_FEATURE_REFERENCE_FIELDS = frozenset({"feature_refs"})
_REFERENCE_KEYED_MAP_FIELDS = frozenset({
    "morph_bindings", "proposed_roles", "bound_arguments", "lexical_units",
})


def _alias_reference(value, aliases):
    if isinstance(value, str):
        return aliases.get(value, value)
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value) if isinstance(value, (set, frozenset)) else value
        return [_alias_reference(item, aliases) for item in items]
    return value


def _alias_evidence(value, tokens, features, *, field=None, token_record=False, feature_record=False):
    """Alias typed references; never guess that identical lexical text is an ID.

    Metadata and opaque extension fields remain intact. Known reference fields
    and token-indexed binding maps are the only aliased paths. In particular a
    TokenHypothesis.span_ref is raw text, not a token ID, and stays unchanged.
    """
    if field in _TOKEN_REFERENCE_FIELDS:
        return _alias_reference(value, tokens)
    if field in _FEATURE_REFERENCE_FIELDS:
        return _alias_reference(value, features)
    if field == "required_operators" and isinstance(value, (list, tuple)):
        return [[kind, _alias_reference(anchors, tokens)] for kind, anchors in value]
    if field == "token_hypotheses" and isinstance(value, (list, tuple)):
        return [_alias_reference(item, features) if isinstance(item, str)
                else _alias_evidence(item, tokens, features, feature_record=True) for item in value]
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            alias = tokens.get(key, key) if field in _REFERENCE_KEYED_MAP_FIELDS else key
            if alias in result:
                raise ProtocolError("TP-C2 evidence key alias collision")
            if token_record and key == "id":
                result[alias] = _alias_reference(item, tokens)
            elif feature_record and key == "hypothesis_id":
                result[alias] = _alias_reference(item, features)
            else:
                result[alias] = _alias_evidence(item, tokens, features, field=key)
        return result
    if isinstance(value, (list, tuple)):
        return [_alias_evidence(item, tokens, features) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_alias_evidence(item, tokens, features) for item in sorted(value)]
    return value


_GRAMMAR = """H label token_refs [alternatives=COUNT]
N nINDEX NODE_KIND token_refs [head=tINDEX] [features=fINDEX,fINDEX]
E EDGE_KIND nFROM nTO [role=ROLE_ID] [scope]
END"""


def build_readable_structure_prompt(req: StructureProposalRequest, tokens: list[dict]) -> str:
    """Keep all captured evidence while separating token and node references."""
    catalog = readable_structure_catalog(req)
    token_aliases = {value: "t" + str(i) for i, value in enumerate(req.source_spans)}
    feature_aliases = {value: "f" + str(i) for i, value in enumerate(_features(req))}
    payload = {
        "protocol": READABLE_TP_PROTOCOL,
        "catalog": catalog,
        "reference_binding_sha256": digest({"tokens": list(req.source_spans), "features": _features(req)}),
        "request": _alias_evidence(asdict(req), token_aliases, feature_aliases),
        "tokens": [_alias_evidence(token, token_aliases, feature_aliases, token_record=True)
                   for token in tokens],
    }
    instructions = """Propose bounded local syntax using the captured input evidence. Return TP-C2 records only: no JSON, prose or markdown.
There are THREE DIFFERENT reference spaces: t0,t1,... name input tokens; f0,f1,... name captured morphological features; n0,n1,... name nodes YOU DECLARE inside one hypothesis. Token t5 is NOT node n5. Every edge endpoint must name an already declared n-node, never a token.
The exact response grammar is:
""" + _GRAMMAR + """
H, N, E and END are literal record keywords. Start every hypothesis with the literal capital H followed by a space; do not start with just its label. Use one record per line. First H, then all N records, then all E records, then END. Node IDs must be declared in exact sequence n0,n1,n2,... without gaps or duplicates. Separate hypotheses have their own node numbering and distinct short ASCII labels.
token_refs is a nonempty comma-separated list such as t0,t2,t3. H lists this reading's alignment; every node's anchors must be contained in it. Use readable NODE_KIND and EDGE_KIND names from catalog, not invented numeric codes. ROLE_ID is an exact key from catalog.role_tokens; ordinary registered names are unchanged. Optional fields are omitted when neutral: alternatives defaults to 1; head is absent; features is empty; edge role is absent where allowed; scope defaults to false. If needed, use the exact prefixes alternatives=, head=, features=, role= and the literal scope, once and in the shown order. Never drop genuine alternatives or nondefault information to shorten output.
FORMAT ONLY demonstration from a SEPARATE synthetic catalog: t0=predicate-placeholder, t1=argument-placeholder, node kinds=[PREDICATE,ENTITY], edge kinds=[ARGUMENT], role_tokens={SUBJECT:SUBJECT}. This catalog is unrelated to the current input:
H format_demo t0,t1
N n0 PREDICATE t0
N n1 ENTITY t1
E ARGUMENT n0 n1 role=SUBJECT
END
The demonstration is a complete example of serialization only; it supplies no interpretation or factual conclusion for the current input. Your response must use the ACTUAL captured token references, node/edge kinds and roles permitted by THIS request's catalog, not the separate synthetic catalog.

STRUCTURAL RULES:
- Propose syntax, attachments and operator scope, never canonical memory IDs, sense identities, timestamps, inferred facts or truth supports. A local proposition node is not a claim that its content is independently true.
- A missing dictionary sense or unknown word alone is NOT a reason to abstain. Unknown predicates may still have a supported anchored PREDICATE structure. Keep compatible unknown/known structural alternatives; downstream code decides semantic coverage. Do not invent a known sense or identity for an unknown unit.
- Every node has raw-token anchors. PREDICATE and ENTITY with multiple anchors require head=tINDEX naming one of their OWN anchors. Other node kinds must not have head. features= may select only catalog feature references.
- ARGUMENT and ATTITUDE run from a PREDICATE to an ENTITY or proposition; ATTITUDE must target a proposition. ARGUMENT, ATTITUDE and QUERY_SLOT require a registered, nonempty ROLE_ID. Use released role names and argument_types for known lexical alternatives. A declared PROPOSITION/EVENT content slot must use its declared role and attitude; SURFACE_ARG is not a substitute for a known content role. For unknown units use only positively supported roles or an anchored SURFACE_ARG proper subregion.
- Preserve every supported scope in request.required_operators. OPERAND goes from the operator to its typed operands. Preserve syntactic operand order. NOT/POSSIBLE/NECESSARY have one proposition operand. AND/OR/XOR have at least two. IMPLIES/COUNTERFACTUAL/ASSOCIATION have two proposition operands. Do not turn an operator's operands into extra asserted facts.
- FORALL/EXISTS operands are [BOUND_VAR, proposition body]. AT_LEAST_N/EXACTLY_N/AT_MOST_N operands are [BOUND_VAR, proposition body, NUMERAL]. BIND connects BOUND_VAR to its body ENTITY. Do not invent bound-variable identities or numeric values: use captured anchors.
- TIME_SCOPE goes from a proposition to an anchored TIME. Each proposition has at most one TIME_SCOPE owner edge. BEFORE/AFTER/DURING have two TIME/proposition operands. Raw temporal triggers do not determine an owner: preserve supported temporal attachment alternatives; do not attach time to the whole sentence by default or generate dates.
- A BOOLEAN/FORMULA query checks a complete proposition: it does not introduce WH/COUNT_REQUEST or QUERY_SLOT. Such a missing-role slot requires positively supported question evidence. QUERY_SLOT goes from PREDICATE to WH/COUNT_REQUEST with a registered role. A connective or complementizer alone does not create a question gap. Preserve supported alternatives for an undetermined query form.
- released_slot_evidence contains all bounded snapshot-pinned resource alternatives, not a selected semantic answer. Keep incompatible lexical/construction alternatives distinct. Maintain proposition-slot cardinality, type constraints, acyclicity and request.max_nodes/max_edges/max_depth. Do not discard a supported reading to make another appear unique.
Return the single literal ABSTAIN only if no positively supported local structure can be supplied. Uncertainty between supported structures requires multiple hypothesis blocks, not ABSTAIN.

The following input JSON is produced by code. Typed token/feature reference fields use t*/f* aliases; the original reference binding is pinned by reference_binding_sha256. Lexical text, opaque metadata, resource hashes and request identity are retained exactly, even if their strings equal a captured reference ID.
EVIDENCE_JSON:
"""
    evidence = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    reminder = """
END OF INPUT. Reply only with complete TP-C2 blocks in this grammar:
""" + _GRAMMAR + """
The FIRST output line must start with the literal H and a space; the LAST line of each block must be END. Edge endpoints use n* nodes; anchors use t* tokens. Otherwise output only ABSTAIN. No explanation.
"""
    return instructions + evidence + reminder


def _reference(raw, prefix, count, context):
    suffix = raw[1:] if raw.startswith(prefix) else ""
    if not _NUMBER.fullmatch(suffix):
        raise ProtocolError(f"TP-C2 invalid {context} reference")
    if len(suffix) > len(str(max(count - 1, 0))):
        raise ProtocolError(f"TP-C2 {context} reference outside catalog")
    index = int(suffix)
    if not 0 <= index < count:
        raise ProtocolError(f"TP-C2 {context} reference outside catalog")
    return index


def _references(raw, prefix, values, context):
    if not raw:
        raise ProtocolError(f"TP-C2 empty {context} list")
    result = tuple(values[_reference(part, prefix, len(values), context)] for part in raw.split(","))
    if len(set(result)) != len(result):
        raise ProtocolError(f"TP-C2 duplicate {context} reference")
    return result


def parse_readable_structure_reply(req: StructureProposalRequest, raw: str | None) -> list[Hypothesis]:
    """Strict TP-C2 expansion followed by the unchanged structural validator."""
    if raw is None:
        return []
    if not isinstance(raw, str) or not raw.strip():
        raise ProtocolError("TP-C2 empty or nontext reply")
    catalog = readable_structure_catalog(req)
    if raw.strip() == "ABSTAIN":
        return validate_structure_reply(req, StructureProposalReply(abstain=True))
    hypotheses = []
    current = None
    labels = set()
    edges_started = False
    source = list(req.source_spans)
    features = _features(req)
    for line_number, line in enumerate(raw.strip().splitlines(), 1):
        fields = line.split()
        if not fields:
            raise ProtocolError(f"TP-C2 empty record at line {line_number}")
        tag = fields[0]
        if tag == "H":
            if current is not None or len(fields) not in {3, 4}:
                raise ProtocolError("TP-C2 malformed or nested hypothesis header")
            label = fields[1]
            if not _LABEL.fullmatch(label) or label in labels:
                raise ProtocolError("TP-C2 invalid or duplicate hypothesis label")
            count = 1
            if len(fields) == 4:
                prefix = "alternatives="
                if not fields[3].startswith(prefix) or not _NUMBER.fullmatch(fields[3][len(prefix):]):
                    raise ProtocolError("TP-C2 invalid alternatives field")
                try:
                    count = int(fields[3][len(prefix):])
                except ValueError as exc:
                    raise ProtocolError("TP-C2 alternatives exceeds integer decoding limit") from exc
                if count < 1:
                    raise ProtocolError("TP-C2 invalid alternatives count")
            labels.add(label)
            current = {"label": label, "alignment": _references(fields[2], "t", source, "alignment"),
                       "alternatives": count, "nodes": [], "edges": []}
            edges_started = False
        elif tag == "N":
            if current is None or edges_started or not 4 <= len(fields) <= 6:
                raise ProtocolError("TP-C2 misplaced or malformed node record")
            if fields[1] != "n" + str(len(current["nodes"])):
                raise ProtocolError("TP-C2 node ids must be distinct and sequential")
            kind = fields[2]
            if kind not in req.allowed_node_kinds:
                raise ProtocolError("TP-C2 undeclared node kind")
            anchors = _references(fields[3], "t", source, "anchor")
            head = None
            feature_refs = ()
            optional = fields[4:]
            if optional and optional[0].startswith("head="):
                head = source[_reference(optional.pop(0)[5:], "t", len(source), "head")]
            if optional and optional[0].startswith("features="):
                feature_refs = _references(optional.pop(0)[9:], "f", features, "feature")
            if optional:
                raise ProtocolError("TP-C2 duplicate, unknown or unordered node option")
            current["nodes"].append(TNode(kind, anchors, feature_refs, head))
            if len(current["nodes"]) > req.max_nodes:
                raise ProtocolError("PROPOSAL_BUDGET: nodes")
        elif tag == "E":
            if current is None or not 4 <= len(fields) <= 6:
                raise ProtocolError("TP-C2 misplaced or malformed edge record")
            edges_started = True
            kind = fields[1]
            if kind not in req.allowed_edge_kinds:
                raise ProtocolError("TP-C2 undeclared edge kind")
            count = len(current["nodes"])
            from_idx = _reference(fields[2], "n", count, "node endpoint")
            to_idx = _reference(fields[3], "n", count, "node endpoint")
            role = None
            scope = False
            optional = fields[4:]
            if optional and optional[0].startswith("role="):
                role_token = optional.pop(0)[5:]
                if role_token not in catalog["role_tokens"]:
                    raise ProtocolError("TP-C2 undeclared role id")
                role = catalog["role_tokens"][role_token]
            if optional and optional[0] == "scope":
                scope = True
                optional.pop(0)
            if optional:
                raise ProtocolError("TP-C2 duplicate, unknown or unordered edge option")
            current["edges"].append(TEdge(kind, from_idx, to_idx, role, scope))
            if len(current["edges"]) > req.max_edges:
                raise ProtocolError("PROPOSAL_BUDGET: edges")
        elif tag == "END":
            if current is None or len(fields) != 1:
                raise ProtocolError("TP-C2 misplaced hypothesis terminator")
            hypotheses.append(Hypothesis(current["label"], tuple(current["nodes"]),
                tuple(current["edges"]), current["alternatives"], current["alignment"]))
            current = None
        else:
            raise ProtocolError(f"TP-C2 unexpected record at line {line_number}")
    if current is not None or not hypotheses:
        raise ProtocolError("TP-C2 unterminated or missing hypothesis")
    return validate_structure_reply(req, StructureProposalReply(tuple(hypotheses)))


def serialize_readable_structure_reply(req: StructureProposalRequest, hypotheses) -> str:
    """Code-owned formatting for fixtures and offline codec proof, never repair."""
    accepted = validate_structure_reply(req, StructureProposalReply(tuple(hypotheses)))
    if not accepted:
        return "ABSTAIN"
    readable_structure_catalog(req)
    source = {value: "t" + str(i) for i, value in enumerate(req.source_spans)}
    features = {value: "f" + str(i) for i, value in enumerate(_features(req))}
    role_tokens = {role: token for token, role in _role_tokens(req).items()}
    def refs(values, mapping):
        return ",".join(mapping[value] for value in values)
    lines = []
    for hyp in accepted:
        if not _LABEL.fullmatch(hyp.local_id):
            raise ProtocolError("TP-C2 requires a short ASCII hypothesis label")
        line = "H " + hyp.local_id + " " + refs(hyp.alignment, source)
        if hyp.alternatives != 1:
            line += " alternatives=" + str(hyp.alternatives)
        lines.append(line)
        for index, node in enumerate(hyp.nodes):
            line = f"N n{index} {node.kind} {refs(node.anchor_spans, source)}"
            if node.head_anchor is not None:
                line += " head=" + source[node.head_anchor]
            if node.feature_refs:
                line += " features=" + refs(node.feature_refs, features)
            lines.append(line)
        for edge in hyp.edges:
            line = f"E {edge.kind} n{edge.from_idx} n{edge.to_idx}"
            if edge.role_id is not None:
                line += " role=" + role_tokens[edge.role_id]
            if edge.scope:
                line += " scope"
            lines.append(line)
        lines.append("END")
    raw = "\n".join(lines)
    if parse_readable_structure_reply(req, raw) != accepted:
        raise ProtocolError("TP-C2 formatter changed a validated hypothesis")
    return raw
