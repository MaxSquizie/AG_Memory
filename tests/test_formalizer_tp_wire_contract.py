"""The live proposer is told the wire contract its validator actually requires."""
import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from ah.formalizer.selection_protocol import ProtocolError
from ah.formalizer.tp_proposer import (
    StructureProposalRequest, build_structure_prompt, parse_and_validate,
)


def request():
    return StructureProposalRequest('TP:example', 'pre-seal', ('t0', 't1', 't2'),
        allowed_node_kinds=frozenset({'PREDICATE', 'ENTITY', 'NOT'}),
        allowed_edge_kinds=frozenset({'ARGUMENT', 'OPERAND'}),
        allowed_role_ids=frozenset({'SUBJECT', 'SURFACE_ARG'}))


def reply():
    return {'hypotheses': [{'local_id': 'local-reading',
        'nodes': [{'kind': 'PREDICATE', 'anchor_spans': ['t1']},
                  {'kind': 'ENTITY', 'anchor_spans': ['t0']}],
        'edges': [{'kind': 'ARGUMENT', 'from': 0, 'to': 1, 'role_id': 'SUBJECT'}],
        'alignment': ['t0', 't1']} ]}


def test_prompt_declares_mandatory_fields_indices_and_request_reference_space():
    req = request()
    prompt = json.loads(build_structure_prompt(req, [
        {'id': 't0', 'text': 'Иван'}, {'id': 't1', 'text': 'вошёл'}, {'id': 't2', 'text': '.'}]))
    schema = prompt['response_schema']
    hypothesis = schema['properties']['hypotheses']['items']
    assert set(hypothesis['required']) == {'local_id', 'nodes', 'alignment'}
    assert hypothesis['properties']['edges']['items']['properties']['from']['type'] == 'integer'
    assert hypothesis['properties']['alignment']['items']['enum'] == list(req.source_spans)
    assert hypothesis['properties']['nodes']['items']['additionalProperties'] is False
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(reply())
    assert len(parse_and_validate(req, json.dumps(reply()))) == 1


def test_compact_wire_preserves_text_evidence_and_stable_instruction_prefix():
    first = request()
    second = StructureProposalRequest('TP:other-source', 'other-seal', ('different-token',),
        allowed_node_kinds=first.allowed_node_kinds,
        allowed_edge_kinds=first.allowed_edge_kinds,
        allowed_role_ids=first.allowed_role_ids,
        released_slot_evidence={'status': 'COMPLETE', 'attitude_alternatives': [
            {'argument_role': 'SUBJECT', 'note': 'spaces within evidence stay intact'}]})
    tokens = [{'id': 'different-token', 'text': 'слово с пробелами'}]
    raw = build_structure_prompt(second, tokens)
    parsed = json.loads(raw)
    assert raw == json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))
    assert parsed['tokens'] == tokens
    assert parsed['request']['released_slot_evidence'] == second.released_slot_evidence
    assert raw.split(',"response_schema":', 1)[0] == build_structure_prompt(
        first, []).split(',"response_schema":', 1)[0]
    assert set(parsed) == {'task', 'reply_rules', 'response_schema', 'request', 'tokens'}


def test_omitting_neutral_defaults_preserves_validated_graph_and_nondefaults():
    req = StructureProposalRequest('TP:defaults', 'seal', ('t0', 't1', 't2', 't3'),
        token_hypotheses=('feature:t2',),
        allowed_node_kinds=frozenset({'NOT', 'PREDICATE', 'ENTITY'}),
        allowed_edge_kinds=frozenset({'OPERAND', 'ARGUMENT'}),
        allowed_role_ids=frozenset({'SUBJECT'}))
    minimal = {'hypotheses': [{'local_id': 'h', 'alternatives': 2,
        'nodes': [{'kind': 'NOT', 'anchor_spans': ['t0']},
                  {'kind': 'PREDICATE', 'anchor_spans': ['t1', 't2'],
                   'head_anchor': 't2', 'feature_refs': ['feature:t2']},
                  {'kind': 'ENTITY', 'anchor_spans': ['t3']}],
        'edges': [{'kind': 'OPERAND', 'from': 0, 'to': 1, 'scope': True},
                  {'kind': 'ARGUMENT', 'from': 1, 'to': 2, 'role_id': 'SUBJECT'}],
        'alignment': ['t0', 't1', 't2', 't3']}, reply()['hypotheses'][0]]}
    verbose = deepcopy(minimal)
    for hypothesis in verbose['hypotheses']:
        hypothesis.setdefault('alternatives', 1)
        for node in hypothesis['nodes']:
            node.setdefault('head_anchor', None)
            node.setdefault('feature_refs', [])
        for edge in hypothesis['edges']:
            edge.setdefault('scope', False)
            edge.setdefault('role_id', None)
    schema = json.loads(build_structure_prompt(req, []))['response_schema']
    Draft202012Validator(schema).validate(minimal)
    Draft202012Validator(schema).validate(verbose)
    actual = parse_and_validate(req, json.dumps(minimal, separators=(',', ':')))
    assert actual == parse_and_validate(req, json.dumps(verbose, indent=2))
    assert len(actual) == 2
    assert actual[0].alternatives == 2
    assert actual[0].nodes[1].head_anchor == 't2'
    assert actual[0].nodes[1].feature_refs == ('feature:t2',)
    assert actual[0].edges[0].scope is True
    assert actual[0].edges[1].role_id == 'SUBJECT'


@pytest.mark.parametrize('damage', ['alignment', 'node_id', 'string_edge', 'foreign_anchor'])
def test_fenced_reply_still_rejects_invalid_structures(damage):
    value = reply()
    hyp = value['hypotheses'][0]
    if damage == 'alignment':
        del hyp['alignment']
    elif damage == 'node_id':
        hyp['nodes'][0]['id'] = 'p'
    elif damage == 'string_edge':
        hyp['edges'][0]['from'] = 'p'
    else:
        hyp['nodes'][0]['anchor_spans'] = ['outside-request']
    with pytest.raises(ProtocolError):
        parse_and_validate(request(), '```json\n' + json.dumps(value) + '\n```')


def test_one_outer_fence_preserves_the_same_validated_graph_and_prose_stays_invalid():
    raw = json.dumps(reply())
    assert parse_and_validate(request(), '```json\n' + raw + '\n```') == parse_and_validate(request(), raw)
    with pytest.raises(ProtocolError):
        parse_and_validate(request(), 'Here is a graph:\n```json\n' + raw + '\n```')


@pytest.mark.parametrize('kind', ['NOT', 'TIME', 'WH'])
def test_schema_and_validator_agree_on_nonlexical_head_anchor(kind):
    req = StructureProposalRequest('TP:head-kind', 'pre-seal', ('t0', 't1'),
        allowed_node_kinds=frozenset({'PREDICATE', kind}),
        allowed_edge_kinds=frozenset({'OPERAND', 'TIME_SCOPE', 'QUERY_SLOT'}),
        allowed_role_ids=frozenset({'OBJECT'}))
    graph = {'hypotheses': [{'local_id': 'h',
        'nodes': [{'kind': kind, 'anchor_spans': ['t0']},
                  {'kind': 'PREDICATE', 'anchor_spans': ['t1']}],
        'edges': [{'kind': 'OPERAND', 'from': 0, 'to': 1}] if kind == 'NOT' else
                 [{'kind': 'TIME_SCOPE', 'from': 1, 'to': 0}] if kind == 'TIME' else
                 [{'kind': 'QUERY_SLOT', 'from': 1, 'to': 0, 'role_id': 'OBJECT'}],
        'alignment': ['t0', 't1']}]}
    schema = json.loads(build_structure_prompt(req, []))['response_schema']
    validator = Draft202012Validator(schema)
    validator.validate(graph)
    assert parse_and_validate(req, json.dumps(graph))
    # This is the actual failure class in the recorded run: the token is
    # anchored correctly but head_anchor is forbidden for this node kind.
    graph['hypotheses'][0]['nodes'][0]['head_anchor'] = 't0'
    assert list(validator.iter_errors(graph))
    with pytest.raises(ProtocolError, match=rf'node\[0\] kind={kind} forbids head_anchor'):
        parse_and_validate(req, json.dumps(graph))


@pytest.mark.parametrize('kind,target', [('ARGUMENT', 'ENTITY'),
    ('ATTITUDE', 'PREDICATE'), ('QUERY_SLOT', 'WH')])
@pytest.mark.parametrize('missing', [True, False])
def test_schema_and_validator_require_nonnull_typed_edge_role(kind, target, missing):
    req = StructureProposalRequest('TP:role', 'pre-seal', ('t0', 't1'),
        allowed_node_kinds=frozenset({'PREDICATE', target}),
        allowed_edge_kinds=frozenset({kind}), allowed_role_ids=frozenset({'OBJECT'}))
    graph = {'hypotheses': [{'local_id': 'h',
        'nodes': [{'kind': 'PREDICATE', 'anchor_spans': ['t0']},
                  {'kind': target, 'anchor_spans': ['t1']}],
        'edges': [{'kind': kind, 'from': 0, 'to': 1, 'role_id': 'OBJECT'}],
        'alignment': ['t0', 't1']}]}
    validator = Draft202012Validator(json.loads(build_structure_prompt(req, []))['response_schema'])
    validator.validate(graph)
    assert parse_and_validate(req, json.dumps(graph))
    edge = graph['hypotheses'][0]['edges'][0]
    if missing:
        del edge['role_id']
    else:
        edge['role_id'] = None
    assert list(validator.iter_errors(graph))
    with pytest.raises(ProtocolError, match=rf'{kind} requires a non-null registered role_id'):
        parse_and_validate(req, json.dumps(graph))


def test_schema_requires_own_head_for_multitoken_lexical_node():
    req = request()
    graph = reply()
    graph['hypotheses'][0]['nodes'][0]['anchor_spans'] = ['t1', 't2']
    graph['hypotheses'][0]['alignment'].append('t2')
    validator = Draft202012Validator(json.loads(build_structure_prompt(req, []))['response_schema'])
    assert list(validator.iter_errors(graph))
    with pytest.raises(ProtocolError, match='explicit morphological head'):
        parse_and_validate(req, json.dumps(graph))
    graph['hypotheses'][0]['nodes'][0]['head_anchor'] = 't1'
    validator.validate(graph)
    assert parse_and_validate(req, json.dumps(graph))


def test_actual_native_simple_ingest_observes_declared_contract_and_accepts_fenced_graph(tmp_path):
    from tools.formalizer_v7_extended_binding import Session
    from tools.formalizer_v7_native_binding import execute_native

    prompts = []

    class Backend:
        def generate(self, prompt, **_kwargs):
            if prompt.startswith('{'):
                data = json.loads(prompt)
                assert 'response_schema' in data
                tokens = {t['text']: t['id'] for t in data['tokens']}
                result = {'hypotheses': [{'local_id': 'native-local',
                    'nodes': [{'kind': 'PREDICATE', 'anchor_spans': [tokens['вошёл']]},
                              {'kind': 'ENTITY', 'anchor_spans': [tokens['Иван']]}],
                    'edges': [{'kind': 'ARGUMENT', 'from': 0, 'to': 1, 'role_id': 'SUBJECT'}],
                    'alignment': [tokens['Иван'], tokens['вошёл']]}]}
                Draft202012Validator(data['response_schema']).validate(result)
                prompts.append(data)
                return '```json\n' + json.dumps(result) + '\n```'
            raise AssertionError('One released, grounded value should not need model selection')

    payload = {'raw_input': {'text': 'Иван вошёл.', 'source_id': 'native-wire-contract',
        'revision': 1, 'range': [0, 11], 'language': 'ru',
        'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    session = Session([payload], tmp_path / 'native.log')
    # Exercise the real T0–T6 path; inject only the provider response.
    from unittest.mock import patch
    with patch('tools.formalizer_v7_native_binding.ChatBackend', return_value=Backend()):
        actual = execute_native(session, payload, {'provider': 'lmstudio', 'model': 'wire-fixture'})
    assert len(prompts) == 1
    expected = [{'predicate': 'ENTER', 'roles': {'AGENT': {'entity': 'ivan'}}}]
    assert actual['generation']['gold_patterns'] == expected
    assert actual['assertions']['ah'] == expected
    assert actual['runtime']['report']['terminal'] == 'APPLIED'
    assert actual['store']['marker_count'] == 1


def test_actual_native_missing_alignment_stays_empty_with_actionable_diagnostic(tmp_path):
    from unittest.mock import patch
    from tools.formalizer_v7_extended_binding import Session
    from tools.formalizer_v7_native_binding import execute_native
    from tools.formalizer_v7_run_diagnostics import case_diagnostics

    class Backend:
        def generate(self, prompt, **_kwargs):
            data = json.loads(prompt)
            tokens = {t['text']: t['id'] for t in data['tokens']}
            return json.dumps({'hypotheses': [{'local_id': 'missing-alignment',
                'nodes': [{'kind': 'PREDICATE', 'anchor_spans': [tokens['вошёл']]},
                          {'kind': 'ENTITY', 'anchor_spans': [tokens['Иван']]}],
                'edges': [{'kind': 'ARGUMENT', 'from': 0, 'to': 1, 'role_id': 'SUBJECT'}]}]})

    payload = {'raw_input': {'text': 'Иван вошёл.', 'source_id': 'invalid-wire-contract',
        'revision': 1, 'range': [0, 11], 'language': 'ru',
        'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    session = Session([payload], tmp_path / 'native.log')
    with patch('tools.formalizer_v7_native_binding.ChatBackend', return_value=Backend()):
        observed = execute_native(session, payload, {'provider': 'lmstudio', 'model': 'wire-fixture'})
    assert observed['assertions']['ah'] == observed['generation']['gold_patterns'] == []
    assert observed['runtime']['report']['terminal'] == 'RESOLUTION_ONLY'
    assert observed['store']['marker_count'] == 0
    diagnostics = case_diagnostics({'case_id': 'wire-failure', 'checkpoints': [
        {'step_id': 'ingest', 'actual': observed}]}, wal_path=tmp_path / 'native.log')
    problem = next(d for d in diagnostics['native_diagnostics'] if d['code'] == 'PROPOSAL_INVALID')
    assert "missing=['alignment']" in problem['detail']
    assert '$.hypotheses[0]' in problem['detail']


@pytest.mark.parametrize('text,predicate,entities,expected,coverage', [
    ('Мне холодно.', 'холодно', [('Мне', 'EXPERIENCER')],
     {'predicate': 'OPEN:холодно', 'roles': {'EXPERIENCER': {'entity': 'speaker'}}}, 'OPEN_LEXICAL'),
    ('Курьер переадресовал письмо.', 'переадресовал', [('Курьер', 'SUBJECT'), ('письмо', 'OBJECT')],
     {'predicate': 'OPEN:переадресовать', 'roles': {'AGENT': {'entity': 'courier'},
                                                'THEME': {'entity': 'letter'}}}, 'OPEN_LEXICAL'),
    ('Иван вошёл.', 'вошёл', [('Иван', 'SUBJECT')],
     {'predicate': 'ENTER', 'roles': {'AGENT': {'entity': 'ivan'}}}, 'FULL_CANONICAL'),
    ('Иван вошёл неизвестно.', 'вошёл', [('Иван', 'SUBJECT')],
     {'predicate': 'ENTER', 'roles': {'AGENT': {'entity': 'ivan'}}}, 'PARTIAL'),
])
def test_real_morphology_punctuation_does_not_lower_native_coverage(
        tmp_path, text, predicate, entities, expected, coverage):
    from unittest.mock import patch
    from tools.formalizer_v7_extended_binding import Session
    from tools.formalizer_v7_native_binding import execute_native

    class Backend:
        def generate(self, prompt, **_kwargs):
            data = json.loads(prompt)
            tokens = {t['text']: t['id'] for t in data['tokens']}
            nodes = [{'kind': 'PREDICATE', 'anchor_spans': [tokens[predicate]]}]
            nodes += [{'kind': 'ENTITY', 'anchor_spans': [tokens[word]]} for word, _ in entities]
            graph = {'hypotheses': [{'local_id': 'punctuation', 'nodes': nodes,
                'edges': [{'kind': 'ARGUMENT', 'from': 0, 'to': i, 'role_id': role}
                          for i, (_, role) in enumerate(entities, 1)],
                'alignment': [tokens[predicate]] + [tokens[word] for word, _ in entities]}]}
            Draft202012Validator(data['response_schema']).validate(graph)
            return json.dumps(graph)

    payload = {'raw_input': {'text': text, 'source_id': 'coverage-wire-contract',
        'revision': 1, 'range': [0, len(text)], 'language': 'ru',
        'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    session = Session([payload], tmp_path / 'native.log')
    with patch('tools.formalizer_v7_native_binding.ChatBackend', return_value=Backend()):
        actual = execute_native(session, payload, {'provider': 'lmstudio', 'model': 'wire-fixture'})
    assert actual['runtime']['report']['terminal'] == 'APPLIED'
    assert actual['assertions']['ah'] == [expected]
    assert actual['coverage']['status'] == coverage
    assert bool(actual['coverage']['unresolved_span_ids']) == (coverage == 'PARTIAL')
    punct_id = f'tok:{len(text)-1}:{len(text)}'
    assert punct_id not in actual['runtime']['coverage_evidence']['relevant_token_refs']
