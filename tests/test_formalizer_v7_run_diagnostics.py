"""Inspect actual native/provider evidence without gold or final run reports."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from tools.formalizer_v7_run_diagnostics import case_diagnostics, inspect_run


def actual(case_id='case', diagnostics=None):
    return {'case_id': case_id, 'execution_status': 'EXECUTED', 'checkpoints': [
        {'step_id': 'native', 'actual': {'runtime': {'ir': {'diagnostics': diagnostics or []},
            'report': {'terminal': 'RESOLUTION_ONLY', 't5_eligibility': 'FRAGMENT_UNRESOLVED'}}}}]}


def wal(root, case_id, rows):
    digest = hashlib.sha256(json.dumps(case_id, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    path = root / 'cases' / digest / 'journal.log'
    path.parent.mkdir(parents=True)
    path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows), encoding='utf-8')
    return path


def test_actual_native_error_details_survive_without_guessed_stage_or_gold():
    result = actual(diagnostics=[{'code': 'PROPOSAL_INVALID', 'detail': 'TP_REPLY_SHAPE: unexpected field'}])
    observed = case_diagnostics(result)
    first = observed['first_observed_issue']
    assert first['code'] == 'PROPOSAL_INVALID'
    assert first['detail'] == 'TP_REPLY_SHAPE: unexpected field'
    assert first['stage'] == 'NOT_RECORDED'
    assert first['path'] == '/checkpoints/0/actual/runtime/ir/diagnostics/0'
    assert first['step_id'] == 'native'
    assert observed['native_reports'][0]['terminal'] == 'RESOLUTION_ONLY'
    assert observed['causal_attribution'] == 'NOT_INFERRED'
    assert 'expected' not in observed and 'checks' not in observed


def test_provider_failed_wal_has_exact_message_and_explicit_tp_request_stage(tmp_path):
    path = wal(tmp_path, 'case', [{'seq': 2, 'payload': {'kind': 'prov_call', 'state': 'FAILED',
        'id': 'R:backend:1:1', 'provider': 'ChatBackend', 'ordinal': 1, 'attempt': 1,
        'prompt': json.dumps({'request': {'request_id': 'TP:obs'}}),
        'error': 'HTTP 400: unsupported reasoning setting'}}])
    before = path.read_bytes()
    observed = case_diagnostics(actual(), wal_path=path)
    assert observed['first_observed_issue']['kind'] == 'PROVIDER_ERROR'
    assert observed['provider_errors'][0]['error'] == 'HTTP 400: unsupported reasoning setting'
    assert observed['provider_errors'][0]['stage'] == 'TP'
    assert observed['provider_errors'][0]['stage_evidence'] == 'provider prompt /request/request_id'
    assert path.read_bytes() == before


def test_received_wal_reply_preview_is_actual_and_bounded_without_gold(tmp_path):
    reply = '```json\n{"nodes":[{"id":"n0"}],"missing":"alignment"}\n```' + ' ' * 2000
    path = wal(tmp_path, 'case', [{'seq': 2, 'payload': {'kind': 'prov_call', 'state': 'RECEIVED',
        'id': 'R:backend:1:1', 'ordinal': 1,
        'prompt': json.dumps({'request': {'request_id': 'TP:obs'}}), 'raw_response': reply}}])
    before = path.read_bytes()
    observed = case_diagnostics(actual(), wal_path=path)
    preview = observed['provider_replies'][0]
    assert preview['response'] == reply[:1600]
    assert preview['response_chars'] == len(reply) and preview['truncated']
    assert preview['stage'] == 'TP'
    assert preview['response_sha256'] == hashlib.sha256(reply.encode()).hexdigest()
    assert observed['provider_reply_record_count'] == 1
    assert observed['first_observed_issue'] is None  # Receipt alone is not an error.
    assert path.read_bytes() == before


def test_interrupted_run_keeps_complete_actual_rows_and_pending_case_error(tmp_path):
    first = actual('completed', [{'code': 'PROPOSAL_INVALID', 'detail': 'missing hypotheses'}])
    (tmp_path / 'actual.jsonl').write_text(json.dumps(first) + '\n{"case_id":', encoding='utf-8')
    progress = [{'event': 'case_finished', 'case_id': 'completed', 'status': 'FAIL'},
        {'event': 'case_started', 'case_id': 'pending'},
        {'event': 'request_started', 'case_id': 'pending', 'request_id': 'HTTP', 'step_id': 'formalize'},
        {'event': 'request_finished', 'case_id': 'pending', 'request_id': 'HTTP',
         'status': 'ERROR', 'error': 'Timeout', 'http_status': None}]
    (tmp_path / 'progress.jsonl').write_text('\n'.join(map(json.dumps, progress)), encoding='utf-8')
    result = inspect_run(tmp_path)
    assert result['completion'] == 'FINAL_EVENT_NOT_RECORDED'
    assert result['cases_observed'] == 2 and result['cases_with_actual_record'] == 1
    assert result['recorded_status_counts'] == {'FAIL': 1, 'INCOMPLETE': 1}
    assert result['cases_with_provider_errors'] == 1
    assert result['cases'][1]['provider_errors'][0]['error'] == 'Timeout'
    assert result['artifact_warnings']
    assert not result['comparison_or_gates_re_evaluated']


def test_archive_and_bounded_details_are_read_only_with_all_case_totals(tmp_path):
    rows = [actual('c' + str(i), [{'code': 'CODE', 'detail': 'x' * 5000}]) for i in range(3)]
    archive = tmp_path / 'actual.jsonl.gz'
    archive.write_bytes(gzip.compress(('\n'.join(map(json.dumps, rows)) + '\n').encode()))
    before = archive.read_bytes()
    result = inspect_run(tmp_path, limit=1)
    assert result['cases_observed'] == 3 and result['omitted_cases'] == 2
    assert len(result['cases']) == 1
    assert result['first_issue_case_counts'] == {'CODE': 3}
    assert len(result['cases'][0]['native_diagnostics'][0]['detail']) == 1600
    assert archive.read_bytes() == before
    # Plain interrupted data is authoritative even when a partial archive exists.
    (tmp_path / 'actual.jsonl').write_text(json.dumps(actual('plain')), encoding='utf-8')
    archive.write_bytes(b'broken-gzip')
    assert inspect_run(tmp_path)['cases'][0]['case_id'] == 'plain'


def test_cli_needs_no_corpus_no_runtime_import_and_no_final_summary(tmp_path):
    (tmp_path / 'actual.jsonl').write_text(json.dumps(actual('local')), encoding='utf-8')
    script = Path(__file__).resolve().parents[1] / 'tools/formalizer_v7_run_diagnostics.py'
    command = subprocess.run([sys.executable, str(script), str(tmp_path), '--limit', '1'],
        cwd=tmp_path, capture_output=True, text=True, check=True)
    result = json.loads(command.stdout)
    assert result['cases_observed'] == 1
    assert result['completion'] == 'FINAL_EVENT_NOT_RECORDED'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['actual.jsonl']
