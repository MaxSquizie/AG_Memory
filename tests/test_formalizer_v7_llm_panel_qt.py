"""Actual Qt panel: no adaptive controls; external oracle data survive polling."""
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from ah.config import load_config
from ah.gui.llm_panel import LLMControlWidget


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def services(tmp_path):
    config = tmp_path / 'gui.toml'
    config.write_text('[llm]\nenabled=false\n[paths]\nagent_prompt_path="agent.txt"\n')
    return SimpleNamespace(config=load_config(config), llm=None, perception=None,
                           formalizer_resource_error=None, formalizer_status='TEST_ONLY')


def test_panel_removes_old_probe_editor_and_saves_only_agent_prompt(qapp, tmp_path):
    svc = services(tmp_path)
    panel = LLMControlWidget(svc)
    tabs = [panel.tabs.tabText(i) for i in range(panel.tabs.count())]
    assert 'Formalizer RAW' in tabs and 'V7 IR / trace' in tabs
    assert not any('Parser' in t or 'Perception probe' in t for t in tabs)
    assert not hasattr(panel, 'probe_selector') and not hasattr(panel, 'perception_editor')
    panel.agent_editor.setPlainText('real Agent prompt')
    panel._save_prompts()
    assert (tmp_path / 'agent.txt').read_text() == 'real Agent prompt'
    assert not (tmp_path / 'perception.txt').exists()
    panel.close()


def test_external_run_prompts_counters_and_checkpoint_survive_normal_refresh(qapp, tmp_path):
    panel = LLMControlWidget(services(tmp_path))
    panel.set_oracle_running(True)
    panel.set_oracle_progress({'schema_version': 'v7-oracle-progress-1', 'event': 'request_started',
        'seq': 1, 'case_id': 'LANG', 'request_id': 'R', 'prompt': 'bounded request'})
    panel.refresh_status(force=True)
    assert 'IN FLIGHT' in panel.parser_raw_view.toPlainText()
    assert 'bounded request' in panel.parser_raw_view.toPlainText()
    assert 'requests=1' in panel.stage_label.text()
    panel.set_oracle_progress({'schema_version': 'v7-oracle-progress-1', 'event': 'step_finished',
        'seq': 2, 'case_id': 'LANG', 'step_id': 'S', 'checkpoint': {'diagnostics': ['ACTUAL']}})
    assert json.loads(panel.parser_decoded_view.toPlainText())['case_checkpoints'][0]['checkpoint']['diagnostics'] == ['ACTUAL']
    panel.set_oracle_running(False)
    panel._refresh_parser_diagnostics(force=True)
    assert 'bounded request' in panel.parser_raw_view.toPlainText()
    panel.begin_turn('новый обычный запрос')
    assert 'bounded request' not in panel.parser_raw_view.toPlainText()
    assert not panel._oracle_scope
    panel.close()


def test_chat_scope_uses_actual_native_snapshot_and_never_old_perception_history(qapp, tmp_path):
    snapshot = {'sequence': 1, 'source_text': 'ранее', 'state': {'frames': ['old-frame']}}
    formalizer = SimpleNamespace(diagnostic_snapshot=lambda: snapshot)
    svc = services(tmp_path)
    # This old compatibility buffer must not be consulted at all.
    svc.perception = SimpleNamespace(_formalizer=formalizer,
        diagnostics=lambda: (_ for _ in ()).throw(AssertionError('old parser history consulted')))
    panel = LLMControlWidget(svc)
    panel.begin_turn('сейчас')
    panel._refresh_parser_diagnostics(force=True)
    assert 'old-frame' not in panel.parser_decoded_view.toPlainText()
    snapshot = {'sequence': 2, 'source_text': 'сейчас', 'state': {'frames': ['real-frame']},
                'interpretation_report': {'terminal': 'RESOLUTION_ONLY'}}
    panel._refresh_parser_diagnostics(force=True)
    current = json.loads(panel.parser_decoded_view.toPlainText())
    assert current['state']['frames'] == ['real-frame']
    assert current['interpretation_report']['terminal'] == 'RESOLUTION_ONLY'
    panel.close()


def test_unchanged_native_sequence_does_not_copy_whole_ir_on_poll(qapp, tmp_path):
    snapshot = {'sequence': 1, 'source_text': 'готово', 'state': {'frames': ['real-frame']}}
    copies = []
    def read_snapshot():
        copies.append(1)
        return snapshot
    formalizer = SimpleNamespace(diagnostic_sequence=lambda: snapshot['sequence'],
                                 diagnostic_snapshot=read_snapshot)
    svc = services(tmp_path)
    svc.perception = SimpleNamespace(_formalizer=formalizer)
    panel = LLMControlWidget(svc)
    panel._refresh_parser_diagnostics(force=True)
    assert len(copies) == 1
    for _ in range(5):
        panel._refresh_parser_diagnostics()
    assert len(copies) == 1
    snapshot = {'sequence': 2, 'source_text': 'новое', 'state': {'frames': ['new-frame']}}
    panel._refresh_parser_diagnostics()
    assert len(copies) == 2
    assert 'new-frame' in panel.parser_decoded_view.toPlainText()
    panel.begin_turn('следующий запрос')
    assert len(copies) == 2
    panel.close()
