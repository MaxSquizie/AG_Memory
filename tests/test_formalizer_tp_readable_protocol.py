"""Readable TP-C2 preserves fields and rejects unbound/ambiguous references."""
from dataclasses import asdict, replace
import json

import pytest

from ah.formalizer.canonical_ledger import digest
from ah.formalizer.selection_protocol import ProtocolError
from ah.formalizer.tp_proposer import (
    Hypothesis, PROPOSITION_NODE_KINDS, StructureProposalRequest, TEdge, TNode,
    parse_and_validate,
)
from ah.formalizer.tp_readable_protocol import (
    build_readable_structure_prompt, parse_readable_structure_reply,
    readable_structure_catalog, serialize_readable_structure_reply,
)


def request(**updates):
    values = dict(token_hypotheses=('captured-feature:0', 'captured-feature:1'),
        allowed_node_kinds=PROPOSITION_NODE_KINDS | {'ENTITY', 'BOUND_VAR', 'TIME', 'NUMERAL', 'WH', 'COUNT_REQUEST'},
        allowed_edge_kinds=frozenset({'ARGUMENT', 'ATTITUDE', 'OPERAND', 'BIND', 'TIME_SCOPE', 'QUERY_SLOT'}),
        allowed_role_ids=frozenset({'SUBJECT', 'OBJECT', 'EXPERIENCER', 'SURFACE_ARG'}))
    values.update(updates)
    return StructureProposalRequest('TP:captured-request', 'structural-hash-pre',
        tuple('captured-token:' + str(i) for i in range(12)), **values)


def node(req, kind, index, **updates):
    return TNode(kind, (req.source_spans[index],), **updates)


def simple(req):
    return Hypothesis('h0', (node(req, 'PREDICATE', 1), node(req, 'ENTITY', 0)),
        (TEdge('ARGUMENT', 0, 1, 'SUBJECT'),), alignment=req.source_spans[:2])


def legacy_wire(hypotheses):
    result = []
    for hypothesis in hypotheses:
        value = asdict(hypothesis)
        value['edges'] = [dict(kind=e.kind, **{'from': e.from_idx, 'to': e.to_idx},
            role_id=e.role_id, scope=e.scope) for e in hypothesis.edges]
        result.append(value)
    return json.dumps({'hypotheses': result}, separators=(',', ':'))


def payload(prompt):
    result, end = json.JSONDecoder().raw_decode(prompt.split('EVIDENCE_JSON:\n', 1)[1])
    assert end > 0
    return result


def test_complete_graph_is_bijective_and_still_small_without_opaque_kind_codes():
    req = request()
    first = Hypothesis('h0', (
        node(req, 'NOT', 0), TNode('PREDICATE', req.source_spans[1:3],
            req.token_hypotheses, req.source_spans[2]),
        node(req, 'ENTITY', 3), node(req, 'TIME', 4)),
        (TEdge('OPERAND', 0, 1, scope=True), TEdge('ARGUMENT', 1, 2, 'SUBJECT'),
         TEdge('TIME_SCOPE', 0, 3)), alternatives=2, alignment=req.source_spans[:5])
    second = replace(simple(req), local_id='h1')
    hypotheses = [first, second]
    wire = serialize_readable_structure_reply(req, hypotheses)
    assert parse_readable_structure_reply(req, wire) == parse_and_validate(req, legacy_wire(hypotheses)) == hypotheses
    assert 'N n1 PREDICATE t1,t2 head=t2 features=f0,f1' in wire
    assert 'E ARGUMENT n1 n2 role=SUBJECT' in wire
    assert 'E OPERAND n0 n1 scope' in wire
    assert 'alternatives=2' in wire
    assert len(wire) < len(legacy_wire(hypotheses)) / 3
    assert all(value not in wire for value in req.source_spans + req.token_hypotheses)


def test_input_aliases_typed_reference_values_and_map_keys_without_evidence_loss():
    req = request(deterministic_candidates=({'bindings': {'captured-token:0': 'captured-token:1'},
        'morph_bindings': {'captured-token:0': {'lemma': 'captured-token:1'}},
        'proposed_roles': {'captured-token:1': 'OBJECT'},
        'feature_refs': ['captured-feature:0'], 'note': 'prefix:captured-token:0'},),
        uncovered_spans=('captured-token:0',), required_operators=(('NOT', ('captured-token:2',)),),
        released_slot_evidence={'resource_snapshot': {'release_sha256': 'immutable-release-hash'},
            'valency_alternatives': [{'anchor_refs': ['captured-token:0'],
                'roles': [{'role_id': 'OBJECT', 'argument_types': ['PROPOSITION']}]}]},
        speech_act_metadata={'query_form': 'BOOLEAN'})
    tokens = [{'id': req.source_spans[0], 'text': 'raw text kept exactly'},
              {'id': req.source_spans[1], 'text': 'other text', 'feature_refs': ['captured-feature:1']}]
    prompt = build_readable_structure_prompt(req, tokens)
    data = payload(prompt)
    assert data['protocol'] == 'TP-C2'
    assert data['reference_binding_sha256'] == digest({'tokens': list(req.source_spans),
                                                    'features': list(req.token_hypotheses)})
    assert data['catalog']['token_refs'] == ['t' + str(i) for i in range(12)]
    assert data['catalog']['feature_refs'] == ['f0', 'f1']
    assert data['tokens'] == [{'id': 't0', 'text': 'raw text kept exactly'},
                              {'id': 't1', 'text': 'other text', 'feature_refs': ['f1']}]
    assert data['request']['deterministic_candidates'] == [{'bindings': {'captured-token:0': 'captured-token:1'},
        'morph_bindings': {'t0': {'lemma': 'captured-token:1'}},
        'proposed_roles': {'t1': 'OBJECT'},
        'feature_refs': ['f0'], 'note': 'prefix:captured-token:0'}]
    assert data['request']['required_operators'] == [['NOT', ['t2']]]
    assert data['request']['released_slot_evidence']['valency_alternatives'][0]['anchor_refs'] == ['t0']
    assert data['request']['released_slot_evidence']['resource_snapshot']['release_sha256'] == 'immutable-release-hash'
    assert data['request']['request_id'] == req.request_id
    assert data['request']['structural_hash_pre'] == req.structural_hash_pre
    assert data['request']['speech_act_metadata'] == req.speech_act_metadata
    assert 'expanded_structure_rules' not in data
    assert 'Use token IDs, never token text' not in prompt
    assert 'Nodes have no id field' not in prompt
    assert 'END OF INPUT. Reply only with complete TP-C2 blocks' in prompt
    assert 'missing dictionary sense or unknown word alone is NOT a reason to abstain' in prompt
    assert 'H format_demo t0,t1\nN n0 PREDICATE t0\nN n1 ENTITY t1\nE ARGUMENT n0 n1 role=SUBJECT\nEND' in prompt
    # Fresh IDs with the same readable indices still change the replay identity.
    another = replace(req, source_spans=tuple('other-capture:' + str(i) for i in range(12)))
    assert payload(build_readable_structure_prompt(another, []))['reference_binding_sha256'] != data['reference_binding_sha256']


def test_reference_aliasing_preserves_lexical_text_and_opaque_metadata_equal_to_ids():
    req = replace(request(), request_id='alpha', structural_hash_pre='beta',
        source_spans=('alpha', 'beta'), token_hypotheses=('feature',),
        deterministic_candidates=({'anchor_span': 'alpha', 'participants': ['alpha', 'beta'],
            'predicate_token_ref': 'alpha', 'argument_token_refs': ['beta'],
            'opaque': {'alpha': 'beta'}, 'semantic': {'lexical_units': {
                'alpha': {'head_ref': 'alpha', 'anchor_refs': ['alpha'], 'surface': 'alpha'}}}},),
        released_slot_evidence={'resource_snapshot': {'release_sha256': 'alpha'},
            'valency_alternatives': [{'anchor_refs': ['alpha'], 'lemma': 'alpha',
                'role_id': 'beta', 'value': 'alpha'}]},
        speech_act_metadata={'text': 'alpha', 'value': 'beta', 'hypothesis_id': 'feature'})
    tokens = [{'id': 'alpha', 'token_id': 'alpha', 'text': 'alpha', 'span': 'alpha',
               'lemma': 'alpha', 'variants': [{'lemma': 'beta', 'pos': 'feature'}]},
              {'id': 'beta', 'text': 'beta'}]
    data = payload(build_readable_structure_prompt(req, tokens))
    assert data['tokens'] == [dict(tokens[0], id='t0', token_id='t0'), dict(tokens[1], id='t1')]
    assert data['request']['request_id'] == 'alpha'
    assert data['request']['structural_hash_pre'] == 'beta'
    assert data['request']['speech_act_metadata'] == req.speech_act_metadata
    candidate = data['request']['deterministic_candidates'][0]
    assert candidate['anchor_span'] == 'alpha' and candidate['participants'] == ['alpha', 'beta']
    assert candidate['opaque'] == {'alpha': 'beta'}
    assert candidate['predicate_token_ref'] == 't0' and candidate['argument_token_refs'] == ['t1']
    assert candidate['semantic']['lexical_units']['t0'] == {'head_ref': 't0', 'anchor_refs': ['t0'], 'surface': 'alpha'}
    assert data['request']['released_slot_evidence']['valency_alternatives'][0] == {
        'anchor_refs': ['t0'], 'lemma': 'alpha', 'role_id': 'beta', 'value': 'alpha'}
    assert data['request']['released_slot_evidence']['resource_snapshot']['release_sha256'] == 'alpha'


def test_captured_feature_record_id_is_aliased_but_raw_span_and_variants_are_preserved():
    from ah.formalizer.state import TokenHypothesis
    feature = TokenHypothesis('feature', 'alpha', ('feature', 'alpha'))
    req = replace(request(), source_spans=('alpha',), token_hypotheses=(feature,))
    data = payload(build_readable_structure_prompt(req, []))
    record = data['request']['token_hypotheses'][0]
    assert record['hypothesis_id'] == 'f0'
    assert record['span_ref'] == 'alpha' and record['variants'] == ['feature', 'alpha']


@pytest.mark.parametrize('kind', ['NOT', 'POSSIBLE', 'NECESSARY'])
def test_unary_scopes_keep_required_trigger_and_flag(kind):
    req = request(required_operators=((kind, ('captured-token:0',)),))
    hyp = Hypothesis('h0', (node(req, kind, 0), node(req, 'PREDICATE', 1)),
        (TEdge('OPERAND', 0, 1, scope=True),), alignment=req.source_spans[:2])
    assert parse_readable_structure_reply(req, serialize_readable_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind', ['AND', 'OR', 'XOR', 'IMPLIES', 'COUNTERFACTUAL', 'ASSOCIATION'])
def test_binary_nary_operator_order_is_not_sorted_or_invented(kind):
    req = request()
    hyp = Hypothesis('h0', (node(req, kind, 0), node(req, 'PREDICATE', 1),
        node(req, 'PREDICATE', 2)), (TEdge('OPERAND', 0, 2), TEdge('OPERAND', 0, 1)),
        alignment=req.source_spans[:3])
    assert parse_readable_structure_reply(req, serialize_readable_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind', ['FORALL', 'EXISTS', 'AT_LEAST_N', 'EXACTLY_N', 'AT_MOST_N'])
def test_quantifier_numeric_scope_and_binding_slots_are_complete(kind):
    req = request()
    nodes = [node(req, kind, 0), node(req, 'BOUND_VAR', 1), node(req, 'PREDICATE', 2), node(req, 'ENTITY', 3)]
    edges = [TEdge('OPERAND', 0, 1), TEdge('OPERAND', 0, 2), TEdge('ARGUMENT', 2, 3, 'SUBJECT'), TEdge('BIND', 1, 3)]
    if kind not in {'FORALL', 'EXISTS'}:
        nodes.append(node(req, 'NUMERAL', 4)); edges.append(TEdge('OPERAND', 0, 4))
    hyp = Hypothesis('h0', tuple(nodes), tuple(edges), alignment=req.source_spans[:len(nodes)])
    assert parse_readable_structure_reply(req, serialize_readable_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind', ['BEFORE', 'AFTER', 'DURING'])
def test_temporal_operands_are_typed_anchors_not_values(kind):
    req = request()
    hyp = Hypothesis('h0', (node(req, kind, 0), node(req, 'TIME', 1), node(req, 'PREDICATE', 2)),
        (TEdge('OPERAND', 0, 1), TEdge('OPERAND', 0, 2)), alignment=req.source_spans[:3])
    assert parse_readable_structure_reply(req, serialize_readable_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('kind,target,role', [('ATTITUDE', 'PREDICATE', 'OBJECT'),
    ('QUERY_SLOT', 'WH', 'SUBJECT'), ('QUERY_SLOT', 'COUNT_REQUEST', 'OBJECT'),
    ('ARGUMENT', 'ENTITY', 'SURFACE_ARG')])
def test_typed_content_questions_and_surface_roles_remain_registered(kind, target, role):
    req = request()
    hyp = Hypothesis('h0', (node(req, 'PREDICATE', 0), node(req, target, 1)),
        (TEdge(kind, 0, 1, role),), alignment=req.source_spans[:2])
    assert parse_readable_structure_reply(req, serialize_readable_structure_reply(req, [hyp])) == [hyp]


@pytest.mark.parametrize('damage', ['json', 'c1', 'missing_H', 'fence', 'prose', 'missing_END',
    'numeric_token', 'token_as_node', 'node_as_token', 'node_gap', 'duplicate_node', 'node_after_edge',
    'foreign_kind', 'foreign_edge', 'foreign_role', 'missing_role', 'foreign_token', 'foreign_head',
    'foreign_feature', 'duplicate_alignment', 'duplicate_anchor', 'duplicate_feature', 'duplicate_head',
    'bare_alternatives', 'duplicate_scope', 'abstain_plus_graph', 'duplicate_label', 'trailing_prose'])
def test_bad_new_wire_does_not_get_repaired_or_reinterpreted(damage):
    req = request()
    valid = serialize_readable_structure_reply(req, [simple(req)])
    invalid = {
        'json': legacy_wire([simple(req)]), 'c1': 'H h0 0,1\nN K20 1\nN K10 0\nE E0 0 1 /R14\n.',
        'missing_H': valid.replace('H h0', 'h0'), 'fence': '```\n' + valid + '\n```',
        'prose': 'Here is a graph:\n' + valid, 'missing_END': valid.rsplit('\n', 1)[0],
        'numeric_token': valid.replace('H h0 t0,t1', 'H h0 0,1'),
        'token_as_node': valid.replace('ARGUMENT n0 n1', 'ARGUMENT t0 t1'),
        'node_as_token': valid.replace('PREDICATE t1', 'PREDICATE n1'),
        'node_gap': valid.replace('N n1 ENTITY', 'N n2 ENTITY'),
        'duplicate_node': valid.replace('N n1 ENTITY', 'N n0 ENTITY'),
        'node_after_edge': valid.replace('\nEND', '\nN n2 ENTITY t2\nEND'),
        'foreign_kind': valid.replace('PREDICATE', 'INVENTED'),
        'foreign_edge': valid.replace('ARGUMENT', 'INVENTED'),
        'foreign_role': valid.replace('SUBJECT', 'INVENTED'),
        'missing_role': valid.replace(' role=SUBJECT', ''),
        'foreign_token': valid.replace('H h0 t0,t1', 'H h0 t0,t999'),
        'foreign_head': valid.replace('PREDICATE t1', 'PREDICATE t1 head=t999'),
        'foreign_feature': valid.replace('PREDICATE t1', 'PREDICATE t1 features=f999'),
        'duplicate_alignment': valid.replace('H h0 t0,t1', 'H h0 t0,t1,t1'),
        'duplicate_anchor': valid.replace('PREDICATE t1', 'PREDICATE t1,t1'),
        'duplicate_feature': valid.replace('PREDICATE t1', 'PREDICATE t1 features=f0,f0'),
        'duplicate_head': valid.replace('PREDICATE t1', 'PREDICATE t1 head=t1 head=t1'),
        'bare_alternatives': valid.replace('H h0 t0,t1', 'H h0 t0,t1 1'),
        'duplicate_scope': valid.replace('SUBJECT', 'SUBJECT scope scope'),
        'abstain_plus_graph': 'ABSTAIN\n' + valid,
        'duplicate_label': valid + '\n' + valid,
        'trailing_prose': valid + '\nDone.',
    }[damage]
    with pytest.raises(ProtocolError):
        parse_readable_structure_reply(req, invalid)


def test_cycles_arity_alignment_heads_required_operators_and_budgets_stay_strict():
    req = request()
    invalid = [
        'H h0 t0,t1\nN n0 PREDICATE t0\nN n1 PREDICATE t1\nE ARGUMENT n0 n1 role=OBJECT\nE ARGUMENT n1 n0 role=OBJECT\nEND',
        'H h0 t0\nN n0 NOT t0\nEND',
        'H h0 t0,t1\nN n0 PREDICATE t0,t1\nEND',
        'H h0 t0\nN n0 PREDICATE t1\nEND',
        'H h0 t0\nN n0 TIME t0 head=t0\nEND',
    ]
    for value in invalid:
        with pytest.raises(ProtocolError): parse_readable_structure_reply(req, value)
    wire = serialize_readable_structure_reply(req, [simple(req)])
    with pytest.raises(ProtocolError, match='source operator scope silently lost'):
        parse_readable_structure_reply(replace(req, required_operators=(('NOT', (req.source_spans[0],)),)), wire)
    with pytest.raises(ProtocolError, match='PROPOSAL_BUDGET'):
        parse_readable_structure_reply(replace(req, max_nodes=1), wire)
    assert parse_readable_structure_reply(req, 'ABSTAIN') == []
    assert parse_readable_structure_reply(req, None) == []
    with pytest.raises(ProtocolError, match='budget pre-check'):
        parse_readable_structure_reply(replace(req, budget_ok=False), 'ABSTAIN')


def test_capture_alias_collisions_fail_instead_of_losing_fields():
    req = request(deterministic_candidates=({'morph_bindings': {'captured-token:0': 'first', 't0': 'second'}},))
    with pytest.raises(ProtocolError, match='alias collision'):
        build_readable_structure_prompt(req, [])
    with pytest.raises(ProtocolError, match='duplicate source'):
        readable_structure_catalog(replace(req, source_spans=('same', 'same')))
    with pytest.raises(ProtocolError, match='duplicate feature'):
        readable_structure_catalog(replace(req, token_hypotheses=('same', 'same')))


def test_token_and_feature_ids_can_overlap_in_their_separate_namespaces():
    req = replace(request(), source_spans=('same',), token_hypotheses=('same',))
    hypothesis = Hypothesis('h0', (TNode('PREDICATE', ('same',), ('same',)),), alignment=('same',))
    data = payload(build_readable_structure_prompt(req, [{'id': 'same', 'text': 'same', 'feature_refs': ['same']}]))
    assert data['request']['source_spans'] == ['t0']
    assert data['request']['token_hypotheses'] == ['f0']
    assert data['tokens'] == [{'id': 't0', 'text': 'same', 'feature_refs': ['f0']}]
    wire = serialize_readable_structure_reply(req, [hypothesis])
    assert 'N n0 PREDICATE t0 features=f0' in wire
    assert parse_readable_structure_reply(req, wire) == [hypothesis]


@pytest.mark.parametrize('role', ['scope', 'АГЕНТ', 'agent role', 'agent%20role', 'agent\trole', 'роль с пробелом'])
def test_registered_role_values_have_unambiguous_closed_wire_tokens(role):
    req = request(allowed_role_ids=frozenset({role}))
    hyp = replace(simple(req), edges=(TEdge('ARGUMENT', 0, 1, role, True),))
    wire = serialize_readable_structure_reply(req, [hyp])
    assert parse_readable_structure_reply(req, wire) == [hyp]
    role_token = next(iter(readable_structure_catalog(req)['role_tokens']))
    assert ' role=' + role_token + ' scope' in wire
    assert not any(c.isspace() for c in role_token)
    # There is one accepted spelling: no arbitrary percent-decoding guesses.
    if role == 'scope':
        with pytest.raises(ProtocolError):
            parse_readable_structure_reply(req, wire.replace('role=scope', 'role=%73cope'))
