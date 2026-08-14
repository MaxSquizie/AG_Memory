from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ah.bootstrap import RuntimeServices
from ah.config import AppConfig

from .config_editor import ConfigEditor
from .config_store import ApplyMode, ConfigDocument
from .graph_canvas import GraphCanvasWidget
from .node_manager import NodeManagerWidget
from .link_manager import LinkManagerWidget
from .llm_panel import LLMControlWidget


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            value = self.fn()
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.result.emit(value)
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self, services: RuntimeServices, config_path: str | Path) -> None:
        super().__init__()
        self.services = services
        self.config_path = Path(config_path)
        self.thread_pool = QThreadPool.globalInstance()
        self._last_turn = None
        self._selected_uid: str | None = None
        self._selected_edge_key: str | None = None
        self._llm_restart_required = False
        self._runtime_restart_required = False

        self.setWindowTitle("AH Agent — Cognitive Runtime")
        self.resize(1580, 980)

        self.canvas = GraphCanvasWidget(services)
        self.canvas.node_selected.connect(self._select_node)
        self.canvas.edge_selected.connect(self._select_edge)
        self.setCentralWidget(self.canvas)

        self._build_toolbar()
        self._build_chat_dock()
        self._build_config_dock()
        self._build_llm_dock()
        self._build_inspector_dock()
        self._build_node_manager_dock()
        self._build_link_manager_dock()
        self._build_runtime_dock()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(300)
        self._refresh_status()

    # ---------- UI construction ----------
    def _build_toolbar(self) -> None:
        bar = QToolBar("Runtime", self)
        self.addToolBar(bar)

        self.action_llm = QAction("Запустить LLM", self)
        self.action_llm.triggered.connect(self._toggle_llm)
        bar.addAction(self.action_llm)

        self.action_ignition = QAction("Запустить Ignition", self)
        self.action_ignition.triggered.connect(self._toggle_ignition)
        bar.addAction(self.action_ignition)

        self.action_tick = QAction("Tick", self)
        self.action_tick.triggered.connect(self._manual_tick)
        bar.addAction(self.action_tick)

        self.action_save = QAction("Save AH", self)
        self.action_save.triggered.connect(self._save_memory)
        bar.addAction(self.action_save)

        bar.addSeparator()
        reset_camera = QAction("Сброс камеры", self)
        reset_camera.triggered.connect(self.canvas.reset_camera)
        bar.addAction(reset_camera)

    def _build_chat_dock(self) -> None:
        dock = QDockWidget("Диалог", self)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.chat_history = QTextBrowser()
        self.chat_input = QPlainTextEdit()
        self.chat_input.setPlaceholderText("Сообщение пользователю/агенту…")
        self.chat_input.setMaximumBlockCount(1000)
        self.chat_input.setFixedHeight(90)
        self.send_button = QPushButton("Отправить")
        self.send_button.clicked.connect(self._send_chat)
        layout.addWidget(self.chat_history, 1)
        layout.addWidget(self.chat_input)
        layout.addWidget(self.send_button)
        dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def _build_config_dock(self) -> None:
        dock = QDockWidget("Конфигурация", self)
        self.config_editor = ConfigEditor(self.config_path)
        self.config_editor.config_saved.connect(self._config_saved)
        dock.setWidget(self.config_editor)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_llm_dock(self) -> None:
        dock = QDockWidget("LLM", self)
        self.llm_panel = LLMControlWidget(self.services)
        self.llm_panel.start_requested.connect(self._start_llm)
        self.llm_panel.stop_requested.connect(self._stop_llm)
        self.llm_panel.restart_requested.connect(self._restart_llm)
        self.llm_panel.prompts_saved.connect(
            lambda: self.statusBar().showMessage("LLM prompt-файлы сохранены", 3000)
        )
        dock.setWidget(self.llm_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_inspector_dock(self) -> None:
        dock = QDockWidget("Узел / Связь", self)
        self.node_inspector = QPlainTextEdit()
        self.node_inspector.setReadOnly(True)
        self.node_inspector.setPlaceholderText("Выберите узел или связь на canvas")
        dock.setWidget(self.node_inspector)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_node_manager_dock(self) -> None:
        dock = QDockWidget("Добавление узла", self)
        self.node_manager = NodeManagerWidget(
            self.services,
            selected_uid=lambda: self._selected_uid,
        )
        self.node_manager.node_created.connect(self._node_created)
        dock.setWidget(self.node_manager)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_link_manager_dock(self) -> None:
        dock = QDockWidget("Связи", self)
        self.link_manager = LinkManagerWidget(
            self.services,
            selected_uid=lambda: self._selected_uid,
        )
        self.link_manager.link_created.connect(self._link_created)
        dock.setWidget(self.link_manager)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_runtime_dock(self) -> None:
        dock = QDockWidget("Runtime / Trace", self)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.runtime_label = QLabel()
        self.visual_legend = QLabel(
            "Красный = excitation x; движущийся красный хвост = source → target; "
            "w не затухает визуально и показывается отдельно в инспекторе."
        )
        self.visual_legend.setWordWrap(True)
        self.trace_view = QPlainTextEdit()
        self.trace_view.setReadOnly(True)
        layout.addWidget(self.runtime_label)
        layout.addWidget(self.visual_legend)
        layout.addWidget(self.trace_view, 1)
        dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    # ---------- runtime controls ----------
    def _toggle_llm(self) -> None:
        llm = self.services.llm
        if llm is None:
            QMessageBox.warning(self, "LLM", "LLM отключена в конфиге.")
            return
        if llm.is_running:
            self._stop_llm()
        else:
            self._start_llm()

    def _run_llm_operation(self, fn, *, clears_restart: bool = False) -> None:
        self.action_llm.setEnabled(False)
        worker = FunctionWorker(fn)
        worker.signals.error.connect(lambda msg: QMessageBox.critical(self, "LLM", msg))
        if clears_restart:
            worker.signals.result.connect(lambda _value: setattr(self, "_llm_restart_required", False))
        worker.signals.finished.connect(lambda: self.action_llm.setEnabled(True))
        worker.signals.finished.connect(self._refresh_status)
        self.thread_pool.start(worker)

    def _start_llm(self) -> None:
        llm = self.services.llm
        if llm is None:
            QMessageBox.warning(self, "LLM", "LLM отключена в конфиге.")
            return
        if llm.is_running:
            return
        self._run_llm_operation(llm.start, clears_restart=True)

    def _stop_llm(self) -> None:
        llm = self.services.llm
        if llm is None or not llm.is_running:
            return
        self._run_llm_operation(llm.stop)

    def _restart_llm(self) -> None:
        llm = self.services.llm
        if llm is None:
            QMessageBox.warning(self, "LLM", "LLM отключена в конфиге.")
            return
        self._run_llm_operation(llm.restart, clears_restart=True)

    def _toggle_ignition(self) -> None:
        if self.services.clock.running:
            self.services.clock.stop()
        else:
            self.services.clock.start()
        self._refresh_status()

    def _manual_tick(self) -> None:
        if self.services.clock.running:
            QMessageBox.information(self, "Ignition", "Остановите непрерывный clock перед manual tick.")
            return
        try:
            with self.services.operation_lock:
                result = self.services.ignition.tick()
            self.canvas.push_tick(result)
        except Exception as exc:
            QMessageBox.critical(self, "Tick", str(exc))

    def _save_memory(self) -> None:
        try:
            with self.services.operation_lock:
                self.services.save()
        except Exception as exc:
            QMessageBox.critical(self, "Persistence", str(exc))
        else:
            self.statusBar().showMessage("AH сохранена", 2500)

    # ---------- chat ----------
    def _send_chat(self) -> None:
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        if self.services.llm is None or not self.services.llm.is_running:
            QMessageBox.warning(self, "Диалог", "Сначала запустите локальную LLM.")
            return
        self.chat_input.clear()
        self.chat_history.append(f"<b>{self.services.config.identity.user_name}:</b> {self._html(text)}")
        self.send_button.setEnabled(False)

        def run_turn():
            orchestrator = self.services.create_orchestrator()
            result = orchestrator.handle_user_text(text)
            return result

        worker = FunctionWorker(run_turn)
        worker.signals.result.connect(self._turn_finished)
        worker.signals.error.connect(self._turn_error)
        worker.signals.finished.connect(lambda: self.send_button.setEnabled(True))
        self.thread_pool.start(worker)

    def _turn_finished(self, result) -> None:
        self._last_turn = result
        parser_failures = [d for d in result.perception.diagnostics if str(d).startswith("PARSER_FAILURE:")]
        if parser_failures:
            self.chat_history.append(
                "<span style='color:#d28a2e'><b>Perception:</b> semantic parse failed; "
                "the user turn was stored as H experience only. See LLM → Parser RAW.</span>"
            )
        self.chat_history.append(
            f"<b>{self.services.config.identity.agent_name}:</b> {self._html(result.response_text)}"
        )
        for tick in (*result.ticks_after_input, *result.ticks_after_response):
            self.canvas.push_tick(tick)
        trace_payload = []
        for i, q in enumerate(result.queries, 1):
            if q.outcome is None:
                trace_payload.append({"query": i, "diagnostics": q.diagnostics})
                continue
            trace_payload.append(
                {
                    "query": i,
                    "status": q.outcome.status.value,
                    "stop_reason": q.outcome.stop_reason.value,
                    "premise_uids": [r.uid for r in q.outcome.premise_refs],
                    "trace": [r.uid for r in q.outcome.uid_trace],
                    "materialized": (
                        q.materialization.ref.uid
                        if q.materialization is not None and q.materialization.ref is not None
                        else None
                    ),
                }
            )
        self.trace_view.setPlainText(json.dumps(trace_payload, ensure_ascii=False, indent=2))
        self.canvas.refresh()

    def _turn_error(self, message: str) -> None:
        self.chat_history.append(f"<b>ERROR:</b> {self._html(message)}")
        QMessageBox.critical(self, "Turn", message)

    @staticmethod
    def _html(text: str) -> str:
        import html
        return html.escape(text).replace("\n", "<br>")

    # ---------- config ----------
    def _config_saved(self, new_config: AppConfig, changed_paths: tuple[str, ...]) -> None:
        modes = {ConfigDocument.apply_mode(path) for path in changed_paths}
        try:
            # apply_config only swaps hot-safe policy holders. Persistence/identity
            # require process/runtime restart and are intentionally left untouched.
            self.services.apply_config(new_config)
            self.canvas.set_settings(new_config.gui)
            self.llm_panel.reload_prompts()
        except Exception as exc:
            QMessageBox.critical(self, "Config apply", str(exc))
            return

        self._llm_restart_required = ApplyMode.RESTART_LLM in modes
        self._runtime_restart_required = ApplyMode.RESTART_RUNTIME in modes
        if self._runtime_restart_required:
            self.statusBar().showMessage("Config сохранён: требуется перезапуск runtime", 6000)
        elif self._llm_restart_required:
            self.statusBar().showMessage("Config сохранён: требуется перезапуск LLM", 6000)
        else:
            self.statusBar().showMessage("Config применён", 2500)
        self._refresh_status()

    # ---------- diagnostics / inspector ----------
    def _select_node(self, uid: str) -> None:
        self._selected_uid = uid or None
        if self._selected_uid is not None:
            self._selected_edge_key = None
            self.canvas.set_selected_uid(self._selected_uid)
        elif self._selected_edge_key is None:
            self.canvas.set_selected_uid(None)
        self._refresh_inspector()

    def _select_edge(self, key: str) -> None:
        self._selected_edge_key = key or None
        if self._selected_edge_key is not None:
            self._selected_uid = None
            self.canvas.set_selected_edge_key(self._selected_edge_key)
        elif self._selected_uid is None:
            self.canvas.set_selected_edge_key(None)
        self._refresh_inspector()

    def _node_created(self, uid: str) -> None:
        self.canvas.refresh()
        self._selected_edge_key = None
        self._select_node(uid)
        self.statusBar().showMessage(f"Узел готов: {uid}", 3000)

    def _link_created(self, uid: str) -> None:
        self.canvas.refresh()
        self._selected_uid = None
        key = f"L:{uid}"
        self._selected_edge_key = key
        self.canvas.set_selected_edge_key(key)
        self._refresh_inspector()
        self.statusBar().showMessage(f"Связь готова: {uid}", 3000)

    def _refresh_inspector(self) -> None:
        if self._selected_uid:
            snap = self.services.graph_inspector.snapshot()
            node = next((n for n in snap.nodes if n.uid == self._selected_uid), None)
            if node is None:
                self.node_inspector.setPlainText("Узел больше не существует (GC).")
                return
            payload = {"selection": "node", **asdict(node)}
            payload["pending_incoming"] = snap.pending_incoming.get(node.uid, 0.0)
            self.node_inspector.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        if self._selected_edge_key:
            edge = self.canvas.edge_descriptor(self._selected_edge_key)
            if edge is None:
                self.node_inspector.setPlainText("Связь больше не отображается.")
                return
            payload = {
                "selection": "canonical_link" if edge.canonical_link else "structural_edge",
                "key": edge.key,
                "uid": edge.uid,
                "edge_kind": edge.edge_kind,
                "relation_id": edge.relation_id,
                "source_uid": edge.source_uid,
                "target_uid": edge.target_uid,
            }
            if edge.canonical_link and edge.uid:
                snap = self.services.graph_inspector.snapshot()
                link = next((item for item in snap.links if item.uid == edge.uid), None)
                if link is not None:
                    payload["weight"] = link.weight
            self.node_inspector.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        self.node_inspector.clear()
        self.node_inspector.setPlaceholderText("Выберите узел или связь на canvas")

    def _refresh_status(self) -> None:
        llm_running = bool(self.services.llm and self.services.llm.is_running)
        clock = self.services.clock.stats()
        snap = self.services.graph_inspector.snapshot()
        self.action_llm.setText("Остановить LLM" if llm_running else "Запустить LLM")
        self.action_ignition.setText("Остановить Ignition" if clock.running else "Запустить Ignition")
        restart = []
        if self._llm_restart_required:
            restart.append("LLM restart")
        if self._runtime_restart_required:
            restart.append("runtime restart")
        self.runtime_label.setText(
            f"tick={snap.tick} | nodes={len(snap.nodes)} | links={len(snap.links)} | "
            f"workspace={len(snap.workspace_uids)} | LLM={'ON' if llm_running else 'OFF'} | "
            f"Ignition={'ON' if clock.running else 'OFF'}"
            + (" | " + ", ".join(restart) if restart else "")
        )
        if clock.last_error:
            self.statusBar().showMessage(f"Ignition error: {clock.last_error}")
        self.llm_panel.refresh_status()
        self._refresh_inspector()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        try:
            self.services.stop(save=True)
        finally:
            super().closeEvent(event)
