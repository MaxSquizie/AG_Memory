"""Live V7 observability is separate from normal chat and gold evaluation."""
import json
from types import SimpleNamespace
import pytest

from ah.gui.formalizer_diagnostics import OracleDiagnostics, diagnostic_json, format_formalizer_requests
from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.run_binding import InterpretationRunBinding
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import fixture


def progress(name, seq, **fields):
    return {'schema_version': 'v7-oracle-progress-1', 'event': name, 'seq': seq,
            'case_id': 'actual-case', **fields}


def test_request_started_is_visible_before_result_and_counter_is_independent():
    view = OracleDiagnostics()
    row = progress('request_started', 1, request_id='r1', role='formalizer',
                   prompt='actual bounded prompt', system='actual system')
    assert view.update(row)
    assert 'IN FLIGHT' in view.raw_text()
    assert 'actual bounded prompt' in view.raw_text()
    assert view.requests_started == 1
    assert not view.update(row)
    assert view.requests_started == 1
    assert view.requests_finished == 0
    view.update(progress('request_finished', 2, request_id='r1', response='actual response',
                         status='SUCCESS', requests_started=1, requests_finished=1))
    assert 'actual bounded prompt' in view.raw_text()
    assert 'actual response' in view.raw_text()
    assert view.requests_started == view.requests_finished == 1
    view.update(progress('case_started', 3, case_id='next-case'))
    assert 'actual response' not in view.raw_text()
    assert view.requests_started == view.requests_finished == 1


def test_progress_keeps_only_real_checkpoint_and_bounded_history():
    view = OracleDiagnostics()
    for seq in range(1, 91):
        view.update(progress('step_finished', seq, step_id=str(seq),
                             checkpoint={'diagnostics': ['real-diagnostic'], 'actual': seq}))
    exported = json.loads(view.ir_text())
    assert len(exported['case_checkpoints']) == 64
    assert exported['case_checkpoints'][-1]['checkpoint']['actual'] == 90
    assert 'forbidden_conclusions' not in exported
    view.update(progress('case_started', 91, case_id='next-case'))
    assert not json.loads(view.ir_text())['case_checkpoints']
    assert len(view.events) == 64
    assert not view.update(progress('request_started', 1, request_id='obsolete'))
    assert view.requests_started == 0


def test_request_error_never_synthesizes_an_output():
    view = OracleDiagnostics()
    view.update(progress('request_started', 1, request_id='r1', prompt='P'))
    view.update(progress('request_finished', 2, request_id='r1', status='ERROR', error='Timeout'))
    assert view.requests_failed == 1
    assert 'Timeout' in view.raw_text()
    assert 'VISIBLE MODEL RESPONSE' not in view.raw_text()


def test_normal_bounded_calls_are_raw_and_agent_calls_are_not_parser_calls():
    agent = SimpleNamespace(sequence=1, role='agent', prompt='agent prompt', response_text='agent reply')
    active = SimpleNamespace(sequence=2, role='formalizer', prompt='bounded JSON', system='S')
    text = format_formalizer_requests([agent], active, source_text='Мария спит')
    assert 'bounded JSON' in text and 'IN FLIGHT' in text
    assert 'agent prompt' not in text and 'agent reply' not in text
    assert 'waiting for response' in text
    assert json.loads(diagnostic_json({'set': frozenset({'b', 'a'})})) == {'set': ['a', 'b']}


class BoundedFixtureBackend:
    def generate(self, prompt, **kwargs):
        data = json.loads(prompt)
        anchors = {t['text']: t['id'] for t in data['tokens']}
        return json.dumps({'hypotheses': [{'local_id': 'native-gui-fixture',
            'nodes': [{'kind': 'PREDICATE', 'anchor_spans': [anchors['спит']]},
                      {'kind': 'ENTITY', 'anchor_spans': [anchors['Мария']]}],
            'edges': [{'kind': 'ARGUMENT', 'from': 0, 'to': 1, 'role_id': 'SUBJECT'}],
            'alignment': list(anchors.values())}]}, ensure_ascii=False)


def test_native_diagnostic_snapshot_contains_actual_ir_and_receipt_without_aliasing(tmp_path):
    session = Session([], tmp_path / 'native.log')
    release, _ = fixture(session.core, 'known')
    selector = RealBackendSelector(BoundedFixtureBackend(), journal=session.store._journal)
    adapter = FormalizerAdapter(selector, store=session.store,
        binding=InterpretationRunBinding(session.store._journal), release=release)
    assert adapter.diagnostic_snapshot() is None
    text = 'Мария спит.'
    receipt = adapter.interpret(text, raw_input={'source_id': 'gui-diagnostic', 'text': text,
        'range': [0, len(text)], 'source_revision': 1, 'language': 'ru'})
    snap = adapter.diagnostic_snapshot()
    assert snap['source_text'] == text
    assert snap['commit_receipt']['terminal'] == receipt.terminal == 'APPLIED'
    assert snap['commit_receipt']['node_refs'] == receipt.node_refs
    assert snap['state']['frames']
    assert snap['state']['decisions']
    assert snap['interpretation_report']['observation_id'] == receipt.observation_id
    assert 'perception' not in snap['commit_receipt']
    snap['state']['frames'].clear()
    assert adapter.diagnostic_snapshot()['state']['frames']


@pytest.mark.parametrize('conversion', ['asdict', 'deepcopy'])
def test_diagnostic_conversion_failure_cannot_fail_successful_native_commit(tmp_path, monkeypatch, conversion):
    import ah.formalizer.runtime_adapter as runtime
    session = Session([], tmp_path / (conversion + '.log'))
    release, _ = fixture(session.core, 'known')
    adapter = FormalizerAdapter(RealBackendSelector(BoundedFixtureBackend(), journal=session.store._journal),
        store=session.store, binding=InterpretationRunBinding(session.store._journal), release=release)
    text = 'Мария спит.'
    def fail_observer(*args, **kwargs):
        raise RuntimeError('observer conversion failed')
    with monkeypatch.context() as patch:
        patch.setattr(runtime, conversion, fail_observer)
        receipt = adapter.interpret(text, raw_input={'source_id': 'observer-fault', 'text': text,
            'range': [0, len(text)], 'source_revision': 1, 'language': 'ru'})
    assert receipt.terminal == 'APPLIED' and receipt.applied
    assert receipt.node_refs
    assert set(receipt.node_refs) <= session.store.ledger.f_visible()
    # Observation failure is confined to the UI artifact, not the result or WAL.
    snapshot = adapter.diagnostic_snapshot()
    assert snapshot['commit_receipt']['terminal'] == 'APPLIED'
    assert snapshot['commit_receipt']['batch_hash'] == receipt.batch_hash
    assert snapshot['diagnostic_error'] == {'type': 'RuntimeError', 'message': 'observer conversion failed'}
    assert 'observer conversion failed' not in receipt.diagnostics
    rows = session.store._journal.scan_unprocessed(0)
    assert not any('observer conversion failed' in str(row) for row in rows)
    assert adapter.diagnostic_sequence() == snapshot['sequence'] == 1
