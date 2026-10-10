"""TP-C1 changes serialization, never the typed local proposal contract."""
from dataclasses import asdict, replace
import json

import pytest

from ah.formalizer.selection_protocol import ProtocolError
from ah.formalizer.tp_compact_protocol import (
    build_compact_structure_prompt, compact_structure_catalog,
    parse_compact_structure_reply, serialize_compact_structure_reply,
)
from ah.formalizer.tp_proposer import (
    Hypothesis, StructureProposalRequest, TEdge, TNode, parse_and_validate,
)


NODE_KINDS = frozenset({
    'PREDICATE', 'ENTITY', 'BOUND_VAR', 'TIME', 'WH', 'COUNT_REQUEST', 'NUMERAL',
    'NOT', 'AND', 'OR', 'XOR', 'IMPLIES', 'FORALL', 'EXISTS', 'POSSIBLE',
    'NECESSARY', 'COUNTERFACTUAL', 'BEFORE', 'AFTER', 'DURING', 'ASSOCIATION',
    'AT_LEAST_N', 'EXACTLY_N', 'AT_MOST_N',
})
EDGE_KINDS = frozenset({'ARGUMENT', 'ATTITUDE', 'OPERAND', 'BIND', 'TIME_SCOPE', 'QUERY_SLOT'})


def request(**kwargs):
    values = dict(token_hypotheses=('morph:declared-feature-0', 'morph:declared-feature-1'),
        allowed_node_kinds=NODE_KINDS, allowed_edge_kinds=EDGE_KINDS,
        allowed_role_ids=frozenset({'SUBJECT', 'OBJECT', 'EXPERIENCER', 'SURFACE_ARG'}),
        max_nodes=64, max_edges=128, max_depth=16)
    values.update(kwargs)
    return StructureProposalRequest('TP:bounded-fixture', 'pre-seal-hash',
        tuple('raw:source:revision:token:' + str(i) for i in range(12)), **values)


def node(req, kind, i, **kwargs):
    return TNode(kind, (req.source_spans[i],), **kwargs)


def simple(req):
    return Hypothesis('h0', (node(req, 'PREDICATE', 1), node(req, 'ENTITY', 0)),
        (TEdge('ARGUMENT', 0, 1, 'SUBJECT'),), alignment=req.source_spans[:2])


def legacy_wire(hypotheses):
    data = {'hypotheses': []}
    for hyp in hypotheses:
        result = asdict(hyp)
        result['edges'] = [dict(kind=e.kind, **{'from': e.from_idx, 'to': e.to_idx},
                                role_id=e.role_id, scope=e.scope) for e in hyp.edges]
        data['hypotheses'].append(result)
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def test_code_owned_compact_format_expands_into_identical_validated_hypotheses():
    req = request()
    first = Hypothesis('h0', (
        node(req, 'NOT', 0),
        TNode('PREDICATE', req.source_spans[1:3], req.token_hypotheses, req.source_spans[2]),
        node(req, 'ENTITY', 3), node(req, 'TIME', 4)),
        (TEdge('OPERAND', 0, 1, scope=True), TEdge('ARGUMENT', 1, 2, 'SUBJECT'),
         TEdge('TIME_SCOPE', 0, 3)), alternatives=2, alignment=req.source_spans[:5])
    second = replace(simple(req), local_id='h1')
    gold = [first, second]
    json_reply = legacy_wire(gold)
    compact_reply = serialize_compact_structure_reply(req, gold)
    assert parse_compact_structure_reply(req, compact_reply) == parse_and_validate(req, json_reply) == gold
    assert json.loads(json_reply)['hypotheses'][0]['alternatives'] == 2
    assert '@2 ^0,1' in compact_reply and ' !' in compact_reply and ' A2' in compact_reply
    assert len(compact_reply) < len(json_reply) / 3
    assert all(source not in compact_reply for source in req.source_spans)


def test_prompt_retains_every_evidence_field_and_indexes_references_instead_of_inventing_them():
    evidence = {'status': 'COMPLETE', 'resource_snapshot': {'release_sha256': 'fixed-hash'},
        'valency_alternatives': [{'anchor_refs': ['raw:source:revision:token:1'],
            'roles': [{'role_id': 'OBJECT', 'argument_types': ['PROPOSITION']}]}]}
    req = request(released_slot_evidence=evidence, required_operators=(('NOT',
        ('raw:source:revision:token:0',)),), speech_act_metadata={'query_form': 'BOOLEAN'})
    tokens = [{'id': req.source_spans[0], 'text': 'не'},
              {'id': req.source_spans[1], 'text': 'слово с пробелами'}]
    prompt = build_compact_structure_prompt(req, tokens)
    payload = json.loads(prompt.split('produced by code:\n', 1)[1])
    assert payload['protocol'] == 'TP-C1'
    assert payload['tokens'] == tokens
    assert payload['request']['released_slot_evidence'] == evidence
    assert payload['request']['required_operators'] == [['NOT', [req.source_spans[0]]]]
    assert payload['request']['speech_act_metadata'] == req.speech_act_metadata
    assert payload['catalog']['tokens'] == list(req.source_spans)
    assert set(payload['catalog']['node_kinds'].values()) == req.allowed_node_kinds
    assert set(payload['catalog']['roles'].values()) == req.allowed_role_ids
    assert 'response_schema' not in payload
    assert 'no JSON, markdown, or explanation' in prompt


@pytest.mark.parametrize('kind', ['NOT', 'POSSIBLE', 'NECESSARY'])
def test_every_unary_operator_keeps_operand_scope_and_required_trigger(kind):
    req = request(required_operators=((kind, ('raw:source:revision:token:0',)),))
    hyp = Hypothesis('h0', (node(req, kind, 0), node(req, 'PREDICATE', 1)),
        (TEdge('OPERAND', 0, 1, scope=True),), alignment=req.source_spans[:2])
    assert parse_compact_structure_reply(req, serialize_compact_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind', ['AND', 'OR', 'XOR', 'IMPLIES', 'COUNTERFACTUAL', 'ASSOCIATION'])
def test_binary_and_nary_operators_preserve_syntactic_operand_order(kind):
    req = request()
    hyp = Hypothesis('h0', (node(req, kind, 0), node(req, 'PREDICATE', 1),
        node(req, 'PREDICATE', 2)), (TEdge('OPERAND', 0, 2), TEdge('OPERAND', 0, 1)),
        alignment=req.source_spans[:3])
    assert parse_compact_structure_reply(req, serialize_compact_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind', ['FORALL', 'EXISTS', 'AT_LEAST_N', 'EXACTLY_N', 'AT_MOST_N'])
def test_quantifiers_numeric_scope_and_binding_are_representable(kind):
    req = request()
    nodes = [node(req, kind, 0), node(req, 'BOUND_VAR', 1), node(req, 'PREDICATE', 2),
             node(req, 'ENTITY', 3)]
    edges = [TEdge('OPERAND', 0, 1), TEdge('OPERAND', 0, 2),
             TEdge('ARGUMENT', 2, 3, 'SUBJECT'), TEdge('BIND', 1, 3)]
    if kind not in {'FORALL', 'EXISTS'}:
        nodes.append(node(req, 'NUMERAL', 4)); edges.append(TEdge('OPERAND', 0, 4))
    hyp = Hypothesis('h0', tuple(nodes), tuple(edges), alignment=req.source_spans[:len(nodes)])
    assert parse_compact_structure_reply(req, serialize_compact_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind', ['BEFORE', 'AFTER', 'DURING'])
def test_temporal_order_operands_are_anchors_not_generated_dates(kind):
    req = request()
    hyp = Hypothesis('h0', (node(req, kind, 0), node(req, 'TIME', 1), node(req, 'PREDICATE', 2)),
        (TEdge('OPERAND', 0, 1), TEdge('OPERAND', 0, 2)), alignment=req.source_spans[:3])
    assert parse_compact_structure_reply(req, serialize_compact_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind,target,role', [
    ('ATTITUDE', 'PREDICATE', 'OBJECT'), ('QUERY_SLOT', 'WH', 'SUBJECT'),
    ('QUERY_SLOT', 'COUNT_REQUEST', 'OBJECT'), ('ARGUMENT', 'ENTITY', 'SURFACE_ARG'),
])
def test_proposition_content_questions_and_surface_attachments_keep_declared_roles(kind, target, role):
    req = request()
    hyp = Hypothesis('h0', (node(req, 'PREDICATE', 0), node(req, target, 1)),
        (TEdge(kind, 0, 1, role),), alignment=req.source_spans[:2])
    assert parse_compact_structure_reply(req, serialize_compact_structure_reply(req, [hyp])) == [hyp]


def codes(req):
    catalog = compact_structure_catalog(req)
    return tuple({v: k for k, v in catalog[group].items()} for group in ('node_kinds', 'edge_kinds', 'roles'))


@pytest.mark.parametrize('damage', [
    'json', 'fence', 'prose', 'missing_end', 'node_after_edge', 'foreign_kind', 'foreign_role',
    'foreign_token', 'foreign_feature', 'foreign_head', 'negative_endpoint', 'duplicate_label',
    'duplicate_alignment', 'duplicate_anchor', 'duplicate_feature', 'duplicate_head',
    'duplicate_scope', 'missing_role', 'empty_node', 'unknown_option', 'abstain_plus_graph',
])
def test_malformed_or_unbound_wire_fails_closed_without_repair(damage):
    req = request()
    valid = serialize_compact_structure_reply(req, [simple(req)])
    kind, edge, role = codes(req)
    invalid = {
        'json': legacy_wire([simple(req)]), 'fence': '```\n' + valid + '\n```',
        'prose': 'Here is the structure:\n' + valid, 'missing_end': valid.rsplit('\n', 1)[0],
        'node_after_edge': valid.replace('\n.', '\nN ' + kind['ENTITY'] + ' 2\n.'),
        'foreign_kind': valid.replace('N ' + kind['PREDICATE'], 'N K999'),
        'foreign_role': valid.replace('/' + role['SUBJECT'], '/R999'),
        'foreign_token': valid.replace('H h0 0,1', 'H h0 0,999'),
        'foreign_feature': valid.replace('N ' + kind['PREDICATE'] + ' 1', 'N ' + kind['PREDICATE'] + ' 1 ^99'),
        'foreign_head': valid.replace('N ' + kind['PREDICATE'] + ' 1', 'N ' + kind['PREDICATE'] + ' 1 @99'),
        'negative_endpoint': valid.replace(' 0 1 /', ' -1 1 /'),
        'duplicate_label': valid + '\n' + valid,
        'duplicate_alignment': valid.replace('H h0 0,1', 'H h0 0,1,1'),
        'duplicate_anchor': valid.replace('N ' + kind['PREDICATE'] + ' 1', 'N ' + kind['PREDICATE'] + ' 1,1'),
        'duplicate_feature': valid.replace('N ' + kind['PREDICATE'] + ' 1', 'N ' + kind['PREDICATE'] + ' 1 ^0,0'),
        'duplicate_head': valid.replace('N ' + kind['PREDICATE'] + ' 1', 'N ' + kind['PREDICATE'] + ' 1 @1 @1'),
        'duplicate_scope': valid.replace('\n.', ' ! !\n.'),
        'missing_role': valid.replace(' /' + role['SUBJECT'], ''),
        'empty_node': 'H h0 0,1\n.',
        'unknown_option': valid.replace('\n.', ' repair=yes\n.'),
        'abstain_plus_graph': '-\n' + valid,
    }[damage]
    with pytest.raises(ProtocolError):
        parse_compact_structure_reply(req, invalid)


def test_compact_decoder_runs_existing_cycle_arity_head_alignment_scope_and_budget_checks():
    req = request()
    kind, edge, role = codes(req)
    samples = [
        # Two proposition nodes may not mutually depend on each other.
        f'H h0 0,1\nN {kind["PREDICATE"]} 0\nN {kind["PREDICATE"]} 1\n'
        f'E {edge["ARGUMENT"]} 0 1 /{role["OBJECT"]}\nE {edge["ARGUMENT"]} 1 0 /{role["OBJECT"]}\n.',
        f'H h0 0\nN {kind["NOT"]} 0\n.',
        f'H h0 0,1\nN {kind["PREDICATE"]} 0,1\n.',
        f'H h0 0\nN {kind["PREDICATE"]} 1\n.',
        f'H h0 0\nN {kind["TIME"]} 0 @0\n.',
    ]
    for raw in samples:
        with pytest.raises(ProtocolError):
            parse_compact_structure_reply(req, raw)
    with pytest.raises(ProtocolError, match='source operator scope silently lost'):
        parse_compact_structure_reply(replace(req, required_operators=(('NOT', (req.source_spans[0],)),)),
                                      serialize_compact_structure_reply(req, [simple(req)]))
    with pytest.raises(ProtocolError, match='PROPOSAL_BUDGET'):
        parse_compact_structure_reply(replace(req, max_nodes=1), serialize_compact_structure_reply(req, [simple(req)]))
    assert parse_compact_structure_reply(req, '-') == []
    assert parse_compact_structure_reply(req, None) == []
    with pytest.raises(ProtocolError, match='budget pre-check'):
        parse_compact_structure_reply(replace(req, budget_ok=False), '-')


def test_catalog_is_order_independent_and_bound_to_exact_request_ids():
    req = request()
    same = replace(req, allowed_node_kinds=frozenset(reversed(sorted(req.allowed_node_kinds))))
    assert compact_structure_catalog(req) == compact_structure_catalog(same)
    with pytest.raises(ProtocolError, match='duplicate source'):
        compact_structure_catalog(replace(req, source_spans=(req.source_spans[0],) * 2))
    with pytest.raises(ProtocolError, match='duplicate feature'):
        compact_structure_catalog(replace(req, token_hypotheses=('feature', 'feature')))
