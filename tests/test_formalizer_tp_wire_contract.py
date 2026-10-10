"""The live proposer is told the wire contract its validator actually requires."""
import json

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
