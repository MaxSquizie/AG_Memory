"""Production GUI control for the current V7 oracle, with live diagnostics."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import sys
import time
from uuid import uuid4

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Slot
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton

from .main_window import MainWindow as _BaseMainWindow, FunctionWorker
from .oracle_progress_state import OracleOutputParser, OracleProgressState
from .oracle_semantic_runner import build_oracle_command, detect_lmstudio_models, parse_run_stats, process_run_status, render_report, save_report


@dataclass(frozen=True, slots=True)
class _SemanticSuite:
    kind: str
    label: str
    tiers: tuple[str, ...]
    needs_model: bool = True


class MainWindow(_BaseMainWindow):
    """Only V7 suites are visible; hidden base widgets keep their slot contracts."""

    _SEMANTIC_SUITES = (
        _SemanticSuite("oracle_model", "V7 · язык — локальная модель", ("pipeline",)),
        _SemanticSuite("oracle_all", "V7 · весь корпус архитектуры — локальная модель", ()),
        _SemanticSuite("oracle_components", "V7 · компоненты и recovery — без модели", ("component", "durability"), False),
    )
    _HIDDEN_LEGACY_CHAT_BUTTONS = (
        "acceptance_button", "m1_adversarial_button", "m1_inversion_button",
        "m1_ellipsis_button", "m1_typo_button", "m1_quantifier_button",
        "m1_temporal_mode_button", "document_acceptance_button", "hidden_valency_button", "m2_acceptance_button",
    )
    _HIDDEN_NON_SEMANTIC_METRIC_BUTTON_TEXTS = frozenset({"Запустить M2 acceptance", "Запустить M3 GC acceptance"})

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._semantic_test_process = None
        self._oracle_discovery_worker = None
        self._oracle_closing = False
        self._oracle_cancelled = False
        self._oracle_output_parser = OracleOutputParser()
        self._oracle_progress = OracleProgressState()
        self._semantic_process_output = deque(maxlen=60)
        self._oracle_out_dir = None
        self._oracle_timer = QTimer(self)
        self._oracle_timer.setInterval(250)
        self._oracle_timer.timeout.connect(self._refresh_oracle_progress)
        self._install_semantic_test_controls()

    def _install_semantic_test_controls(self) -> None:
        for name in self._HIDDEN_LEGACY_CHAT_BUTTONS:
            widget = getattr(self, name, None)
            if widget is not None:
                widget.hide()
        for button in self.metrics_panel.findChildren(QPushButton):
            if button.text() in self._HIDDEN_NON_SEMANTIC_METRIC_BUTTON_TEXTS:
                button.hide()
        parent = self.chat_input.parentWidget()
        layout = None if parent is None else parent.layout()
        if layout is None:
            raise RuntimeError("chat dock layout is unavailable for V7 oracle")
        row = QHBoxLayout()
        row.addWidget(QLabel("V7 oracle"))
        self.semantic_suite = QComboBox()
        self.semantic_suite.setObjectName("semanticSuiteSelector")
        for suite in self._SEMANTIC_SUITES:
            self.semantic_suite.addItem(suite.label)
        self.semantic_suite.setToolTip("Языковой набор: tier=pipeline. Весь корпус: все механики, включая typed components и recovery.\nБез модели: языковые шаги внутри компонентных кейсов остаются BLOCKED.")
        row.addWidget(self.semantic_suite, 1)
        self.semantic_test_button = QPushButton("Запустить V7")
        self.semantic_test_button.setObjectName("semanticTestRunButton")
        self.semantic_test_button.clicked.connect(self._run_selected_semantic_suite)
        row.addWidget(self.semantic_test_button)
        self.oracle_stop_button = QPushButton("Остановить")
        self.oracle_stop_button.setEnabled(False)
        self.oracle_stop_button.clicked.connect(self._stop_oracle)
        row.addWidget(self.oracle_stop_button)
        self.semantic_test_status = QLabel("READY")
        self.semantic_test_status.setObjectName("semanticTestStatus")
        row.addWidget(self.semantic_test_status)
        layout.addLayout(row)
        self.oracle_progress_label = QLabel("Прогон не запущен")
        self.oracle_progress_label.setObjectName("oracleLiveProgress")
        self.oracle_progress_label.setWordWrap(True)
        layout.addWidget(self.oracle_progress_label)
        self.oracle_progress_bar = QProgressBar()
        self.oracle_progress_bar.setObjectName("oracleCaseProgress")
        self.oracle_progress_bar.setRange(0, 1)
        self.oracle_progress_bar.setValue(0)
        layout.addWidget(self.oracle_progress_bar)

    def _selected_semantic_suite(self) -> _SemanticSuite:
        return self._SEMANTIC_SUITES[self.semantic_suite.currentIndex()]

    def _semantic_test_busy(self) -> bool:
        process = getattr(self, "_semantic_test_process", None)
        return bool(getattr(self, "_oracle_discovery_worker", None) is not None
                    or (process is not None and process.state() != QProcess.ProcessState.NotRunning))

    def _cognitive_run_active(self) -> bool:
        # The child owns its fixture AH, but shares the model server with chat.
        return self._semantic_test_busy() or super()._cognitive_run_active()

    @Slot()
    def _run_selected_semantic_suite(self) -> None:
        if self._cognitive_run_active():
            QMessageBox.information(self, "V7 oracle", "Дождитесь завершения текущего запроса или прогона.")
            return
        self.semantic_test_status.setText("PREPARING")
        self.semantic_test_button.setEnabled(False)
        self.semantic_suite.setEnabled(False)
        suite = self._selected_semantic_suite()
        if not suite.needs_model:
            self._start_oracle(suite, "disabled", "", "", None)
            return
        llm = self.services.config.llm
        backend = str(getattr(llm, "backend", ""))
        if backend == "lmstudio":
            provider = "lmstudio"
            base_url = str(getattr(llm, "lmstudio_base_url", "")).strip()
            model = str(getattr(llm, "lmstudio_model", "")).strip()
            api_key = str(getattr(llm, "lmstudio_api_key", "")).strip() or None
        elif backend == "ollama":
            provider = "ollama"
            base_url = str(getattr(llm, "ollama_base_url", "")).strip()
            model = str(getattr(llm, "ollama_model", "")).strip()
            api_key = None
        else:
            self._oracle_prepare_error("Для модельного oracle выберите backend=lmstudio или ollama и запущенный локальный сервер.")
            return
        if not base_url:
            self._oracle_prepare_error("URL локального сервера модели не задан в конфиге.")
            return
        if model and model.lower() != "auto":
            self._start_oracle(suite, provider, base_url, model, api_key)
            return
        self.oracle_progress_label.setText("Обнаружение модели на локальном сервере…")
        self.oracle_progress_bar.setRange(0, 0)
        worker = FunctionWorker(lambda: detect_lmstudio_models(base_url, api_key))
        self._oracle_discovery_worker = worker
        worker.signals.result.connect(lambda models: self._oracle_model_discovered(suite, provider, base_url, api_key, models))
        worker.signals.error.connect(self._oracle_prepare_error)
        self.thread_pool.start(worker)

    def _oracle_model_discovered(self, suite, provider, base_url, api_key, models) -> None:
        self._oracle_discovery_worker = None
        if self._oracle_closing:
            return
        if len(models) != 1:
            self._oracle_prepare_error("Укажите точный ключ модели в конфиге: " + (", ".join(models) if models else "сервер не вернул загруженную модель"))
            return
        self._start_oracle(suite, provider, base_url, models[0], api_key)

    def _oracle_prepare_error(self, message: str) -> None:
        self._oracle_discovery_worker = None
        if self._oracle_closing:
            return
        self.chat_history.append(f"<b>V7 oracle ERROR:</b> {self._html(message)}")
        self.oracle_progress_bar.setRange(0, 1)
        self._semantic_suite_idle("ERROR")

    def _start_oracle(self, suite, provider, base_url, model, api_key) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        out_dir = repo_root / ".kripl" / "oracle_v7" / ("gui_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8])
        timeout = float(getattr(self.services.config.llm, "request_timeout_seconds", 240.0))
        argv = build_oracle_command(repo_root, base_url, model, out_dir, provider=provider, tiers=suite.tiers, timeout=timeout)
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setWorkingDirectory(str(repo_root))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        if api_key:
            env.insert("FORMALIZER_ORACLE_API_KEY", api_key)
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(self._oracle_model_output)
        process.finished.connect(self._oracle_model_finished)
        process.errorOccurred.connect(self._oracle_model_error)
        self._semantic_test_process = process
        self._oracle_out_dir = out_dir
        self._oracle_cancelled = False
        self._oracle_progress = OracleProgressState()
        self._oracle_output_parser = OracleOutputParser()
        self._semantic_process_output.clear()
        self.semantic_test_status.setText("RUNNING")
        self.oracle_stop_button.setEnabled(True)
        self.oracle_progress_bar.setRange(0, 0)
        self.llm_panel.set_oracle_running(True)
        self.llm_dock.show()
        self._oracle_timer.start()
        self._refresh_oracle_progress()
        self.chat_history.append(f"<b>{self._html(suite.label)}</b>: provider={self._html(provider)}, model={self._html(model or 'disabled')}, reasoning=off<br>Артефакты: {self._html(str(out_dir))}")
        process.start(sys.executable, ["-u", *argv])

    @Slot()
    def _oracle_model_output(self) -> None:
        process = self._semantic_test_process
        if process is not None:
            self._consume_oracle_output(bytes(process.readAllStandardOutput()))

    def _consume_oracle_output(self, chunk: bytes, *, final: bool = False) -> None:
        events, logs = self._oracle_output_parser.feed(chunk, final=final)
        for event in events:
            if not self._oracle_progress.apply(event):
                continue
            self.llm_panel.set_oracle_progress(event)
            if event.get("event") == "case_finished":
                status = event.get("status", "INCOMPLETE")
                detail = event.get("errors") or event.get("blockers") or event.get("runtime_error") or ""
                cause = event.get('first_observed_text')
                if not isinstance(cause, str):
                    native = event.get('runtime_diagnostics')
                    cause = native.get('first_observed_text', '') if isinstance(native, dict) else ''
                cause_html = f"<br><b>Runtime:</b> {self._html(cause[:2000])}" if cause and status != 'PASS' else ''
                native_text = event.get('native_diagnostic_text')
                if isinstance(native_text, str) and native_text and status != 'PASS':
                    cause_html += f"<br><b>Диагностика IR:</b> {self._html(native_text[:4000])}"
                self.chat_history.append(f"<b>{self._html(str(event.get('case_id')))}: {self._html(str(status))}</b>"
                    f"{cause_html}<br><b>Сверка:</b> {self._html(str(detail)[:600])}")
        for line in logs:
            self._semantic_process_output.append(line)
            self.chat_history.append(f"<pre>{self._html(line[:2000])}</pre>")
        self._refresh_oracle_progress()

    @Slot()
    def _refresh_oracle_progress(self) -> None:
        self.oracle_progress_label.setText(self._oracle_progress.text())
        if self._oracle_progress.total:
            self.oracle_progress_bar.setRange(0, self._oracle_progress.total)
            self.oracle_progress_bar.setValue(self._oracle_progress.completed)

    @Slot(int, QProcess.ExitStatus)
    def _oracle_model_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self._oracle_closing:
            return
        self._oracle_model_output()
        self._consume_oracle_output(b"", final=True)
        status = "ERROR"
        try:
            stats = parse_run_stats(self._oracle_out_dir) if self._oracle_out_dir is not None else {}
            status = process_run_status(stats.get("status", "INCOMPLETE"), exit_code,
                                        normal_exit=exit_status == QProcess.ExitStatus.NormalExit,
                                        completed=self._oracle_progress.finished, cancelled=self._oracle_cancelled)
            self.chat_history.append(f"<b>V7 oracle {self._html(status)}</b><pre>{self._html(render_report(stats)[-16000:])}</pre>")
            if self._oracle_out_dir is not None and self._oracle_out_dir.is_dir():
                stats["process_exit_code"] = exit_code
                stats["gui_status"] = status
                md_path, json_path = save_report(self._oracle_out_dir, stats)
                self.chat_history.append(f"Отчёт: {self._html(str(md_path))}<br>Данные: {self._html(str(json_path))}<br>Живой trace: {self._html(str(self._oracle_out_dir / 'progress.jsonl'))}")
        except Exception as exc:
            self.chat_history.append(f"<b>V7 oracle: ошибка чтения/сохранения отчёта:</b> {self._html(str(exc))}")
        finally:
            self._release_oracle(status)

    @Slot(QProcess.ProcessError)
    def _oracle_model_error(self, error: QProcess.ProcessError) -> None:
        process = self._semantic_test_process
        if process is not None and error == QProcess.ProcessError.FailedToStart:
            self.chat_history.append(f"<b>V7 oracle ERROR:</b> {self._html(process.errorString())}")
            self._release_oracle("ERROR")

    def _release_oracle(self, status: str) -> None:
        self._oracle_timer.stop()
        self.llm_panel.set_oracle_running(False)
        self._oracle_progress.finished = True
        self._oracle_progress.finished_at = time.monotonic()
        self._oracle_progress.active_request_at = None
        self._refresh_oracle_progress()
        process = self._semantic_test_process
        self._semantic_test_process = None
        if process is not None:
            process.deleteLater()
        self._oracle_out_dir = None
        self._semantic_suite_idle(status)

    @Slot()
    def _stop_oracle(self) -> None:
        process = self._semantic_test_process
        if process is None:
            return
        self._oracle_cancelled = True
        self.semantic_test_status.setText("STOPPING")
        self.oracle_stop_button.setEnabled(False)
        process.terminate()
        # A stuck HTTP call must not prevent cancelling our own child process.
        QTimer.singleShot(1500, lambda: process.kill() if self._semantic_test_process is process and process.state() != QProcess.ProcessState.NotRunning else None)

    def _semantic_suite_idle(self, status: str) -> None:
        self.semantic_test_status.setText(status)
        self.semantic_test_button.setEnabled(True)
        self.semantic_suite.setEnabled(True)
        self.oracle_stop_button.setEnabled(False)

    def closeEvent(self, event) -> None:
        self._oracle_closing = True
        self._oracle_timer.stop()
        process = self._semantic_test_process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            if not process.waitForFinished(1000):
                process.kill()
                process.waitForFinished(1000)
        super().closeEvent(event)
