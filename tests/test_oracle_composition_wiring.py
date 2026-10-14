"""The GUI oracle command must reach closed probes over the actual HTTP route."""
import gzip
import json
from pathlib import Path
import subprocess
import sys
import pytest

from ah.config import load_config
from ah.core import AHCore
from ah.formalizer.resources.loader import ResourceRelease
from tools.formalizer_component_fixture import with_full_composition
from tools.formalizer_v7_native_binding import fixture
from tools.formalizer_v7_native_binding import execute_native, ChatBackend
from tools.formalizer_v7_extended_binding import Session
from tools.prepare_formalizer_v7_gui import prepare
from test_formalizer_v7_gui_fixture import source_config
from test_formalizer_v7_oracle_transport import local_server

ROOT = Path(__file__).resolve().parents[1]


def test_gui_and_oracle_share_composition_release(tmp_path):
    cfg = load_config(prepare(source_config(tmp_path), tmp_path/'gui', profile='composition'))
    reviews = json.loads((cfg.paths.data_dir/cfg.formalizer.review_records_filename).read_text())
    gui = ResourceRelease.load(cfg.paths.data_dir/cfg.formalizer.resource_release_filename,
                               trusted_reviews=reviews)
    core = AHCore()
    release, _ = fixture(core, 'known')
    oracle = with_full_composition(release, core=core)
    oracle.validate_store(core.store)
    assert oracle.sha256 == gui.sha256


def test_oracle_cli_sends_closed_probes_and_replays_without_http(tmp_path):
    live = tmp_path/'live'
    response = {'output': [{'type': 'message', 'content': '?'}]}
    # '?' explicitly refuses selection: this verifies wiring, never fabricates
    # an expected graph or claims that the original oracle cases now pass.
    with local_server(response) as (url, requests):
        command = [sys.executable, str(ROOT/'tools/run_formalizer_v7_oracle.py'),
                   '--provider', 'lmstudio', '--base-url', url, '--model', 'test',
                   '--case', 'A01', '--case', 'A02', '--out', str(live)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    assert len(requests) == 2
    assert all(r['path'] == '/api/v1/chat' for r in requests)
    assert all('SELECT_LABELS_V1' in r['body']['input'] for r in requests)
    provenance = json.loads((live/'provenance.json').read_text())
    assert provenance['received_provider_calls'] == 2 and provenance['model_live_execution']
    assert 'tools/formalizer_component_fixture.py' in provenance['source_snapshot']
    traces = [json.loads(line) for line in gzip.decompress((live/'actual.jsonl.gz').read_bytes()).splitlines()]
    assert len(traces) == 2
    for trace in traces:
        actual = trace['checkpoints'][0]['actual']
        assert actual['runtime']['provider_call_count'] == 1
        assert actual['runtime']['probe_configuration']['composition_enabled']
        assert actual['assertions']['ah'] == []
    # The server is now closed. Replay must use the recorded closed answers.
    replay = tmp_path/'replay'
    result = subprocess.run([sys.executable, str(ROOT/'tools/run_formalizer_v7_oracle.py'),
        '--provider', 'replay', '--replay-from', str(live), '--out', str(replay)],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads((live/'comparison.json').read_text()) == json.loads((replay/'comparison.json').read_text())


def test_operator_introducers_and_finite_content_pass_existing_oracle_checks(tmp_path):
    with local_server({'output': [{'type': 'message', 'content': '1'}]}) as (url, requests):
        result = subprocess.run([sys.executable, str(ROOT/'tools/run_formalizer_v7_oracle.py'),
            '--provider', 'lmstudio', '--base-url', url, '--model', 'test',
            '--case', 'A01', '--case', 'A12', '--case', 'LANG-00-0-not', '--out', str(tmp_path/'run')],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(requests) == 3
    for request in requests:
        prompt = request['body']['input']
        assert 'ONE_SELECTED' not in prompt and 'MULTIPLE_ADMISSIBLE' not in prompt
    comparison = json.loads((tmp_path/'run/comparison.json').read_text())
    assert comparison['passed_cases'] == 3


def test_invalid_component_reply_is_retained_for_manual_review(tmp_path, monkeypatch):
    monkeypatch.setattr(ChatBackend, 'generate', lambda *args, **kwargs: 'ONE_SELECTED')
    text = 'Возможно, Иван пришёл.'
    payload = {'raw_input': {'text': text, 'source_id': 'invalid-reply', 'revision': 1,
        'range': [0, len(text)], 'language': 'ru', 'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    result = execute_native(Session([payload], tmp_path/'journal.log'), payload,
        {'provider': 'lmstudio', 'model': 'test', 'structure_mode': 'region_probes'})
    decisions = result['runtime']['ir']['decisions'].values()
    failed = [d for d in decisions if any(h.get('kind')=='PROBE_FAILURE' for h in d['history'])]
    assert len(failed) == 1
    assert failed[0]['raw_response'] == 'ONE_SELECTED'
    assert 'SELECT_LABELS_V1' in failed[0]['last_prompt']
    assert not failed[0]['selected'] and failed[0]['outcome'] == 'UNRESOLVED'
    assert result['assertions']['ah'] == []


@pytest.mark.parametrize('text,operator', [
    ('Возможно, что Иван пришёл.', 'POSSIBLE'),
    ('Возможно что Иван пришёл.', 'POSSIBLE'),
    ('Неверно, Иван пришёл.', 'NOT'),
])
def test_declared_introducer_owns_only_its_tokens(tmp_path, monkeypatch, text, operator):
    monkeypatch.setattr(ChatBackend, 'generate', lambda *args, **kwargs: '1')
    payload = {'raw_input': {'text': text, 'source_id': 'intro', 'revision': 1,
        'range': [0, len(text)], 'language': 'ru', 'request_kind': 'ASSERTION', 'batch_kind': 'MESSAGE'}}
    result = execute_native(Session([payload], tmp_path/'journal.log'), payload,
        {'provider': 'lmstudio', 'model': 'test', 'structure_mode': 'region_probes'})
    assert result['diagnostics']['codes'] == []
    assert result['assertions']['ah'] == [{'operator': operator, 'operands': [
        {'predicate': 'ARRIVE', 'roles': {'AGENT': {'entity': 'ivan'}}}]}]
