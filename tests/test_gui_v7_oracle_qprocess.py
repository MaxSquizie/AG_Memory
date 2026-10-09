"""Actual Qt event-loop/QProcess tests without the unrelated OpenGL canvas."""
from __future__ import annotations

from pathlib import Path
import shutil
from types import SimpleNamespace
import time

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLineEdit, QTextEdit, QDockWidget, QPushButton
from ah.gui import semantic_test_window as gui


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(app, predicate, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Qt condition did not become true")


@pytest.fixture
def window(app, monkeypatch):
    def minimal_base_init(self):
        QMainWindow.__init__(self)
        holder = QWidget(self)
        self.setCentralWidget(holder)
        layout = QVBoxLayout(holder)
        self.chat_input = QLineEdit(holder)
        layout.addWidget(self.chat_input)
        self.chat_history = QTextEdit(holder)
        layout.addWidget(self.chat_history)
        self.metrics_panel = QWidget(self)
        self.llm_dock = QDockWidget(self)
        self._seen_events = []
        self._seen_running = []
        self.llm_panel = SimpleNamespace(set_oracle_progress=self._seen_events.append, set_oracle_running=self._seen_running.append)
        self.services = SimpleNamespace(config=SimpleNamespace(llm=SimpleNamespace(request_timeout_seconds=2)), stop=lambda **kw: None)
        for name in gui.MainWindow._HIDDEN_LEGACY_CHAT_BUTTONS:
            setattr(self, name, QPushButton(name, holder))
    monkeypatch.setattr(gui._BaseMainWindow, "__init__", minimal_base_init)
    monkeypatch.setattr(gui._BaseMainWindow, "_cognitive_run_active", lambda self: False)
    w = gui.MainWindow()
    yield w
    process = w._semantic_test_process
    if process is not None:
        process.kill()
        process.waitForFinished(1000)
    w._oracle_timer.stop()
    w.deleteLater()
    app.processEvents()


def stub(tmp_path):
    script = tmp_path / "runner.py"
    script.write_text('''import json,os,sys,time
from pathlib import Path
import shutil
out=Path(sys.argv[1]); release=Path(sys.argv[2]); out.mkdir(parents=True)
assert os.environ['FORMALIZER_ORACLE_API_KEY']=='secret-fixture'
assert os.environ['PYTHONIOENCODING']=='utf-8'
def emit(seq,event,**kw):
 print('V7_PROGRESS '+json.dumps(dict(schema_version='v7-oracle-progress-1',seq=seq,event=event,**kw),ensure_ascii=False),flush=True)
emit(0,'run_started',total=1)
emit(1,'case_started',case_id='A38',total=1)
emit(2,'step_started',case_id='A38',action='formalize',step_id='step1')
emit(3,'request_started',case_id='A38',prompt='Книга',requests_started=1,requests_finished=0)
while not release.exists(): time.sleep(.01)
emit(4,'request_finished',response='answer',requests_started=1,requests_finished=1)
emit(5,'case_finished',case_id='A38',status='BLOCKED',completed=1,total=1,blocked=1)
(out/'summary.json').write_text(json.dumps(dict(status='BLOCKED',passed_cases=0,failed_cases=0,blocked_cases=1)))
emit(6,'run_finished',status='BLOCKED',completed=1,total=1,blocked=1,requests_started=1,requests_finished=1)
sys.exit(3)
''')
    return script


def test_gui_streams_while_child_waits_and_preserves_blocked_status(app, window, monkeypatch, tmp_path):
    release = tmp_path / "release"
    script = stub(tmp_path)
    actual_command = gui.build_oracle_command
    commands = []
    def command(root, base_url, model, out, **kwargs):
        commands.append(actual_command(root, base_url, model, out, **kwargs))
        return [str(script), str(out), str(release)]
    monkeypatch.setattr(gui, "build_oracle_command", command)
    window._start_oracle(window._SEMANTIC_SUITES[0], "lmstudio", "http://localhost", "model", "secret-fixture")
    # The actual child output reaches the UI before its response is released.
    wait_until(app, lambda: window._oracle_progress.requests_started == 1)
    assert window._cognitive_run_active()
    assert window._oracle_progress.requests_finished == 0
    assert "Запросы 0/1" in window.oracle_progress_label.text()
    assert "ожидание модели" in window.oracle_progress_label.text()
    assert window._seen_events[-1]["event"] == "request_started"
    assert window._seen_running == [True]
    assert "--progress-jsonl" in commands[0]
    release.touch()
    wait_until(app, lambda: window._semantic_test_process is None)
    assert window.semantic_test_status.text() == "BLOCKED"
    assert "A38: BLOCKED" in window.chat_history.toPlainText()
    assert window._seen_running == [True, False]
    assert window.oracle_progress_bar.value() == 1
    assert window.semantic_test_button.isEnabled()
    assert not window._cognitive_run_active()
    shutil.rmtree(Path(commands[0][commands[0].index("--out") + 1]))


def test_stopping_own_child_is_cancelled_not_pass(app, window, monkeypatch, tmp_path):
    monkeypatch.setattr(gui, "build_oracle_command", lambda *a, **kw: [str(stub(tmp_path)), str(tmp_path / "out"), str(tmp_path / "never")])
    window._start_oracle(window._SEMANTIC_SUITES[0], "lmstudio", "http://localhost", "model", "secret-fixture")
    wait_until(app, lambda: window._oracle_progress.requests_started == 1)
    window._stop_oracle()
    wait_until(app, lambda: window._semantic_test_process is None)
    assert window.semantic_test_status.text() == "CANCELLED"
    assert window._seen_running[-1] is False


def test_failed_start_restores_controls(app, window, monkeypatch, tmp_path):
    monkeypatch.setattr(gui.sys, "executable", str(tmp_path / "missing-python"))
    window._start_oracle(window._SEMANTIC_SUITES[0], "lmstudio", "http://localhost", "model", None)
    wait_until(app, lambda: window._semantic_test_process is None)
    assert window.semantic_test_status.text() == "ERROR"
    assert window.semantic_test_button.isEnabled()
    assert window._seen_running == [True, False]


def test_old_buttons_hidden_and_only_current_v7_choices_visible(window):
    assert window.semantic_suite.count() == 3
    for name in window._HIDDEN_LEGACY_CHAT_BUTTONS:
        assert getattr(window, name).isHidden()
    assert all(s.kind.startswith('oracle_') for s in window._SEMANTIC_SUITES)
