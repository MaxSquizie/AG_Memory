"""The default live seam uses indexed replies, retaining raw WAL and typed gates."""
from dataclasses import fields
import json

import pytest

from ah.core.journal import JournalChannel
from ah.formalizer.provider_adapter import IntegrityError
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.selection_protocol import DecisionSchema, ProtocolError, Relation
from ah.formalizer.selector_wire import (
    build_selector_prompt, build_structure_worker_prompt, validate_selector_reply,
    validate_structure_worker_reply,
)
from ah.formalizer.tp_compact_protocol import serialize_compact_structure_reply
from ah.formalizer.tp_readable_protocol import serialize_readable_structure_reply
from ah.formalizer.tp_proposer import Hypothesis, StructureProposalRequest, TEdge, TNode
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import ChatBackend, execute_native


def request_from_payload(prompt):
    data, _ = json.JSONDecoder().raw_decode(prompt.split('EVIDENCE_JSON:\n', 1)[1])
    request = dict(data['request'])
    request['source_spans'] = tuple(request['source_spans'])
    for field in fields(StructureProposalRequest):
        if field.name.startswith('allowed_'):
            request[field.name] = frozenset(request[field.name])
        elif isinstance(field.default, tuple):
            request[field.name] = tuple(request[field.name])
    return data, StructureProposalRequest(**request)


class ScriptedBackend:
    model = 'compact-fixture'

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return next(self.replies)


def schema():
    return DecisionSchema('fixture', {
        'c0': Relation('c0', 'first', 0, (), 'First admissible reading'),
        'c1': Relation('c1', 'second', 0, (), 'Second admissible reading'),
    })


def test_default_compact_raw_bytes_replay_and_protocol_mismatch(tmp_path):
    req = StructureProposalRequest('fixture', 'frozen', ('source:0', 'source:1'),
        allowed_node_kinds=frozenset({'PREDICATE', 'ENTITY'}),
        allowed_edge_kinds=frozenset({'ARGUMENT'}),
        allowed_role_ids=frozenset({'SUBJECT'}))
    hypothesis = Hypothesis('h0', (TNode('PREDICATE', ('source:1',)),
        TNode('ENTITY', ('source:0',))), (TEdge('ARGUMENT', 0, 1, 'SUBJECT'),),
        alignment=req.source_spans)
    raw = serialize_readable_structure_reply(req, [hypothesis]) + '\n'
    path = tmp_path / 'provider.log'
    backend = ScriptedBackend([raw, '2\n'])
    selector = RealBackendSelector(backend, journal=JournalChannel(path))
    assert (selector.structure_reply_format, selector.selection_reply_format) == ('TP-C2', 'SELECT_LABELS_V1')
    selector.start_run('frozen-run')
    prompt = build_structure_worker_prompt(selector, req, [{'id': 'source:0', 'text': 'актант'},
        {'id': 'source:1', 'text': 'предикат'}])
    selection_prompt = build_selector_prompt(selector, slot_id='value', frame_id='frame',
        context_span='input', mentions={}, schema=schema(), candidates=('c1', 'c0'))
    assert validate_structure_worker_reply(selector, req, selector.propose_local(prompt)) == [hypothesis]
    assert validate_selector_reply(selector, selector.select(selection_prompt), schema(), ('c1', 'c0')).selected == ('c0',)
    before = path.read_bytes()
    terminal = [r['payload'] for r in JournalChannel(path).scan_unprocessed(0)
                if r['payload'].get('state') == 'RECEIVED']
    assert [r['raw_response'] for r in terminal] == [raw, '2\n']
    replay_backend = ScriptedBackend([])
    replay = RealBackendSelector(replay_backend, journal=JournalChannel(path))
    replay.start_run('frozen-run')
    assert replay.propose_local(prompt) == raw
    assert replay.select(selection_prompt) == '2\n'
    assert replay_backend.calls == [] and path.read_bytes() == before
    legacy = RealBackendSelector(replay_backend, journal=JournalChannel(path),
        structure_reply_format='JSON_V1', selection_reply_format='JSON_V1')
    legacy.start_run('frozen-run')
    with pytest.raises(IntegrityError, match='REPLAY_MISMATCH'):
        legacy.propose_local(prompt)
    assert replay_backend.calls == [] and path.read_bytes() == before
    child = replay.for_run('separate-run')
    assert child.structure_reply_format == 'TP-C2' and child.selection_reply_format == 'SELECT_LABELS_V1'


def test_explicitly_pinned_c1_history_replays_without_c2_guessing(tmp_path):
    req = StructureProposalRequest('fixture', 'frozen', ('source:0', 'source:1'),
        allowed_node_kinds=frozenset({'PREDICATE', 'ENTITY'}),
        allowed_edge_kinds=frozenset({'ARGUMENT'}),
        allowed_role_ids=frozenset({'SUBJECT'}))
    hypothesis = Hypothesis('h0', (TNode('PREDICATE', ('source:1',)),
        TNode('ENTITY', ('source:0',))), (TEdge('ARGUMENT', 0, 1, 'SUBJECT'),),
        alignment=req.source_spans)
    raw = serialize_compact_structure_reply(req, [hypothesis]) + '\n'
    path = tmp_path / 'c1-provider.log'
    writer = RealBackendSelector(ScriptedBackend([raw]), journal=JournalChannel(path),
        structure_reply_format='TP-C1')
    writer.start_run('c1-frozen-run')
    prompt = build_structure_worker_prompt(writer, req, [])
    assert validate_structure_worker_reply(writer, req, writer.propose_local(prompt)) == [hypothesis]
    before = path.read_bytes()
    backend = ScriptedBackend([])
    replay = RealBackendSelector(backend, journal=JournalChannel(path), structure_reply_format='TP-C1')
    replay.start_run('c1-frozen-run')
    assert replay.propose_local(prompt) == raw
    assert validate_structure_worker_reply(replay, req, raw) == [hypothesis]
    c2 = RealBackendSelector(backend, journal=JournalChannel(path))
    c2.start_run('c1-frozen-run')
    with pytest.raises(IntegrityError, match='REPLAY_MISMATCH'):
        c2.propose_local(prompt)
    with pytest.raises(ProtocolError):
        validate_structure_worker_reply(c2, req, raw)
    assert backend.calls == [] and path.read_bytes() == before


def test_default_native_compact_proposal_commits_scoped_root(monkeypatch, tmp_path):
    replies = []

    def generate(self, prompt, **kwargs):
        payload, req = request_from_payload(prompt)
        bytext = {token['text']: token['id'] for token in payload['tokens']}
        hypothesis = Hypothesis('h0', (TNode('NOT', (bytext['не'],)),
            TNode('PREDICATE', (bytext['вошёл'],)), TNode('ENTITY', (bytext['Иван'],))),
            (TEdge('OPERAND', 0, 1, scope=True), TEdge('ARGUMENT', 1, 2, 'SUBJECT')),
            alignment=req.source_spans)
        assert payload['protocol'] == 'TP-C2'
        raw = serialize_readable_structure_reply(req, [hypothesis])
        replies.append(raw)
        return raw

    monkeypatch.setattr(ChatBackend, 'generate', generate)
    text = 'Иван не вошёл.'
    payload = {'raw_input': {'text': text, 'source_id': 'compact-native', 'revision': 1,
        'range': [0, len(text)], 'language': 'ru', 'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    session = Session([payload], tmp_path / 'native.log')
    actual = execute_native(session, payload, {'provider': 'lmstudio', 'model': 'compact-fixture'})
    assert actual['assertions']['ah'] == [{'operator': 'NOT', 'operands': [
        {'predicate': 'ENTER', 'roles': {'AGENT': {'entity': 'ivan'}}}]}], actual['diagnostics']
    assert actual['runtime']['provider_call_count'] == 1
    records = [r['payload'] for r in session.store._journal.scan_unprocessed(0)
               if r['payload'].get('state') == 'RECEIVED']
    assert [r['raw_response'] for r in records] == replies
    assert all(not raw.startswith('{') for raw in replies)


def test_default_rejects_legacy_json_without_fallback_but_records_it(monkeypatch, tmp_path):
    raw = '{"hypotheses": []}'
    monkeypatch.setattr(ChatBackend, 'generate', lambda self, prompt, **kwargs: raw)
    text = 'Иван не вошёл.'
    payload = {'raw_input': {'text': text, 'source_id': 'wrong-wire', 'revision': 1,
        'range': [0, len(text)], 'language': 'ru', 'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    session = Session([payload], tmp_path / 'wrong.log')
    actual = execute_native(session, payload, {'provider': 'lmstudio', 'model': 'compact-fixture'})
    assert actual['assertions']['ah'] == []
    assert 'PROPOSAL_INVALID' in actual['diagnostics']['codes']
    received = [r['payload'] for r in session.store._journal.scan_unprocessed(0)
                if r['payload'].get('state') == 'RECEIVED']
    assert len(received) == 1 and received[0]['raw_response'] == raw
    selector = RealBackendSelector(ScriptedBackend([]))
    with pytest.raises(ProtocolError):
        validate_selector_reply(selector, '{"outcome":"ONE_SELECTED","selected":["c0"]}', schema(), ('c0', 'c1'))
