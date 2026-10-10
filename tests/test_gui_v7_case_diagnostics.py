"""Real Qt chat shows runtime evidence next to unchanged oracle mismatches."""
from html import escape
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QTextEdit
from PySide6.QtCore import QProcess
from ah.gui.oracle_progress_state import OracleOutputParser
from ah.gui.semantic_test_window import MainWindow
from tools.formalizer_v7_run_diagnostics import case_diagnostics


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def display(qapp, event):
    history = QTextEdit()
    target = SimpleNamespace(_oracle_output_parser=OracleOutputParser(),
        _oracle_progress=SimpleNamespace(apply=lambda e: True),
        llm_panel=SimpleNamespace(set_oracle_progress=lambda e: None),
        _semantic_process_output=[], chat_history=history, _html=escape,
        _refresh_oracle_progress=lambda: None)
    data = ('V7_PROGRESS ' + json.dumps(event, ensure_ascii=False) + '\n').encode()
    MainWindow._consume_oracle_output(target, data)
    return history.toPlainText()


def test_runtime_error_visible_beside_mismatch_and_html_escaped(qapp):
    native = case_diagnostics({'case_id': 'C', 'checkpoints': [{'step_id': 'TP', 'actual': {
        'runtime': {'ir': {'diagnostics': [{'code': 'PROPOSAL_INVALID',
            'detail': 'TP_REPLY_SHAPE: missing alignment <script>'}]},
            'report': {'terminal': 'RESOLUTION_ONLY'}}}}]})
    text = display(qapp, {'schema_version': 'v7-oracle-progress-1', 'event': 'case_finished',
        'seq': 1, 'case_id': 'C', 'status': 'FAIL', 'errors': [{'path': '/assertions/ah', 'observed': []}],
        'first_observed_text': native['first_observed_text'],
        'native_diagnostic_text': native['native_diagnostic_text'], 'runtime_diagnostics': native})
    assert 'C: FAIL' in text
    assert 'PROPOSAL_INVALID' in text and 'missing alignment <script>' in text
    assert 'Сверка:' in text and '/assertions/ah' in text
    assert 'RESOLUTION_ONLY' not in text or 'PASS' not in text


def test_success_has_no_spurious_missing_cause_warning(qapp):
    native = case_diagnostics({'case_id': 'C', 'checkpoints': []})
    text = display(qapp, {'schema_version': 'v7-oracle-progress-1', 'event': 'case_finished',
        'seq': 1, 'case_id': 'C', 'status': 'PASS', 'first_observed_text': native['first_observed_text']})
    assert 'C: PASS' in text
    assert 'Runtime:' not in text and 'не записана' not in text


def test_first_issue_text_survives_truncated_large_diagnostics(qapp):
    text = display(qapp, {'schema_version': 'v7-oracle-progress-1', 'event': 'case_finished',
        'seq': 1, 'case_id': 'C', 'status': 'FAIL', 'runtime_diagnostics': '<preview>',
        'first_observed_text': 'Записанная ошибка провайдера [TP]: HTTP 403'})
    assert 'HTTP 403' in text and '[TP]' in text


def test_cancelled_gui_writer_preserves_completed_case_and_same_report_on_screen(qapp, tmp_path):
    (tmp_path / 'progress.jsonl').write_text('\n'.join(json.dumps(e) for e in [
        {'schema_version': 'v7-oracle-progress-1', 'seq': 1, 'event': 'run_started',
            'total': 2, 'provider_config': {'provider': 'lmstudio', 'model': 'local', 'base_url': 'http://localhost:1234'}},
        {'schema_version': 'v7-oracle-progress-1', 'seq': 2, 'event': 'case_finished',
            'case_id': 'A', 'status': 'PASS'},
        {'schema_version': 'v7-oracle-progress-1', 'seq': 3, 'event': 'case_started', 'case_id': 'B'},
    ]), encoding='utf-8')
    history = QTextEdit()
    finished_status = []
    target = SimpleNamespace(_oracle_closing=False, _oracle_model_output=lambda: None,
        _consume_oracle_output=lambda *args, **kwargs: None, _oracle_out_dir=tmp_path,
        _oracle_progress=SimpleNamespace(finished=False), _oracle_cancelled=True,
        chat_history=history, _html=escape, _release_oracle=finished_status.append)
    MainWindow._oracle_model_finished(target, -15, QProcess.ExitStatus.CrashExit)
    assert finished_status == ['CANCELLED']
    stats = json.loads((tmp_path / 'gui_stats.json').read_text())
    assert stats['status'] == 'INCOMPLETE' and stats['gui_status'] == 'CANCELLED'
    assert stats['totals']['passed'] == 1 and stats['totals']['failed'] == 0
    assert stats['non_passing_cases'][0]['case_id'] == 'B'
    text = history.toPlainText()
    assert 'GUI process status: CANCELLED' in text
    assert 'passed=1  failed=0' in text
    assert 'A: INCOMPLETE' not in text
    assert 'GUI process status: CANCELLED' in (tmp_path / 'gui_report.md').read_text()
