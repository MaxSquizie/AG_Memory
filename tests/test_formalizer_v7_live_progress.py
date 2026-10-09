"""Live progress reports real calls and strict comparison before final artifacts."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
import json
import os
import queue
import subprocess
import sys
import time

from tools import check_formalizer_v7_oracle as checker
from tools import formalizer_v7_progress as progress
from tools.run_formalizer_v7_oracle import main


ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_progress_context_flush_bounded_preview_and_real_request_counts(tmp_path, capsys):
    path = tmp_path / 'progress.jsonl'
    progress.configure(path, stdout=True)
    try:
        with progress.context(case_id='case', step_id='s1', action='formalize'):
            progress.emit('request_started', prompt='я' * 5000, provider='openai')
            # A consumer can read the record while the operation is incomplete.
            first = rows(path)[0]
            assert first['requests_started'] == 1
            assert first['requests_finished'] == 0
            assert first['case_id'] == 'case' and first['step_id'] == 's1'
            assert len(first['prompt']) == progress.PREVIEW_LIMIT
            assert first['prompt_truncated'] and first['prompt_chars'] == 5000
            progress.emit('request_finished', status='ERROR', error='HTTP 500', elapsed_seconds=0.25)
        progress.emit('run_finished', status='FAIL')
        events = rows(path)
        assert [r['seq'] for r in events] == [1, 2, 3]
        assert events[1]['request_elapsed_seconds'] == 0.25
        assert events[1]['requests_finished'] == events[1]['requests_failed'] == 1
        assert 'case_id' not in events[-1]
        assert all(line.startswith(progress.PREFIX) for line in capsys.readouterr().out.splitlines())
    finally:
        progress.close()


def test_completed_case_progress_uses_final_comparator_and_never_exec_ok_as_pass(tmp_path, capsys):
    out = tmp_path / 'run'
    assert main(['--provider', 'disabled', '--case', 'A04', '--case', 'DSL-EQUIVALENCE',
                 '--case', 'LANG-00-0-bare', '--progress-jsonl', '--out', str(out)]) == 1
    events = rows(out / 'progress.jsonl')
    finished = [e for e in events if e['event'] == 'case_finished']
    report = checker.readjson(out / 'comparison.json')
    assert [(e['case_id'], e['status'], e['errors']) for e in finished] == [
        (e['case_id'], e['status'], e['errors']) for e in report['results']]
    assert finished[-1]['completed'] == finished[-1]['total'] == 3
    assert finished[-1]['passed'] == report['passed_cases']
    assert finished[-1]['failed'] == report['failed_cases']
    assert finished[-1]['blocked'] == report['blocked_cases']
    assert any(e['status'] == 'FAIL' and e['execution_status'] == 'EXECUTED' for e in finished)
    assert events[0]['event'] == 'run_started' and events[-1]['event'] == 'run_finished'
    assert any(e['event'] == 'step_finished' and e['status'] == 'OBSERVED' and 'actual' in e for e in events)
    stdout_events = [json.loads(line[len(progress.PREFIX):]) for line in capsys.readouterr().out.splitlines()
                     if line.startswith(progress.PREFIX)]
    assert stdout_events == events


def test_large_checkpoint_event_is_bounded_without_losing_identity_or_counts(tmp_path):
    path = tmp_path / 'large.jsonl'
    progress.configure(path)
    try:
        with progress.context(case_id='large', step_id='commit', action='snapshot'):
            progress.emit('step_finished', status='OBSERVED',
                actual={'entries': [{'value': 'я' * 4000} for _ in range(64)]})
        line = path.read_bytes().splitlines()[0]
        assert len(line) <= progress.EVENT_LIMIT
        event = json.loads(line)
        assert event['case_id'] == 'large' and event['step_id'] == 'commit'
        assert event['actual_truncated'] is True
        assert event['requests_started'] == 0
    finally:
        progress.close()


def test_plain_cli_preserves_text_stdout_and_still_persists_events(tmp_path, capsys):
    out = tmp_path / 'plain'
    assert main(['--case', 'A04', '--out', str(out)]) == 0
    assert progress.PREFIX not in capsys.readouterr().out
    assert rows(out / 'progress.jsonl')[-1]['event'] == 'run_finished'


def test_pure_case_comparator_keeps_missing_observations_and_invalid_stimulus_failures():
    case = {'case_id': 'independent', 'steps': [{'id': 's1', 'checks': [
        {'path': '/answer', 'op': 'eq', 'value': 'UNKNOWN'}]}]}
    binding = {'api_refs': ['actual_api']}
    trace = {'schema_version': 'v7-oracle-trace-1', 'case_id': 'independent',
             'execution_status': 'EXECUTED', 'checkpoints': [{'step_id': 's1', 'actual': {}}],
             'binding_manifest': binding,
             'binding_manifest_ref': __import__('hashlib').sha256(checker.canonical(binding).encode()).hexdigest()}
    assert checker.compare_case(case, trace)['status'] == 'FAIL'
    trace['checkpoints'][0]['actual'] = {'answer': 'UNKNOWN'}
    assert checker.compare_case(case, trace)['status'] == 'PASS'
    trace['checkpoints'][0]['actual']['stimulus'] = {'baseline_valid': False, 'baseline_error': 'invalid'}
    assert checker.compare_case(case, trace)['status'] == 'FAIL'


def test_progress_reaches_stdout_and_disk_before_blocking_http_response(tmp_path):
    arrived, release = Event(), Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            arrived.set()
            assert release.wait(10), 'test consumer failed to release bounded provider'
            prompt = request['messages'][-1]['content']
            if prompt.startswith('{'):
                tokens = json.loads(prompt)['tokens']
                anchors = {t['text']: t['id'] for t in tokens}
                reply = {'hypotheses': [{'local_id': 'independent-enter-fixture',
                    'nodes': [{'kind': 'PREDICATE', 'anchor_spans': [anchors['вошёл']]},
                              {'kind': 'ENTITY', 'anchor_spans': [anchors['Иван']]}],
                    'edges': [{'kind': 'ARGUMENT', 'from': 0, 'to': 1, 'role_id': 'SUBJECT'}],
                    'alignment': list(anchors.values())}]}
            else:
                lines = prompt.split('closed set):\n', 1)[1].split('\nTask:', 1)[0].splitlines()
                reply = {'outcome': 'ONE_SELECTED', 'selected': [
                    line.split('. ', 1)[0] for line in lines if '. ' in line and 'ENTER' in line][:1]}
            raw = json.dumps({'choices': [{'message': {'content': json.dumps(reply)}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = tmp_path / 'http-live'
    proc = subprocess.Popen([sys.executable, str(ROOT / 'tools/run_formalizer_v7_oracle.py'),
        '--provider', 'openai', '--base-url', f'http://127.0.0.1:{server.server_port}',
        '--model', 'independent-blocking-fixture', '--timeout', '15', '--case', 'LANG-00-0-bare',
        '--progress-jsonl', '--out', str(output)], cwd=ROOT,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding='utf-8')
    lines = queue.Queue()
    reader = Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True)
    reader.start()
    seen = []
    try:
        assert arrived.wait(15), 'HTTP request did not start'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
            if line.startswith(progress.PREFIX):
                seen.append(json.loads(line[len(progress.PREFIX):]))
                if seen[-1]['event'] == 'request_started':
                    break
        assert seen[-1]['event'] == 'request_started'
        assert seen[-1]['case_id'] == 'LANG-00-0-bare'
        assert seen[-1]['step_id'] and seen[-1]['requests_started'] == 1
        assert seen[-1]['requests_finished'] == 0
        assert not release.is_set() and proc.poll() is None
        persisted = rows(output / 'progress.jsonl')
        assert any(e['event'] == 'request_started' for e in persisted)
        assert not any(e['event'] == 'request_finished' for e in persisted)
        release.set()
        assert proc.wait(timeout=30) == 0, proc.stderr.read()
        reader.join(timeout=5)
        final = rows(output / 'progress.jsonl')
        assert final[-1]['event'] == 'run_finished' and final[-1]['passed'] == 1
        assert final[-1]['requests_started'] == final[-1]['requests_finished'] >= 1
    finally:
        release.set()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_plan_partial_tuple_observation_has_identical_live_and_final_results(tmp_path):
    # This real store partial-commit case exposes tuples in memory. The oracle
    # schema represents arrays as JSON lists; live comparison must use the
    # persisted representation, exactly like the final checker.
    out = tmp_path / 'partial-plan'
    assert main(['--provider', 'disabled', '--case', 'PLAN-E-SHARED', '--out', str(out)]) == 0
    events = rows(out / 'progress.jsonl')
    final = checker.readjson(out / 'comparison.json')
    case = next(e for e in events if e['event'] == 'case_finished')
    assert case['status'] == final['results'][0]['status'] == 'PASS'
    assert case['errors'] == final['results'][0]['errors'] == []
    assert events[-1]['passed'] == final['passed_cases'] == 1
    assert events[-1]['failed'] == final['failed_cases'] == 0
