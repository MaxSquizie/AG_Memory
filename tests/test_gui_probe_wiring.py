"""Exercise the GUI's real service/selector/document route without a model server."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.documents.reading import read_document
from ah.formalizer.probe_diagnostics import describe, configuration_text
from ah.gui.app import _auto_provision_formalizer_config
from tools.prepare_formalizer_v7_gui import prepare,check_composition_session
from test_formalizer_v7_gui_fixture import source_config
from test_formalization_inspection import qt_session


class RecordingBackend:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def generate(self,prompt,**kwargs):
        self.calls.append((prompt,kwargs))
        if self.fail:raise ConnectionError('test transport unavailable')
        return SimpleNamespace(text='?')


def test_auto_gui_uses_composition_not_existing_oracle_and_preserves_it(tmp_path):
    source=source_config(tmp_path);root=tmp_path/'artifacts'
    old=prepare(source,root/'gui-local',profile='oracle')
    before={p.name:p.read_bytes() for p in old.parent.iterdir() if p.is_file()}
    generated=_auto_provision_formalizer_config(source,fixture_root=root)
    assert generated==root/'gui-local-composition/gui.toml'
    assert json.loads((generated.parent/'fixture_manifest.json').read_text())['composition_profile']=='composition'
    assert before=={p.name:p.read_bytes() for p in old.parent.iterdir() if p.is_file()}
    check_composition_session(generated)
    with pytest.raises(ValueError,match='does not enable composition probes'):check_composition_session(old)
    assert before=={p.name:p.read_bytes() for p in old.parent.iterdir() if p.is_file()}
    assert _auto_provision_formalizer_config(source,fixture_root=root)==generated
    assert _auto_provision_formalizer_config(old,fixture_root=root) is None  # explicit configured session is respected


@pytest.mark.parametrize('profile,expected_calls',[('oracle',0),('composition',1)])
def test_gui_service_document_route_reaches_real_backend_selector(tmp_path,monkeypatch,profile,expected_calls):
    source=source_config(tmp_path)
    cfg=load_config(prepare(source,tmp_path/'session',profile=profile))
    backend=RecordingBackend();monkeypatch.setattr('ah.bootstrap.build_llm_backend',lambda _:backend)
    services=RuntimeServices.build(cfg)
    text=tmp_path/'input.txt';text.write_text('Не каждый студент может сдать экзамен и получить диплом.',encoding='utf-8')
    result=read_document(services,text,tmp_path/'first')
    assert len(backend.calls)==expected_calls
    assert result['probe_activity']['started']==expected_calls
    assert result['probe_activity']['finished']==expected_calls
    info=result['probe_configuration']
    assert info['selector']=='RealBackendSelector' and info['composition_enabled']==(profile=='composition')
    assert info['config_path']==str(cfg.source_path)
    if expected_calls:
        assert backend.calls[0][1]['role']=='formalizer'
        assert 'composition_boundary' in backend.calls[0][0]
        assert 'SELECT_LABELS_V1' in backend.calls[0][0]
        snapshot=json.loads((tmp_path/'first/interpretation.json').read_text())
        assert snapshot['probe_activity']==result['probe_activity']
        assert any(d.get('raw_response')=='?' for d in snapshot['state']['decisions'].values())
        again=read_document(services,text,tmp_path/'second')
        assert len(backend.calls)==expected_calls
        assert again['probe_activity']['started']==0 and again['probe_activity']['input_reused']
    else:
        assert 'НЕТ компонентов' in configuration_text(info)


def test_provider_failure_is_visible_as_attempt_not_disabled_probes(tmp_path,monkeypatch):
    cfg=load_config(prepare(source_config(tmp_path),tmp_path/'session',profile='composition'))
    backend=RecordingBackend(fail=True);monkeypatch.setattr('ah.bootstrap.build_llm_backend',lambda _:backend)
    services=RuntimeServices.build(cfg)
    source=tmp_path/'input.txt';source.write_text('Не каждый студент может сдать экзамен и получить диплом.',encoding='utf-8')
    result=read_document(services,source,tmp_path/'report')
    assert result['probe_configuration']['composition_enabled']
    assert result['probe_activity']['started']==1 and result['probe_activity']['failed']==1
    assert result['probe_activity']['finished']==0


def test_pasted_text_button_uses_main_window_worker_and_model(tmp_path,monkeypatch,qt_session):
    from types import MethodType
    from PySide6.QtCore import QEventLoop,QThreadPool,QTimer
    from ah.gui.document_panel import DocumentPanelWidget
    from ah.gui.main_window import MainWindow
    cfg=load_config(prepare(source_config(tmp_path),tmp_path/'session',profile='composition'))
    backend=RecordingBackend();monkeypatch.setattr('ah.bootstrap.build_llm_backend',lambda _:backend)
    services=RuntimeServices.build(cfg);panel=DocumentPanelWidget();reports=[];errors=[]
    loop=QEventLoop();pool=QThreadPool();timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit)
    def finished(report):reports.append(report);panel.set_reading_report(report)
    host=SimpleNamespace(services=services,document_panel=panel,thread_pool=pool,
        _cognitive_run_active=lambda:False,_document_reading_finished=finished,
        _document_operation_error=errors.append,_document_ingest_worker_finished=loop.quit)
    host._ingest_document_from_gui=MethodType(MainWindow._ingest_document_from_gui,host)
    panel.text_requested.connect(MethodType(MainWindow._formalize_text_from_gui,host))
    panel.text_input.setPlainText('Не каждый студент может сдать экзамен и получить диплом.')
    panel.text_button.click();timer.start(10000);loop.exec();timer.stop();pool.waitForDone(10000)
    assert not errors and len(reports)==1
    assert len(backend.calls)==1 and backend.calls[0][1]['role']=='formalizer'
    assert 'Вызовы модели: 1' in panel.status.text()
    assert 'Композиционные пробы включены' in panel.probe_configuration.text()
    panel.close()
