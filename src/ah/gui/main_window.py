from __future__ import annotations

import sys
from dataclasses import asdict
import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QProcess, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QGuiApplication, QResizeEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QTabWidget,
    QWidget,
)

from ah.bootstrap import RuntimeServices
from ah.config import AppConfig
from ah.diagnostics import (
    load_acceptance_cases,
    load_semantic_oracle,
    run_acceptance_suite,
    load_document_specs,
    run_document_acceptance,
    run_hidden_valency_diagnostic,
    run_m2_attention_acceptance,
    validate_oracle_alignment,
    FormalizationTraceBuilder,
    ProofSnapshotBuilder,
    run_m3_gc_acceptance,
    score_m1_acceptance_bundle,
)

from .config_editor import ConfigEditor
from .config_store import ApplyMode, ConfigDocument
from .graph_canvas import GraphCanvasWidget
from .canvas_browser import CanvasBrowserWidget
from .ignition_tuning import IgnitionTuningWidget
from .node_manager import NodeManagerWidget
from .link_manager import LinkManagerWidget
from .llm_panel import LLMControlWidget
from .workspace_viewer import WorkspaceViewerWidget
from .inference_explorer import InferenceExplorerWidget
from .all_nodes_viewer import AllNodesViewerWidget
from .diagnostics_panel import DiagnosticsPanel
from .node_inspector import NodeInspectorWidget
from .document_panel import DocumentPanelWidget
from .metrics_panel import MetricsPanelWidget


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
        self._turn_sequence = 0
        self._chat_worker: FunctionWorker | None = None
        self._acceptance_worker: FunctionWorker | None = None
        self._active_acceptance_label = "Acceptance"
        self._active_acceptance_title = "Acceptance suite"
        self._document_acceptance_worker: FunctionWorker | None = None
        self._hidden_valency_worker: FunctionWorker | None = None
        self._m2_acceptance_worker: FunctionWorker | None = None
        self._document_ingest_worker: FunctionWorker | None = None
        self._document_context_worker: FunctionWorker | None = None
        self._document_summary_worker: FunctionWorker | None = None
        self._metrics_m1_worker: FunctionWorker | None = None
        self._metrics_m3_worker: FunctionWorker | None = None
        self._llm_operation_worker: FunctionWorker | None = None
        self._llm_operation_clears_restart = False
        self._selected_uid: str | None = None
        self._selected_edge_key: str | None = None
        self._llm_restart_required = False
        self._runtime_restart_required = False
        self._acceptance_status_suspended = False
        self._full_canvas_mode = False
        self._dock_visibility_before_full_canvas: dict[QDockWidget, bool] = {}
        self._workspace_mode = "graph"
        self._workspace_mode_actions: dict[str, QAction] = {}
        self._monitor_layout_class: str | None = None
        self.setDockNestingEnabled(True)

        self.setWindowTitle("AH Agent — Cognitive Runtime")
        self._fit_initial_window_to_screen()

        self.canvas = GraphCanvasWidget(services)
        self.canvas_browser = CanvasBrowserWidget(self.canvas, services.config, self)
        self.canvas_browser.live_node_selected.connect(self._select_node)
        self.canvas_browser.live_edge_selected.connect(self._select_edge)
        self.canvas_browser.sandbox_node_selected.connect(self._select_sandbox_node)
        self.canvas_browser.sandbox_edge_selected.connect(self._select_sandbox_edge)
        self.setCentralWidget(self.canvas_browser)

        self._build_toolbar()
        self._build_chat_dock()
        self._build_config_dock()
        self._build_llm_dock()
        self._build_inspector_dock()
        self._build_node_manager_dock()
        self._build_link_manager_dock()
        self._build_workspace_dock()
        self._build_all_nodes_dock()
        self._build_inference_dock()
        self._build_document_dock()
        self._build_metrics_dock()
        self._build_runtime_dock()
        self._build_workspace_mode_menu()

        # Runtime status includes a full GraphInspector snapshot. During acceptance
        # it is suspended to avoid duplicating the snapshot already rebuilt by the
        # live canvas timer. The VisPy canvas itself deliberately remains live so a
        # batch run can be observed as the AH grows. LLM diagnostics use a separate
        # lightweight timer and remain live as well.
        # Text/table diagnostics are deliberately much slower than the 30 Hz canvas.
        # Rebuilding Qt documents/tables several times per second dominates GUI time
        # once prompts and AH grow, while the cognitive clock itself is only 1 Hz.
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(1000)

        self.llm_status_timer = QTimer(self)
        self.llm_status_timer.timeout.connect(self._refresh_llm_status_if_visible)
        self.llm_status_timer.start(1000)

        self._refresh_status()
        self.llm_panel.refresh_status()

    def _fit_initial_window_to_screen(self) -> None:
        """Keep the initial window inside the usable desktop geometry.

        The old fixed 1580x980 startup size placed the bottom dock below the
        taskbar on common 1366x768/1600x900 screens. This is only an initial
        geometry policy: the user can still resize/maximize the window later.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1580, 980)
            return
        available = screen.availableGeometry()
        margin = 24
        width = min(1580, max(1, available.width() - margin))
        height = min(980, max(1, available.height() - margin))
        self.resize(width, height)

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

        self.action_clear_memory = QAction("Очистить память", self)
        self.action_clear_memory.setToolTip("Полностью очистить canonical AH/runtime/context; SELF/USER будут созданы заново.")
        self.action_clear_memory.triggered.connect(self._clear_memory)
        bar.addAction(self.action_clear_memory)

        bar.addSeparator()
        self.action_document = QAction("Документы", self)
        self.action_document.setToolTip("Полный document → AH pipeline и AH-only context")
        self.action_document.triggered.connect(self._show_document_panel)
        bar.addAction(self.action_document)

        self.action_inference_explorer = QAction("Логический вывод", self)
        self.action_inference_explorer.setToolTip(
            "Все live/M2 proof-цепочки: отдельный canvas, семантика шагов, UID trace и проверки."
        )
        self.action_inference_explorer.triggered.connect(self._show_inference_explorer)
        bar.addAction(self.action_inference_explorer)

        self.action_metrics = QAction("Метрики M1–M3", self)
        self.action_metrics.setToolTip("Отдельные вкладки M1, M2 и M3 с диагностическими canvas")
        self.action_metrics.triggered.connect(self._show_metrics_panel)
        bar.addAction(self.action_metrics)

        reset_camera = QAction("Сброс камеры", self)
        reset_camera.triggered.connect(lambda: self.canvas_browser.active_canvas.reset_camera())
        bar.addAction(reset_camera)

        self.action_full_canvas = QAction("Полный canvas", self)
        self.action_full_canvas.setCheckable(True)
        self.action_full_canvas.setShortcut("F11")
        self.action_full_canvas.setToolTip(
            "Скрыть все dock-панели и отдать центральную область целиком графу. F11 — вернуть панели."
        )
        self.action_full_canvas.toggled.connect(self._toggle_full_canvas)
        bar.addAction(self.action_full_canvas)

    def _build_workspace_mode_menu(self) -> None:
        """Workspace presets. MONITOR intentionally merges old INSPECT/RUNTIME modes."""
        bar = self.findChild(QToolBar)
        if bar is None:
            return
        bar.addSeparator()
        button = QToolButton(self)
        button.setText("Режим: GRAPH")
        button.setToolTip(
            "GRAPH — только Canvas; MONITOR — инспектор и runtime одновременно; "
            "EDIT — создание узлов/связей."
        )
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = button.menu()
        if menu is None:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(button)
            button.setMenu(menu)
        modes = (
            ("graph", "GRAPH", "Только граф: максимум места для Canvas"),
            (
                "monitor",
                "MONITOR",
                "Граф + Inspector + Workspace + Runtime/Trace + LLM + диалог одновременно",
            ),
            ("edit", "EDIT", "Граф + создание узлов и связей + Inspector"),
        )
        for key, title, tip in modes:
            action = QAction(title, self)
            action.setCheckable(True)
            action.setToolTip(tip)
            action.triggered.connect(lambda checked, mode=key: self._set_workspace_mode(mode))
            menu.addAction(action)
            self._workspace_mode_actions[key] = action
        self._workspace_mode_button = button
        bar.addWidget(button)
        self._set_workspace_mode("graph")

    def _set_workspace_mode(self, mode: str) -> None:
        if mode not in self._workspace_mode_actions:
            return
        self._workspace_mode = mode
        for key, action in self._workspace_mode_actions.items():
            action.setChecked(key == mode)
        self._workspace_mode_button.setText(f"Режим: {mode.upper()}")

        all_docks = (
            self.inspector_dock, self.node_dock, self.link_dock,
            self.workspace_dock, self.all_nodes_dock, self.inference_dock,
            self.llm_dock, self.config_dock, self.runtime_dock, self.chat_dock,
            self.document_dock, self.metrics_dock,
        )
        for dock in all_docks:
            dock.hide()
        self.llm_panel.set_monitor_compact(mode == "monitor")

        if mode == "monitor":
            # Rebuild only when entering MONITOR or crossing a responsive breakpoint.
            self._monitor_layout_class = None
            self._arrange_monitor_workspace(force=True)
        elif mode == "edit":
            self.node_dock.show()
            self.link_dock.show()
            self.inspector_dock.show()

        self.statusBar().showMessage({
            "graph": "Режим GRAPH: только Canvas",
            "monitor": "Режим MONITOR: Inspector и Runtime видны одновременно",
            "edit": "Режим EDIT: создание узлов и связей",
        }[mode], 2500)

    def _monitor_layout_for_width(self, width: int) -> str:
        """Return a responsive MONITOR layout class for the current window width."""
        if width >= 2300:
            return "wide"
        if width >= 1600:
            return "normal"
        return "compact"

    def _arrange_monitor_workspace(self, *, force: bool = False) -> None:
        """Arrange monitoring docks so Inspector and Runtime remain concurrently visible.

        Wide screens show auxiliary All Nodes and Config as separate panes. On normal
        and compact screens those two *controls* become tabs, while the information
        that must be watched live remains simultaneous: Inspector, Workspace,
        Runtime/Trace, LLM status/diagnostics and Dialog.
        """
        if self._workspace_mode != "monitor":
            return
        layout_class = self._monitor_layout_for_width(self.width())
        if not force and layout_class == self._monitor_layout_class:
            return
        self._monitor_layout_class = layout_class

        monitor_docks = (
            self.inspector_dock, self.workspace_dock, self.all_nodes_dock,
            self.runtime_dock, self.llm_dock, self.config_dock, self.chat_dock,
        )
        # removeDockWidget keeps each dock/widget alive but clears old split/tab
        # relationships, which makes breakpoint transitions deterministic.
        for dock in monitor_docks:
            self.removeDockWidget(dock)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.inspector_dock)
        self.splitDockWidget(self.inspector_dock, self.workspace_dock, Qt.Orientation.Vertical)

        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.runtime_dock)
        self.splitDockWidget(self.runtime_dock, self.llm_dock, Qt.Orientation.Vertical)

        if layout_class == "wide":
            self.splitDockWidget(self.workspace_dock, self.all_nodes_dock, Qt.Orientation.Vertical)
            self.splitDockWidget(self.llm_dock, self.config_dock, Qt.Orientation.Vertical)
        else:
            # These are auxiliary browse/config surfaces, not live-monitoring facts.
            # Keep them one click away without stealing permanent Canvas width/height.
            self.tabifyDockWidget(self.workspace_dock, self.all_nodes_dock)
            self.tabifyDockWidget(self.llm_dock, self.config_dock)

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.chat_dock)

        for dock in monitor_docks:
            dock.show()
        if layout_class != "wide":
            # show() may activate the last tabified dock; explicitly return to the
            # two live-monitoring surfaces after every responsive rebuild.
            self.workspace_dock.raise_()
            self.llm_dock.raise_()

        # Keep Canvas useful on 1366/1440/1600-class desktops. Widths are hints;
        # the user can still drag every splitter.
        if layout_class == "compact":
            side_width = max(250, min(330, self.width() // 4))
            self.resizeDocks(
                [self.inspector_dock, self.workspace_dock],
                [side_width, side_width],
                Qt.Orientation.Horizontal,
            )
            self.resizeDocks(
                [self.runtime_dock, self.llm_dock],
                [max(300, side_width + 40), max(300, side_width + 40)],
                Qt.Orientation.Horizontal,
            )
            self.resizeDocks(
                [self.inspector_dock, self.workspace_dock], [340, 260], Qt.Orientation.Vertical
            )
            self.resizeDocks(
                [self.runtime_dock, self.llm_dock], [340, 260], Qt.Orientation.Vertical
            )
            self.resizeDocks([self.chat_dock], [170], Qt.Orientation.Vertical)
        elif layout_class == "normal":
            self.resizeDocks(
                [self.inspector_dock, self.workspace_dock], [320, 320], Qt.Orientation.Horizontal
            )
            self.resizeDocks(
                [self.runtime_dock, self.llm_dock], [400, 400], Qt.Orientation.Horizontal
            )
            self.resizeDocks(
                [self.inspector_dock, self.workspace_dock], [460, 360], Qt.Orientation.Vertical
            )
            self.resizeDocks(
                [self.runtime_dock, self.llm_dock], [460, 360], Qt.Orientation.Vertical
            )
            self.resizeDocks([self.chat_dock], [200], Qt.Orientation.Vertical)
        else:
            self.resizeDocks(
                [self.inspector_dock, self.workspace_dock, self.all_nodes_dock],
                [360, 360, 360],
                Qt.Orientation.Horizontal,
            )
            self.resizeDocks(
                [self.runtime_dock, self.llm_dock, self.config_dock],
                [440, 440, 440],
                Qt.Orientation.Horizontal,
            )
            self.resizeDocks(
                [self.inspector_dock, self.workspace_dock, self.all_nodes_dock],
                [460, 330, 330],
                Qt.Orientation.Vertical,
            )
            self.resizeDocks(
                [self.runtime_dock, self.llm_dock, self.config_dock],
                [460, 330, 330],
                Qt.Orientation.Vertical,
            )
            self.resizeDocks([self.chat_dock], [220], Qt.Orientation.Vertical)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._workspace_mode == "monitor":
            self._arrange_monitor_workspace()

    def _build_chat_dock(self) -> None:
        dock = QDockWidget("Диалог", self)
        self.chat_dock = dock

        body = QWidget()
        body.setMinimumSize(0, 0)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)

        self.chat_history = QTextBrowser()
        self.chat_history.setMinimumHeight(48)
        self.chat_history.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.chat_input = QPlainTextEdit()
        self.chat_input.setPlaceholderText("Сообщение пользователю/агенту…")
        self.chat_input.setMaximumBlockCount(1000)
        self.chat_input.setMinimumHeight(48)
        self.chat_input.setMaximumHeight(90)
        self.chat_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.send_button = QPushButton("Отправить")
        self.send_button.clicked.connect(self._send_chat)
        self.acceptance_button = QPushButton("Прогнать acceptance-файл")
        self.acceptance_button.setToolTip(
            "Cases: " + str(self.services.config.paths.data_dir / "acceptance_cases.txt")
            + "\nOracle: " + str(self.services.config.paths.data_dir / "acceptance_oracle.json")
        )
        self.acceptance_button.clicked.connect(self._run_acceptance_cases)
        self.m1_adversarial_button = QPushButton("M1: adversarial acceptance")
        self.m1_adversarial_button.setToolTip(
            "Expanded breaker-cases: typo/noise, syntactic inversion, ellipsis и mixed.\n"
            "Cases: " + str(self.services.config.paths.data_dir / "acceptance_cases_m1_adversarial.txt")
            + "\nOracle: " + str(self.services.config.paths.data_dir / "acceptance_oracle_m1_adversarial.json")
        )
        self.m1_adversarial_button.clicked.connect(self._run_m1_adversarial_acceptance)
        self.m1_inversion_button = QPushButton("M1: inversion acceptance")
        self.m1_inversion_button.setToolTip(
            "Expanded order-independent semantic-role corpus.\n"
            "Cases: " + str(self.services.config.paths.data_dir / "acceptance_inversion" / "cases.txt")
            + "\nOracle: " + str(self.services.config.paths.data_dir / "acceptance_inversion" / "oracle.json")
        )
        self.m1_inversion_button.clicked.connect(self._run_m1_inversion_acceptance)
        self.m1_ellipsis_button = QPushButton("M1: ellipsis acceptance")
        self.m1_ellipsis_button.setToolTip(
            "Discourse reconstruction / ellipsis corpus.\n"
            "Cases: " + str(self.services.config.paths.data_dir / "acceptance_ellipsis" / "cases.txt")
            + "\\nOracle: " + str(self.services.config.paths.data_dir / "acceptance_ellipsis" / "oracle.json")
        )
        self.m1_ellipsis_button.clicked.connect(self._run_m1_ellipsis_acceptance)
        self.m1_typo_button = QPushButton("M1: typo/noise acceptance")
        self.m1_typo_button.setToolTip(
            "Lexical Recovery: edits, roles, inversion, ellipsis, protected OOV and ambiguity.\n"
            "Cases: " + str(self.services.config.paths.data_dir / "acceptance_typo" / "cases.txt")
            + "\nOracle: " + str(self.services.config.paths.data_dir / "acceptance_typo" / "oracle.json")
        )
        self.m1_typo_button.clicked.connect(self._run_m1_typo_acceptance)
        self.document_acceptance_button = QPushButton("Document acceptance")
        self.document_acceptance_button.setToolTip(
            "3 вручную написанных многоабзацных текста: причинные цепочки, distractors, "
            "cross-paragraph identity и готовые oracle paths для следующего этапа M2."
        )
        self.document_acceptance_button.clicked.connect(self._run_document_acceptance)
        self.hidden_valency_button = QPushButton("Hidden-valency preflight")
        self.hidden_valency_button.setToolTip(
            "12 LLM-вызовов: 6 semantic cases × 2 порядка binary labels. "
            "Диагностика не пишет в AH."
        )
        self.hidden_valency_button.clicked.connect(self._run_hidden_valency_diagnostic)
        self.m2_acceptance_button = QPushButton("M2: inference attention")
        self.m2_acceptance_button.setToolTip(
            "M2 на snapshot текущей AH без LLM: чистые CAUSE/FOLLOW/IS-A depth 1..6 + "
            "смешанные typed proofs (CAUSE→FOLLOW→IS-A) с общей depth до 6, cold/warm/branches. "
            "После прогона полный M2 sandbox доступен в Canvas Browser, а каждый proof — "
            "в dock-виджете «Логический вывод»."
        )
        self.m2_acceptance_button.clicked.connect(self._run_m2_acceptance)
        chat_buttons = QHBoxLayout()
        chat_buttons.addWidget(self.send_button)
        chat_buttons.addWidget(self.acceptance_button)
        m1_buttons = QHBoxLayout()
        m1_buttons.addWidget(self.m1_adversarial_button)
        m1_buttons.addWidget(self.m1_inversion_button)
        m1_buttons.addWidget(self.m1_ellipsis_button)
        m1_buttons.addWidget(self.m1_typo_button)
        diagnostic_buttons = QHBoxLayout()
        diagnostic_buttons.addWidget(self.document_acceptance_button)
        diagnostic_buttons.addWidget(self.hidden_valency_button)
        diagnostic_buttons.addWidget(self.m2_acceptance_button)
        layout.addWidget(self.chat_history, 1)
        layout.addWidget(self.chat_input)
        layout.addLayout(chat_buttons)
        layout.addLayout(m1_buttons)
        layout.addLayout(diagnostic_buttons)

        # A dock may be squeezed to a very small height by other panels. Keep the
        # controls reachable instead of letting the bottom rows disappear below
        # the viewport. QTextBrowser/QPlainTextEdit retain their own text scrolling;
        # this scroll area is for the dialog *layout* itself.
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.chat_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_scroll.setWidget(body)
        self.chat_scroll.setMinimumSize(0, 0)
        dock.setWidget(self.chat_scroll)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def _build_config_dock(self) -> None:
        dock = QDockWidget("Конфигурация", self)
        self.config_dock = dock
        self.config_editor = ConfigEditor(self.config_path)
        self.config_editor.config_saved.connect(self._config_saved)
        dock.setWidget(self.config_editor)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_llm_dock(self) -> None:
        dock = QDockWidget("LLM", self)
        self.llm_dock = dock
        self.llm_panel = LLMControlWidget(self.services)
        self.llm_panel.start_requested.connect(self._start_llm)
        self.llm_panel.stop_requested.connect(self._stop_llm)
        self.llm_panel.restart_requested.connect(self._restart_llm)
        self.llm_panel.prompts_saved.connect(
            lambda: self.statusBar().showMessage("LLM prompt-файлы сохранены", 3000)
        )
        dock.setWidget(self.llm_panel)
        dock.visibilityChanged.connect(lambda visible: self.llm_panel.refresh_status(force=True) if visible else None)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_inspector_dock(self) -> None:
        dock = QDockWidget("Узел / Связь", self)
        self.inspector_dock = dock
        self.node_inspector = NodeInspectorWidget(self.services, self)
        dock.setWidget(self.node_inspector)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_node_manager_dock(self) -> None:
        dock = QDockWidget("Добавление узла", self)
        self.node_dock = dock
        self.node_manager = NodeManagerWidget(
            self.services,
            selected_uid=lambda: self._selected_uid,
        )
        self.node_manager.node_created.connect(self._node_created)
        dock.setWidget(self.node_manager)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_link_manager_dock(self) -> None:
        dock = QDockWidget("Связи", self)
        self.link_dock = dock
        self.link_manager = LinkManagerWidget(
            self.services,
            selected_uid=lambda: self._selected_uid,
        )
        self.link_manager.link_created.connect(self._link_created)
        dock.setWidget(self.link_manager)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_workspace_dock(self) -> None:
        dock = QDockWidget("Workspace", self)
        self.workspace_dock = dock
        self.workspace_view = WorkspaceViewerWidget(self)
        self.workspace_view.node_selected.connect(self._select_node)
        dock.setWidget(self.workspace_view)
        dock.visibilityChanged.connect(lambda visible: self._refresh_status(force=True) if visible else None)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_all_nodes_dock(self) -> None:
        dock = QDockWidget("Все узлы", self)
        self.all_nodes_dock = dock
        self.all_nodes_view = AllNodesViewerWidget(self)
        self.all_nodes_view.node_selected.connect(self._select_node)
        dock.setWidget(self.all_nodes_view)
        dock.visibilityChanged.connect(lambda visible: self._refresh_status(force=True) if visible else None)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_inference_dock(self) -> None:
        dock = QDockWidget("Логический вывод", self)
        self.inference_dock = dock
        self.inference_explorer = InferenceExplorerWidget(self)
        self.inference_explorer.overlay_requested.connect(self._show_proof_on_main_canvas)
        self.inference_explorer.clear_overlay_requested.connect(
            self.canvas_browser.clear_proof_highlights
        )
        dock.setWidget(self.inference_explorer)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.hide()

    def _build_document_dock(self) -> None:
        dock = QDockWidget("Документ → AH", self)
        self.document_dock = dock
        self.document_panel = DocumentPanelWidget(self)
        self.document_panel.ingest_requested.connect(self._ingest_document_from_gui)
        self.document_panel.activate_requested.connect(self._build_document_context_from_gui)
        self.document_panel.summary_requested.connect(self._summarize_document_from_gui)
        dock.setWidget(self.document_panel)
        dock.setMinimumWidth(520)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.hide()

    def _show_document_panel(self) -> None:
        if self._workspace_mode != "graph":
            self._set_workspace_mode("graph")
        self.document_dock.setFloating(False)
        self.document_dock.show()
        self.document_dock.raise_()
        width = max(440, min(650, self.width() // 2))
        self.resizeDocks([self.document_dock], [width], Qt.Orientation.Horizontal)
        self.statusBar().showMessage("Открыта отдельная вкладка document → AH", 2500)

    def _document_operation_running(self) -> bool:
        return any(
            worker is not None
            for worker in (
                self._document_ingest_worker,
                self._document_context_worker,
                self._document_summary_worker,
            )
        )

    def _ingest_document_from_gui(self, path: str) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return
        if self.services.perception is None:
            QMessageBox.warning(self, "Документ", "Запустите LLM perception перед ingestion.")
            return
        if not Path(path).is_file():
            QMessageBox.warning(self, "Документ", f"Файл не найден:\n{path}")
            return
        self.document_panel.set_busy(True)
        self.document_panel.status.setText("Perception всех chunks → единый DOCUMENT commit…")
        worker = FunctionWorker(lambda: self.services.document_processor().ingest_file(path))
        self._document_ingest_worker = worker
        worker.signals.result.connect(self._document_ingest_finished)
        worker.signals.error.connect(self._document_operation_error)
        worker.signals.finished.connect(self._document_ingest_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _document_ingest_finished(self, result) -> None:
        self.document_panel.set_ingestion_result(result)
        try:
            trace = FormalizationTraceBuilder(
                self.services.core,
                self.services.ignition,
                runtime_lock=self.services.operation_lock,
            ).build(
                result.integration,
                trace_id=f"document:{result.source_ref}",
                source="DOCUMENT",
                title=result.title or result.source_ref,
                source_text=result.source_text,
            )
            self.metrics_panel.add_m1_trace(trace, select=False)
        except Exception:
            # A visualization failure must not roll back an already committed document.
            pass
        self.canvas.refresh()
        self._refresh_status(force=True)
        self.statusBar().showMessage(
            f"Документ загружен: {len(result.chunks)} chunks, coverage {result.coverage_ratio:.1%}",
            7000,
        )

    @Slot(str)
    def _document_operation_error(self, message: str) -> None:
        self.document_panel.set_busy(False)
        self.document_panel.status.setText(f"Ошибка: {message}")
        QMessageBox.critical(self, "Document pipeline", message)

    @Slot()
    def _document_ingest_worker_finished(self) -> None:
        self._document_ingest_worker = None
        self.document_panel.set_busy(False)

    def _build_document_context_from_gui(self, source_ref: str) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return
        request = self.document_panel.summary_request.text().strip()
        self.document_panel.set_busy(True)
        self.document_panel.status.setText("Строю полный source-scoped AgentContext…")
        worker = FunctionWorker(
            lambda: self.services.document_processor().build_context(
                source_ref, request=request
            )
        )
        self._document_context_worker = worker
        worker.signals.result.connect(self._document_context_finished)
        worker.signals.error.connect(self._document_operation_error)
        worker.signals.finished.connect(self._document_context_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _document_context_finished(self, result) -> None:
        self.document_panel.set_context(result.rendered_context, result.workspace_refs)
        self.canvas.refresh()
        self._refresh_status(force=True)
        self.statusBar().showMessage(
            f"Source context готов: ~{result.estimated_tokens} tokens", 6000
        )

    @Slot()
    def _document_context_worker_finished(self) -> None:
        self._document_context_worker = None
        self.document_panel.set_busy(False)

    def _summarize_document_from_gui(self, source_ref: str, request: str) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return
        if self.services.agent is None:
            QMessageBox.warning(self, "Document summary", "Запустите LLM agent перед summary.")
            return
        self.document_panel.set_busy(True)
        self.document_panel.status.setText("Source scope → AgentContext → LLM summary…")
        worker = FunctionWorker(
            lambda: self.services.document_processor().summarize(source_ref, request=request)
        )
        self._document_summary_worker = worker
        worker.signals.result.connect(self._document_summary_finished)
        worker.signals.error.connect(self._document_operation_error)
        worker.signals.finished.connect(self._document_summary_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _document_summary_finished(self, result) -> None:
        self.document_panel.set_context(result.rendered_context, result.workspace_refs)
        self.document_panel.set_summary(result.text)
        self.canvas.refresh()
        self.chat_history.append(
            f"<b>Document summary:</b> source={self._html(result.source_ref)}<br>"
            f"{self._html(result.text)}"
        )
        self.statusBar().showMessage("Memory-grounded document summary готов", 7000)

    @Slot()
    def _document_summary_worker_finished(self) -> None:
        self._document_summary_worker = None
        self.document_panel.set_busy(False)

    def _build_metrics_dock(self) -> None:
        dock = QDockWidget("Метрики M1–M3", self)
        self.metrics_dock = dock
        self.metrics_panel = MetricsPanelWidget(self.services, self)
        self.metrics_panel.m1_score_requested.connect(self._score_m1_from_gui)
        self.metrics_panel.m2_run_requested.connect(self._run_m2_acceptance)
        self.metrics_panel.m3_run_requested.connect(self._run_m3_from_gui)
        dock.setWidget(self.metrics_panel)
        dock.setMinimumWidth(620)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.hide()

    def _show_metrics_panel(self) -> None:
        if self._workspace_mode != "graph":
            self._set_workspace_mode("graph")
        self.metrics_dock.setFloating(False)
        self.metrics_dock.show()
        self.metrics_dock.raise_()
        width = max(620, min(1000, (self.width() * 2) // 3))
        self.resizeDocks([self.metrics_dock], [width], Qt.Orientation.Horizontal)
        self.statusBar().showMessage("Открыты отдельные вкладки метрик M1–M3", 2500)

    def _score_m1_from_gui(self, run_dir: str) -> None:
        if self._metrics_m1_worker is not None:
            return
        path = Path(run_dir)
        if not path.is_dir():
            QMessageBox.warning(self, "M1", f"Папка не найдена:\n{path}")
            return
        worker = FunctionWorker(lambda: score_m1_acceptance_bundle(path))
        self._metrics_m1_worker = worker
        worker.signals.result.connect(self._m1_score_finished)
        worker.signals.error.connect(self._metrics_worker_error)
        worker.signals.finished.connect(self._m1_score_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _m1_score_finished(self, report) -> None:
        self.metrics_panel.set_m1_report(report)
        self.statusBar().showMessage(f"M1 weighted F1 = {report.weighted_mean:.3f}", 5000)

    @Slot()
    def _m1_score_worker_finished(self) -> None:
        self._metrics_m1_worker = None

    def _run_m3_from_gui(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return
        worker = FunctionWorker(lambda: run_m3_gc_acceptance(self.services.config))
        self._metrics_m3_worker = worker
        worker.signals.result.connect(self._m3_from_gui_finished)
        worker.signals.error.connect(self._metrics_worker_error)
        worker.signals.finished.connect(self._m3_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _m3_from_gui_finished(self, report) -> None:
        self.metrics_panel.set_m3_report(report)
        self.statusBar().showMessage(f"M3: {'PASS' if report.passed else 'FAIL'}", 6000)

    @Slot(str)
    def _metrics_worker_error(self, message: str) -> None:
        QMessageBox.critical(self, "Метрики", message)

    @Slot()
    def _m3_worker_finished(self) -> None:
        self._metrics_m3_worker = None

    def _build_runtime_dock(self) -> None:
        dock = QDockWidget("Runtime / Trace", self)
        self.runtime_dock = dock

        runtime_body = QWidget()
        layout = QVBoxLayout(runtime_body)
        self.ignition_tuning = IgnitionTuningWidget(
            self.services.config.ignition.decay,
            self.services.config.ignition.tick_interval_seconds,
            self.services.config.ignition.seeds.resolved_symbol,
            ignition=self.services.config.ignition,
            workspace=self.services.config.workspace,
        )
        self.ignition_tuning.tuning_changed.connect(self._tune_ignition_decay_live)
        self.ignition_tuning.tuning_committed.connect(self._commit_ignition_decay_tuning)
        self.ignition_tuning.mechanism_changed.connect(self._tune_ignition_mechanism_live)
        self.ignition_tuning.mechanism_committed.connect(self._commit_ignition_mechanism_tuning)
        self.ignition_tuning.corpus_import_requested.connect(self._import_corpus_from_gui)
        self.ignition_tuning.raw_text_import_requested.connect(self._import_raw_text_from_gui)
        self.ignition_tuning.memory_import_requested.connect(self._import_memory_from_gui)
        self.manual_seed_button = QPushButton()
        self.manual_seed_button.setToolTip(
            "Передать тестовый импульс выбранному excitable узлу. Величина берётся из "
            "ignition.seeds.reactivated_fact. Если Ignition остановлен, сразу выполняется один tick."
        )
        self.manual_seed_button.clicked.connect(self._seed_selected_node)
        self._refresh_manual_seed_button()
        self.runtime_label = QLabel()
        self.runtime_label.setWordWrap(True)
        self.runtime_label.setMinimumWidth(0)
        self.visual_legend = QLabel(
            "Красный = excitation x; движущийся красный хвост = source → target; "
            "w не затухает визуально и показывается отдельно в инспекторе."
        )
        self.visual_legend.setWordWrap(True)
        self.trace_view = QPlainTextEdit()
        self.trace_view.setReadOnly(True)
        layout.addWidget(self.ignition_tuning)
        layout.addWidget(self.manual_seed_button)
        layout.addWidget(self.runtime_label)
        layout.addWidget(self.visual_legend)
        layout.addWidget(self.trace_view, 1)

        self.diagnostics_panel = DiagnosticsPanel(self.services, self)
        self.diagnostics_panel.save_requested.connect(self._save_memory)
        self.diagnostics_panel.reload_requested.connect(self._reload_from_disk)

        tabs = QTabWidget()
        tabs.addTab(runtime_body, "Runtime")
        tabs.addTab(self.diagnostics_panel, "Diagnostics")
        dock.setWidget(tabs)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    # ---------- runtime controls ----------
    def _cognitive_run_active(self) -> bool:
        """Serialize every operation that reads/mutates the shared live runtime."""
        return any(
            worker is not None
            for worker in (
                self._chat_worker,
                self._acceptance_worker,
                self._document_acceptance_worker,
                self._hidden_valency_worker,
                self._m2_acceptance_worker,
                self._document_ingest_worker,
                self._document_context_worker,
                self._document_summary_worker,
                self._metrics_m3_worker,
                self._llm_operation_worker,
            )
        )

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
        if self._llm_operation_worker is not None:
            return
        self.action_llm.setEnabled(False)
        worker = FunctionWorker(fn)
        self._llm_operation_worker = worker
        self._llm_operation_clears_restart = clears_restart
        worker.signals.error.connect(self._llm_operation_error)
        worker.signals.result.connect(self._llm_operation_result)
        worker.signals.finished.connect(self._llm_operation_finished)
        self.thread_pool.start(worker)

    @Slot(str)
    def _llm_operation_error(self, message: str) -> None:
        QMessageBox.critical(self, "LLM", message)

    @Slot(object)
    def _llm_operation_result(self, _value) -> None:
        if self._llm_operation_clears_restart:
            self._llm_restart_required = False

    @Slot()
    def _llm_operation_finished(self) -> None:
        self._llm_operation_worker = None
        self._llm_operation_clears_restart = False
        self.action_llm.setEnabled(True)
        self._refresh_status()

    def _start_llm(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Диагностический run использует LLM", 2500)
            return
        llm = self.services.llm
        if llm is None:
            QMessageBox.warning(self, "LLM", "LLM отключена в конфиге.")
            return
        if llm.is_running:
            return
        self._run_llm_operation(llm.start, clears_restart=True)

    def _stop_llm(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Диагностический run использует LLM", 2500)
            return
        llm = self.services.llm
        if llm is None or not llm.is_running:
            return
        self._run_llm_operation(llm.stop)

    def _restart_llm(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Диагностический run использует LLM", 2500)
            return
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
            self.diagnostics_panel.record_tick(result)
        except Exception as exc:
            QMessageBox.critical(self, "Tick", str(exc))

    def _reload_from_disk(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Дождитесь окончания текущей операции перед Reload Memory", 3000)
            return
        answer = QMessageBox.question(
            self,
            "Reload Memory",
            "Перезапустить GUI и заново загрузить сохранённую память с диска? "
            "Несохранённые изменения будут потеряны.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.services.stop(save=False)
        except Exception:
            pass
        QProcess.startDetached(
            sys.executable,
            ["-m", "ah.gui.app", "--config", str(self.config_path)],
        )
        self.close()

    def _save_memory(self) -> None:
        try:
            with self.services.operation_lock:
                self.services.save()
        except Exception as exc:
            QMessageBox.critical(self, "Persistence", str(exc))
        else:
            self.statusBar().showMessage("AH сохранена", 2500)

    def _clear_memory(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Дождитесь окончания текущего cognitive run", 2500)
            return
        answer = QMessageBox.question(
            self, "Очистить память",
            "Удалить все canonical узлы/связи, runtime excitation и контекст диалога?\nSELF/USER будут созданы заново.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.services.reset_memory(persist=True)
        except Exception as exc:
            QMessageBox.critical(self, "Память", str(exc)); return
        self._last_turn = None; self._selected_uid = None; self._selected_edge_key = None
        self.chat_history.clear(); self.canvas_browser.live_canvas.refresh(); self._refresh_status(force=True)
        self.statusBar().showMessage("Память очищена", 4000)

    # ---------- chat ----------
    def _send_chat(self) -> None:
        # Only one cognitive turn may mutate the shared runtime at a time. Keeping
        # an explicit Python reference to the QRunnable also prevents Qt/PySide from
        # deleting the worker wrapper before its queued completion signal is
        # delivered. The previous implementation kept the worker only in a local
        # variable and re-enabled the button through a lambda, which is fragile
        # across worker-thread/UI-thread boundaries.
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2000)
            return

        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        if self.services.llm is None or not self.services.llm.is_running:
            QMessageBox.warning(self, "Диалог", "Сначала запустите локальную LLM.")
            return

        self.chat_input.clear()
        self.chat_history.append(f"<b>{self.services.config.identity.user_name}:</b> {self._html(text)}")
        self.send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.llm_panel.begin_turn(text)

        def run_turn():
            orchestrator = self.services.create_orchestrator()
            return orchestrator.handle_user_text(text)

        worker = FunctionWorker(run_turn)
        self._chat_worker = worker
        worker.signals.result.connect(self._turn_finished)
        worker.signals.error.connect(self._turn_error)
        # Connect to a QObject slot owned by MainWindow instead of a bare lambda so
        # UI cleanup is always queued onto the GUI thread.
        worker.signals.finished.connect(self._chat_worker_finished)
        self.thread_pool.start(worker)

    def _run_acceptance_cases(self) -> None:
        self._run_acceptance_pair(
            cases_filename="acceptance_cases.txt",
            oracle_filename="acceptance_oracle.json",
            runs_dirname="acceptance_runs",
            label="Acceptance",
            title="Acceptance suite",
        )

    def _run_m1_adversarial_acceptance(self) -> None:
        self._run_acceptance_pair(
            cases_filename="acceptance_cases_m1_adversarial.txt",
            oracle_filename="acceptance_oracle_m1_adversarial.json",
            runs_dirname="acceptance_runs_m1_adversarial",
            label="M1 adversarial",
            title="M1 adversarial acceptance",
        )

    def _run_m1_inversion_acceptance(self) -> None:
        self._run_acceptance_pair(
            cases_filename="acceptance_inversion/cases.txt",
            oracle_filename="acceptance_inversion/oracle.json",
            runs_dirname="acceptance_runs_m1_inversion",
            label="M1 inversion",
            title="M1 inversion acceptance",
        )

    def _run_m1_ellipsis_acceptance(self) -> None:
        self._run_acceptance_pair(
            cases_filename="acceptance_ellipsis/cases.txt",
            oracle_filename="acceptance_ellipsis/oracle.json",
            runs_dirname="acceptance_runs_m1_ellipsis",
            label="M1 ellipsis",
            title="M1 ellipsis acceptance",
        )

    def _run_m1_typo_acceptance(self) -> None:
        self._run_acceptance_pair(
            cases_filename="acceptance_typo/cases.txt",
            oracle_filename="acceptance_typo/oracle.json",
            runs_dirname="acceptance_runs_m1_typo",
            label="M1 typo/noise",
            title="M1 typo/noise acceptance",
        )

    def _run_acceptance_pair(
        self,
        *,
        cases_filename: str,
        oracle_filename: str,
        runs_dirname: str,
        label: str,
        title: str,
    ) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return
        if self._llm_operation_worker is not None:
            self.statusBar().showMessage("Дождитесь завершения операции LLM", 2500)
            return
        if self.services.llm is None or not self.services.llm.is_running:
            QMessageBox.warning(self, title, "Сначала запустите локальную LLM.")
            return

        cases_file = self.services.config.paths.data_dir / cases_filename
        oracle_file = self.services.config.paths.data_dir / oracle_filename
        try:
            cases = load_acceptance_cases(cases_file)
            oracle = load_semantic_oracle(oracle_file)
            validate_oracle_alignment(cases, oracle)
        except Exception as exc:
            QMessageBox.critical(self, title, f"{type(exc).__name__}: {exc}")
            return

        self._active_acceptance_label = label
        self._active_acceptance_title = title
        self.send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.acceptance_button.setEnabled(False)
        self.m1_adversarial_button.setEnabled(False)
        self.m1_inversion_button.setEnabled(False)
        self.m1_ellipsis_button.setEnabled(False)
        self.m1_typo_button.setEnabled(False)
        self.document_acceptance_button.setEnabled(False)
        self.hidden_valency_button.setEnabled(False)
        self.m2_acceptance_button.setEnabled(False)
        self.action_llm.setEnabled(False)
        self.action_ignition.setEnabled(False)
        self.action_tick.setEnabled(False)
        self.action_save.setEnabled(False)
        self.chat_history.append(
            f"<b>{self._html(label)}:</b> запускаю {len(cases)} запросов с semantic oracle: "
            f"{self._html(str(cases_file))}."
        )
        self.statusBar().showMessage(f"{label}: 0/{len(cases)} — выполняется")
        self._suspend_acceptance_status_polling()

        def run_suite():
            return run_acceptance_suite(
                self.services,
                cases_file=cases_file,
                oracle_file=oracle_file,
                runs_dirname=runs_dirname,
            )

        worker = FunctionWorker(run_suite)
        self._acceptance_worker = worker
        worker.signals.result.connect(self._acceptance_finished)
        worker.signals.error.connect(self._acceptance_error)
        worker.signals.finished.connect(self._acceptance_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _acceptance_finished(self, result) -> None:
        if getattr(result, "proofs", ()):
            self.inference_explorer.add_chains(result.proofs, select_last=False)
            self.metrics_panel.add_m2_chains(result.proofs, select_last=False)
        if getattr(result, "formalization_traces", ()):
            self.metrics_panel.add_m1_traces(result.formalization_traces, select_last=True)
        label = self._active_acceptance_label
        self.chat_history.append(
            f"<b>{self._html(label)}:</b> semantic PASS {result.semantic_passed}/{result.total}, "
            f"FAIL {result.semantic_failed}, GAP {result.semantic_gaps}; "
            f"runtime ERROR {result.failed}. Результаты: {self._html(str(result.output_dir))}"
        )
        self.statusBar().showMessage(
            f"Semantic PASS {result.semantic_passed}/{result.total}; "
            f"FAIL {result.semantic_failed}; GAP {result.semantic_gaps}",
            10000,
        )
        if label.startswith("M1"):
            self.metrics_panel.m1_path.setText(str(result.output_dir))
            self._score_m1_from_gui(str(result.output_dir))
        QMessageBox.information(
            self,
            self._active_acceptance_title,
            f"Прогон завершён.\n\n"
            f"SEMANTIC PASS: {result.semantic_passed}/{result.total}\n"
            f"SEMANTIC FAIL: {result.semantic_failed}\n"
            f"ARCHITECTURE GAP: {result.semantic_gaps}\n\n"
            f"Runtime OK: {result.succeeded}/{result.total}\n"
            f"Runtime ERROR: {result.failed}\n\n"
            f"Результаты:\n{result.output_dir}",
        )

    @Slot(str)
    def _acceptance_error(self, message: str) -> None:
        label = self._active_acceptance_label
        self.chat_history.append(f"<b>{self._html(label)} ERROR:</b> {self._html(message)}")
        QMessageBox.critical(self, self._active_acceptance_title, message)

    @Slot()
    def _acceptance_worker_finished(self) -> None:
        self._acceptance_worker = None
        self.send_button.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.acceptance_button.setEnabled(True)
        self.m1_adversarial_button.setEnabled(True)
        self.m1_inversion_button.setEnabled(True)
        self.m1_ellipsis_button.setEnabled(True)
        self.m1_typo_button.setEnabled(True)
        self.document_acceptance_button.setEnabled(True)
        self.hidden_valency_button.setEnabled(True)
        self.m2_acceptance_button.setEnabled(True)
        self.action_llm.setEnabled(True)
        self.action_ignition.setEnabled(True)
        self.action_tick.setEnabled(True)
        self.action_save.setEnabled(True)
        self.chat_input.setFocus()
        self._resume_acceptance_status_polling()
        self._active_acceptance_label = "Acceptance"
        self._active_acceptance_title = "Acceptance suite"

    def _run_document_acceptance(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return
        if self._llm_operation_worker is not None:
            self.statusBar().showMessage("Дождитесь завершения операции LLM", 2500)
            return
        if self.services.llm is None or not self.services.llm.is_running:
            QMessageBox.warning(self, "Document acceptance", "Сначала запустите локальную LLM.")
            return
        try:
            specs = load_document_specs(self.services.config.paths.data_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Document acceptance", f"{type(exc).__name__}: {exc}")
            return

        self.send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.acceptance_button.setEnabled(False)
        self.m1_adversarial_button.setEnabled(False)
        self.m1_inversion_button.setEnabled(False)
        self.m1_ellipsis_button.setEnabled(False)
        self.m1_typo_button.setEnabled(False)
        self.document_acceptance_button.setEnabled(False)
        self.hidden_valency_button.setEnabled(False)
        self.m2_acceptance_button.setEnabled(False)
        self.action_llm.setEnabled(False)
        self.action_ignition.setEnabled(False)
        self.action_tick.setEnabled(False)
        self.action_save.setEnabled(False)
        paragraph_count = sum(len(item.paragraphs) for item in specs)
        self.chat_history.append(
            f"<b>Document acceptance:</b> запускаю {len(specs)} текста / {paragraph_count} абзацев. "
            "Каждый текст идёт как единый scenario с общей AH между абзацами."
        )
        self.statusBar().showMessage(f"Document acceptance: 0/{paragraph_count} абзацев — выполняется")
        self._suspend_acceptance_status_polling()

        worker = FunctionWorker(lambda: run_document_acceptance(self.services))
        self._document_acceptance_worker = worker
        worker.signals.result.connect(self._document_acceptance_finished)
        worker.signals.error.connect(self._document_acceptance_error)
        worker.signals.finished.connect(self._document_acceptance_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _document_acceptance_finished(self, result) -> None:
        self.chat_history.append(
            f"<b>Document acceptance:</b> documents PASS {result.passed_documents}/{result.total_documents}; "
            f"paragraph semantic {result.paragraph_semantic_passed}/{result.total_paragraphs}; "
            f"runtime ERROR {result.runtime_errors}. Результаты: {self._html(str(result.output_dir))}"
        )
        self.statusBar().showMessage(
            f"Document PASS {result.passed_documents}/{result.total_documents}; "
            f"paragraphs {result.paragraph_semantic_passed}/{result.total_paragraphs}",
            10000,
        )
        QMessageBox.information(
            self,
            "Document acceptance",
            f"Прогон завершён.\n\n"
            f"DOCUMENT PASS: {result.passed_documents}/{result.total_documents}\n"
            f"DOCUMENT FAIL: {result.failed_documents}\n\n"
            f"Paragraph semantic PASS: {result.paragraph_semantic_passed}/{result.total_paragraphs}\n"
            f"Paragraph semantic FAIL/GAP: {result.paragraph_semantic_failed}\n"
            f"Runtime ERROR: {result.runtime_errors}\n\n"
            f"Результаты:\n{result.output_dir}",
        )

    @Slot(str)
    def _document_acceptance_error(self, message: str) -> None:
        self.chat_history.append(f"<b>DOCUMENT ACCEPTANCE ERROR:</b> {self._html(message)}")
        QMessageBox.critical(self, "Document acceptance", message)

    @Slot()
    def _document_acceptance_worker_finished(self) -> None:
        self._document_acceptance_worker = None
        self.send_button.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.acceptance_button.setEnabled(True)
        self.m1_adversarial_button.setEnabled(True)
        self.m1_inversion_button.setEnabled(True)
        self.m1_ellipsis_button.setEnabled(True)
        self.m1_typo_button.setEnabled(True)
        self.document_acceptance_button.setEnabled(True)
        self.hidden_valency_button.setEnabled(True)
        self.m2_acceptance_button.setEnabled(True)
        self.action_llm.setEnabled(True)
        self.action_ignition.setEnabled(True)
        self.action_tick.setEnabled(True)
        self.action_save.setEnabled(True)
        self.chat_input.setFocus()
        self._resume_acceptance_status_polling()

    def _run_m2_acceptance(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return

        # The runner snapshots the *current* AH/runtime under operation_lock, pads
        # the sandbox to >=150k UIDs when necessary, and executes real Ignition
        # attention during proof. Live memory is never polluted by M2 fixtures.
        self.m2_acceptance_button.setEnabled(False)
        self.acceptance_button.setEnabled(False)
        self.m1_adversarial_button.setEnabled(False)
        self.m1_inversion_button.setEnabled(False)
        self.m1_ellipsis_button.setEnabled(False)
        self.m1_typo_button.setEnabled(False)
        self.document_acceptance_button.setEnabled(False)
        self.hidden_valency_button.setEnabled(False)
        self.send_button.setEnabled(False)
        self.chat_history.append(
            "<b>M2 acceptance:</b> запускаю attention-driven suite на snapshot текущей AH: "
            "pure + mixed CAUSE/FOLLOW/IS-A, общая logical depth до 6, cold/warm/branches, >=150k UIDs."
        )
        self.statusBar().showMessage("M2 inference/attention acceptance — выполняется")

        worker = FunctionWorker(
            lambda: run_m2_attention_acceptance(
                data_dir=self.services.config.paths.data_dir,
                inference_settings=self.services.config.inference,
                ignition_settings=self.services.config.ignition,
                workspace_settings=self.services.config.workspace,
                lifecycle_settings=self.services.config.lifecycle,
                base_core=self.services.core,
                base_ignition=self.services.ignition,
                runtime_lock=self.services.operation_lock,
            )
        )
        self._m2_acceptance_worker = worker
        worker.signals.result.connect(self._m2_acceptance_finished)
        worker.signals.error.connect(self._m2_acceptance_error)
        worker.signals.finished.connect(self._m2_acceptance_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _m2_acceptance_finished(self, result) -> None:
        self.metrics_panel.set_m2_acceptance_result(result)
        self.canvas_browser.set_sandbox_snapshot(
            result.sandbox_snapshot,
            total_uids=result.ah_uids,
            hidden_stress_uids=result.cold_uids_added,
        )
        self.canvas_browser.show_sandbox()
        proofs = [case.proof for case in result.cases if case.proof is not None]
        self.inference_explorer.add_chains(proofs, select_last=True)
        self._show_inference_explorer()
        self.chat_history.append(
            f"<b>M2 acceptance:</b> PASS {result.passed}/{result.total}, "
            f"FAIL {result.failed}. Результаты: {self._html(str(result.output_dir))}"
        )
        self.statusBar().showMessage(
            f"M2 acceptance: PASS {result.passed}/{result.total}; FAIL {result.failed}",
            10000,
        )
        QMessageBox.information(
            self,
            "M2 inference attention acceptance",
            f"Прогон завершён.\n\n"
            f"PASS: {result.passed}/{result.total}\n"
            f"FAIL: {result.failed}\n"
            f"Sandbox AH: {result.ah_uids} UIDs\n"
            f"Workspace: {result.initial_workspace_count} -> {result.final_workspace_count}\n\n"
            f"Холодный Workspace — только purity control первого case.\n"
            f"Live AH не изменялась. LLM не использовалась.\n\n"
            f"Все {result.total} cases загружены в dock-виджет «Логический вывод»: "
            f"proof-canvas, формальная Goal/Stop диагностика, семантика, UID trace и проверки.\n"
            f"Тестовый sandbox доступен через Canvas: «Обычный AH / M2 sandbox». "
            f"Синтетический stress-noise учитывается в размере AH, но скрыт из рендера canvas.\n\n"
            f"Результаты:\n{result.output_dir}",
        )

    @Slot(str)
    def _m2_acceptance_error(self, message: str) -> None:
        self.chat_history.append(f"<b>M2 ACCEPTANCE ERROR:</b> {self._html(message)}")
        QMessageBox.critical(self, "M2 inference attention acceptance", message)

    @Slot()
    def _m2_acceptance_worker_finished(self) -> None:
        self._m2_acceptance_worker = None
        self.m2_acceptance_button.setEnabled(True)
        self.acceptance_button.setEnabled(True)
        self.m1_adversarial_button.setEnabled(True)
        self.m1_inversion_button.setEnabled(True)
        self.m1_ellipsis_button.setEnabled(True)
        self.m1_typo_button.setEnabled(True)
        self.document_acceptance_button.setEnabled(True)
        self.hidden_valency_button.setEnabled(True)
        self.send_button.setEnabled(True)
        self._refresh_status()

    def _run_hidden_valency_diagnostic(self) -> None:
        if self._cognitive_run_active():
            self.statusBar().showMessage("Другой cognitive run ещё выполняется", 2500)
            return
        if self._llm_operation_worker is not None:
            self.statusBar().showMessage("Дождитесь завершения операции LLM", 2500)
            return
        if self.services.llm is None or not self.services.llm.is_running:
            QMessageBox.warning(self, "Hidden-valency preflight", "Сначала запустите локальную LLM.")
            return

        self.send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.acceptance_button.setEnabled(False)
        self.m1_adversarial_button.setEnabled(False)
        self.m1_inversion_button.setEnabled(False)
        self.m1_ellipsis_button.setEnabled(False)
        self.m1_typo_button.setEnabled(False)
        self.document_acceptance_button.setEnabled(False)
        self.hidden_valency_button.setEnabled(False)
        self.m2_acceptance_button.setEnabled(False)
        self.action_llm.setEnabled(False)
        self.action_ignition.setEnabled(False)
        self.action_tick.setEnabled(False)
        self.action_save.setEnabled(False)
        self.chat_history.append(
            "<b>Hidden valency:</b> запускаю capability preflight — "
            "6 cases × 2 порядка labels, без записи в AH."
        )
        self.statusBar().showMessage("Hidden-valency preflight: 12 LLM-вызовов — выполняется")

        worker = FunctionWorker(lambda: run_hidden_valency_diagnostic(self.services))
        self._hidden_valency_worker = worker
        worker.signals.result.connect(self._hidden_valency_finished)
        worker.signals.error.connect(self._hidden_valency_error)
        worker.signals.finished.connect(self._hidden_valency_worker_finished)
        self.thread_pool.start(worker)

    @Slot(object)
    def _hidden_valency_finished(self, result) -> None:
        self.chat_history.append(
            f"<b>Hidden valency:</b> semantic OK {result.semantic_ok}/{result.cases}; "
            f"ORDER_BIAS {result.order_bias}; MALFORMED {result.malformed}; "
            f"first-choice {result.first_choice_calls}/{result.calls}; "
            f"AH unchanged={result.ah_unchanged}. "
            f"Bundle: {self._html(str(result.archive_path))}"
        )
        self.statusBar().showMessage(
            f"Hidden-valency preflight: OK {result.semantic_ok}/{result.cases}; "
            f"ORDER_BIAS {result.order_bias}; first-choice {result.first_choice_calls}/{result.calls}",
            10000,
        )
        QMessageBox.information(
            self,
            "Hidden-valency preflight",
            f"Диагностика завершена.\n\n"
            f"SEMANTIC_OK: {result.semantic_ok}/{result.cases}\n"
            f"ORDER_BIAS: {result.order_bias}\n"
            f"SEMANTIC_WRONG: {result.semantic_wrong}\n"
            f"INCONSISTENT: {result.inconsistent}\n"
            f"MALFORMED: {result.malformed}\n"
            f"Exact protocol: {result.exact_protocol_calls}/{result.calls}\n"
            f"Recovered </think>: {result.wrapper_recovered_calls}/{result.calls}\n"
            f"First-choice: {result.first_choice_calls}/{result.calls}\n"
            f"AH unchanged: {result.ah_unchanged}\n\n"
            f"Архив для анализа:\n{result.archive_path}",
        )

    @Slot(str)
    def _hidden_valency_error(self, message: str) -> None:
        self.chat_history.append(f"<b>HIDDEN VALENCY ERROR:</b> {self._html(message)}")
        QMessageBox.critical(self, "Hidden-valency preflight", message)

    @Slot()
    def _hidden_valency_worker_finished(self) -> None:
        self._hidden_valency_worker = None
        self.send_button.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.acceptance_button.setEnabled(True)
        self.m1_adversarial_button.setEnabled(True)
        self.m1_inversion_button.setEnabled(True)
        self.m1_ellipsis_button.setEnabled(True)
        self.m1_typo_button.setEnabled(True)
        self.document_acceptance_button.setEnabled(True)
        self.hidden_valency_button.setEnabled(True)
        self.m2_acceptance_button.setEnabled(True)
        self.action_llm.setEnabled(True)
        self.action_ignition.setEnabled(True)
        self.action_tick.setEnabled(True)
        self.action_save.setEnabled(True)
        self.chat_input.setFocus()
        self.llm_panel.refresh_status()
        self._refresh_status()

    def _suspend_acceptance_status_polling(self) -> None:
        if self._acceptance_status_suspended:
            return
        self._acceptance_status_suspended = True
        # Broad acceptance runs mutate a growing AH for many turns. Rebuilding the
        # whole visual graph at gui.refresh_hz adds no diagnostic value during the
        # run and competes with the worker for the shared runtime snapshot lock.
        # Pause visualization only; Ignition and the cognitive runtime keep running.
        self.status_timer.stop()
        self.canvas.set_live_updates_enabled(False)

    def _resume_acceptance_status_polling(self) -> None:
        if not self._acceptance_status_suspended:
            return
        self._acceptance_status_suspended = False
        # Re-enable visualization after the worker is done. The canvas performs one
        # immediate fresh snapshot before its periodic timer resumes.
        self.canvas.set_live_updates_enabled(True)
        self.llm_panel.refresh_status()
        self.status_timer.start(300)

    @Slot()
    def _chat_worker_finished(self) -> None:
        self._chat_worker = None
        self.send_button.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.chat_input.setFocus()
        self.llm_panel.finish_turn()
        self._refresh_status()

    def _turn_finished(self, result) -> None:
        self._last_turn = result
        self._turn_sequence += 1
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
            self.diagnostics_panel.record_tick(tick)
        trace_payload = []
        proof_builder = ProofSnapshotBuilder(self.services.core)
        for i, q in enumerate(result.queries, 1):
            if q.outcome is None:
                # Preserve the current provenance contract inside the audited GUI:
                # an epistemic target that could not be compiled is still a visible
                # logical outcome. Never let the UI collapse it into "no chains".
                proof = proof_builder.build_unresolved(
                    chain_id=f"live:turn:{self._turn_sequence}:query:{i}",
                    source="LIVE",
                    title=f"Turn {self._turn_sequence} · Query {i}",
                    diagnostics=q.diagnostics,
                )
                self.inference_explorer.add_chain(proof, select=False)
                self.metrics_panel.add_m2_chain(proof, select=False)
                trace_payload.append(
                    {
                        "query": i,
                        "status": "UNRESOLVED",
                        "stop_reason": "GOAL_NOT_COMPILED",
                        "diagnostics": q.diagnostics,
                    }
                )
                continue
            proof = proof_builder.build(
                q.outcome,
                chain_id=f"live:turn:{self._turn_sequence}:query:{i}",
                source="LIVE",
                title=f"Turn {self._turn_sequence} · Query {i}",
            )
            self.inference_explorer.add_chain(proof, select=False)
            self.metrics_panel.add_m2_chain(proof, select=False)
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
        try:
            formalization = FormalizationTraceBuilder(
                self.services.core,
                self.services.ignition,
                runtime_lock=self.services.operation_lock,
            ).build(
                result.integration,
                trace_id=f"live:turn:{self._turn_sequence}",
                source="LIVE",
                title=f"Turn {self._turn_sequence}",
                source_text=result.user_text,
                diagnostics=tuple(str(item) for item in result.perception.diagnostics),
            )
            self.metrics_panel.add_m1_trace(formalization, select=False)
        except Exception:
            # The committed turn stays authoritative; visualization is best-effort.
            pass
        self.trace_view.setPlainText(json.dumps(trace_payload, ensure_ascii=False, indent=2))
        self.llm_panel.show_agent_context(result.agent_context, result.agent_context_diagnostic)
        self.canvas.refresh()
        # Do not wait for the 1 s status poll to expose the just-finished parser
        # and agent diagnostics in the LLM tabs.
        self.llm_panel.refresh_status()

    def _show_inference_explorer(self) -> None:
        self.inference_dock.show()
        self.inference_dock.raise_()

    @Slot(object)
    def _show_proof_on_main_canvas(self, chain) -> None:
        if chain.source == "M2":
            if not self.canvas_browser.show_sandbox():
                QMessageBox.information(
                    self,
                    "Логический вывод",
                    "Для этой M2-цепочки полный sandbox canvas уже недоступен. "
                    "Proof-canvas и frozen семантика цепочки остаются доступны в виджете вывода.",
                )
                return
            canvas = self.canvas_browser.sandbox_canvas
            assert canvas is not None
        else:
            self.canvas_browser.show_live()
            canvas = self.canvas

        self.canvas_browser.clear_proof_highlights()
        node_hits, link_hits = canvas.set_proof_highlight(chain.node_uids, chain.edge_uids)
        if node_hits == 0:
            QMessageBox.information(
                self,
                "Логический вывод",
                "UID выбранной цепочки отсутствуют в соответствующем canvas snapshot. "
                "Семантический proof и UID trace всё равно доступны в виджете «Логический вывод».",
            )
            return
        self.statusBar().showMessage(
            f"Proof overlay [{chain.source}]: {node_hits}/{len(chain.node_uids)} узлов, "
            f"{link_hits}/{len(chain.edge_uids)} canonical links",
            6000,
        )

    def _select_sandbox_node(self, uid: str) -> None:
        canvas = self.canvas_browser.sandbox_canvas
        snapshot = None if canvas is None else canvas.current_snapshot
        if snapshot is None or not uid:
            self.node_inspector.set_raw_payload(
                {"canvas": "M2 SANDBOX", "status": "node not selected"}
            )
            return
        node = next((item for item in snapshot.nodes if item.uid == uid), None)
        if node is None:
            self.node_inspector.set_raw_payload(
                {"canvas": "M2 SANDBOX", "uid": uid, "status": "not found"}
            )
            return
        outgoing = [link for link in snapshot.links if link.source_uid == uid]
        incoming = [link for link in snapshot.links if link.target_uid == uid]
        self.node_inspector.set_raw_payload(
            {
                "canvas": "M2 SANDBOX (read-only frozen snapshot)",
                "node": asdict(node),
                "outgoing_links": [asdict(link) for link in outgoing[:100]],
                "incoming_links": [asdict(link) for link in incoming[:100]],
            }
        )

    def _select_sandbox_edge(self, key: str) -> None:
        canvas = self.canvas_browser.sandbox_canvas
        if canvas is None:
            return
        edge = canvas.edge_descriptor(key)
        if edge is None:
            self.node_inspector.set_raw_payload(
                {"canvas": "M2 SANDBOX", "status": "edge not selected"}
            )
            return
        self.node_inspector.set_raw_payload(
            {
                "canvas": "M2 SANDBOX (read-only frozen snapshot)",
                "edge": asdict(edge),
            }
        )

    def _turn_error(self, message: str) -> None:
        self.chat_history.append(f"<b>ERROR:</b> {self._html(message)}")
        self.llm_panel.refresh_status()
        QMessageBox.critical(self, "Turn", message)

    @staticmethod
    def _html(text: str) -> str:
        import html
        return html.escape(text).replace("\n", "<br>")

    @Slot(float, float, float, float)
    def _tune_ignition_decay_live(
        self,
        alpha: float,
        midpoint_ticks: float,
        reactivation_min_input: float,
        resolved_symbol_seed: float,
    ) -> None:
        try:
            self.services.tune_decay(
                alpha=alpha,
                midpoint_ticks=midpoint_ticks,
                reactivation_min_input=reactivation_min_input,
                resolved_symbol_seed=resolved_symbol_seed,
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Ignition tuning error: {exc}", 4000)

    @Slot(float, float, float, float)
    def _commit_ignition_decay_tuning(
        self,
        alpha: float,
        midpoint_ticks: float,
        reactivation_min_input: float,
        resolved_symbol_seed: float,
    ) -> None:
        # Runtime was already changed continuously while dragging. Mirror the
        # settled values into the generic config editor; explicit Save persists.
        self.config_editor.set_external_values(
            {
                "ignition.decay.alpha": round(float(alpha), 4),
                "ignition.decay.midpoint_ticks": round(float(midpoint_ticks), 4),
                "ignition.decay.reactivation_min_input": round(float(reactivation_min_input), 4),
                "ignition.seeds.resolved_symbol": round(float(resolved_symbol_seed), 4),
            },
            save=False,
        )
        self.statusBar().showMessage(
            "Ignition sliders применены live; для сохранения нажмите «Сохранить / применить» в конфиге",
            4500,
        )

    @Slot(bool, float, float)
    def _tune_ignition_mechanism_live(self, enabled: bool, pulse: float, threshold: float) -> None:
        try:
            self.services.tune_ignition_mechanism(pacemaker_enabled=enabled, pacemaker_pulse=pulse, workspace_threshold=threshold)
        except Exception as exc:
            self.statusBar().showMessage(f"Ignition mechanism tuning error: {exc}", 4000)

    @Slot(bool, float, float)
    def _commit_ignition_mechanism_tuning(self, enabled: bool, pulse: float, threshold: float) -> None:
        self.config_editor.set_external_values({
            "ignition.pacemaker.enabled": bool(enabled),
            "ignition.seeds.pacemaker": round(float(pulse), 4),
            "workspace.threshold": round(float(threshold), 4),
        }, save=False)
        self.statusBar().showMessage("Pacemaker/Workspace параметры применены live", 3000)

    @Slot(str, str, bool)
    def _import_corpus_from_gui(self, path: str, domain: str, cold_save: bool) -> None:
        if not path:
            QMessageBox.information(self, "Импорт", "Укажите путь к JSON/.ahm/.prj"); return
        try:
            from ah.model import Domain
            result = self.services.import_corpus(path, domain=Domain(domain), save=True, cold_save=cold_save)
        except Exception as exc:
            QMessageBox.critical(self, "Импорт структуры", f"{type(exc).__name__}: {exc}"); return
        self.canvas_browser.live_canvas.refresh(); self._refresh_status(force=True)
        QMessageBox.information(self, "Импорт структуры", json.dumps(result.as_dict(), ensure_ascii=False, indent=2))

    @Slot(str, bool, bool, bool)
    def _import_raw_text_from_gui(self, text: str, parse_semantics: bool, cold_save: bool, strict: bool) -> None:
        if not text.strip():
            QMessageBox.information(self, "Импорт", "Введите текст"); return
        try:
            result = self.services.import_raw_text(text, save=True, parse_user_semantics=parse_semantics, cold_save=cold_save, strict=strict)
        except Exception as exc:
            QMessageBox.critical(self, "Импорт текста", f"{type(exc).__name__}: {exc}"); return
        self.canvas_browser.live_canvas.refresh(); self._refresh_status(force=True)
        QMessageBox.information(self, "Импорт текста", json.dumps(result.as_dict(), ensure_ascii=False, indent=2))

    @Slot(str, bool)
    def _import_memory_from_gui(self, path: str, cold_restore: bool) -> None:
        if not path:
            QMessageBox.information(self, "Импорт", "Укажите persistence JSON"); return
        try:
            result = self.services.import_memory(path, save=True, cold_restore=cold_restore)
        except Exception as exc:
            QMessageBox.critical(self, "Импорт памяти", f"{type(exc).__name__}: {exc}"); return
        self.canvas_browser.live_canvas.refresh(); self._refresh_status(force=True)
        QMessageBox.information(self, "Импорт памяти", json.dumps(result.as_dict(), ensure_ascii=False, indent=2))

    def _refresh_manual_seed_button(self) -> None:
        amount = float(self.services.config.ignition.seeds.reactivated_fact)
        self.manual_seed_button.setText(f"Импульс выбранному узлу  +{amount:.2f} x")

    @Slot()
    def _seed_selected_node(self) -> None:
        uid = self._selected_uid
        if not uid:
            QMessageBox.information(self, "Тест возбуждения", "Сначала выберите узел на canvas.")
            return
        if not self.services.core.store.has_uid(uid):
            QMessageBox.warning(self, "Тест возбуждения", f"Узел больше не существует: {uid}")
            return

        amount = float(self.services.config.ignition.seeds.reactivated_fact)
        tick = None
        try:
            with self.services.operation_lock:
                ref = self.services.core.ref(uid)
                self.services.ignition.seed(ref, amount)
                if not self.services.clock.running:
                    tick = self.services.ignition.tick()
        except ValueError as exc:
            QMessageBox.information(self, "Тест возбуждения", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Тест возбуждения", f"{type(exc).__name__}: {exc}")
            return

        if tick is not None:
            self.canvas.push_tick(tick)
            self.diagnostics_panel.record_tick(tick)
        else:
            # Continuous clock consumes the queued impulse on its next tick. Keep
            # the graph live; no synthetic immediate x mutation is performed here.
            self.canvas.refresh()
        self._refresh_inspector()
        self.statusBar().showMessage(
            f"Тестовый импульс +{amount:.2f} → {uid}"
            + ("; выполнен один tick" if tick is not None else "; будет принят следующим tick"),
            3500,
        )

    @Slot(bool)
    def _toggle_full_canvas(self, enabled: bool) -> None:
        """Give the central VisPy canvas the whole client area without losing docks."""
        enabled = bool(enabled)
        if enabled == self._full_canvas_mode:
            return
        self._full_canvas_mode = enabled
        docks = tuple(self.findChildren(QDockWidget))
        if enabled:
            self._dock_visibility_before_full_canvas = {dock: dock.isVisible() for dock in docks}
            for dock in docks:
                dock.hide()
            self.statusBar().showMessage("Полный canvas — F11 для возврата панелей", 2500)
        else:
            previous = self._dock_visibility_before_full_canvas
            for dock in docks:
                if previous.get(dock, True):
                    dock.show()
            self._dock_visibility_before_full_canvas = {}
        self.canvas_browser.active_canvas.refresh()

    # ---------- config ----------
    def _config_saved(self, new_config: AppConfig, changed_paths: tuple[str, ...]) -> None:
        modes = {ConfigDocument.apply_mode(path) for path in changed_paths}
        try:
            # apply_config only swaps hot-safe policy holders. Persistence/identity
            # require process/runtime restart and are intentionally left untouched.
            self.services.apply_config(new_config)
            self.canvas_browser.set_config(new_config)
            if hasattr(self, "ignition_tuning"):
                self.ignition_tuning.set_parameters(
                    new_config.ignition.decay,
                    new_config.ignition.seeds.resolved_symbol,
                    new_config.ignition.tick_interval_seconds,
                )
                self.ignition_tuning.set_mechanism(
                    pacemaker_enabled=new_config.ignition.pacemaker.enabled,
                    pacemaker_pulse=new_config.ignition.seeds.pacemaker,
                    workspace_threshold=new_config.workspace.threshold,
                )
            if hasattr(self, "manual_seed_button"):
                self._refresh_manual_seed_button()
            self.llm_panel.reload_prompts()
            self.acceptance_button.setToolTip(
                "Cases: " + str(new_config.paths.data_dir / "acceptance_cases.txt")
                + "\nOracle: " + str(new_config.paths.data_dir / "acceptance_oracle.json")
            )
            self.m1_adversarial_button.setToolTip(
                "Expanded breaker-cases: typo/noise, syntactic inversion, ellipsis и mixed.\n"
                "Cases: " + str(new_config.paths.data_dir / "acceptance_cases_m1_adversarial.txt")
                + "\nOracle: " + str(new_config.paths.data_dir / "acceptance_oracle_m1_adversarial.json")
            )
            self.m1_inversion_button.setToolTip(
                "Expanded order-independent semantic-role corpus.\n"
                "Cases: " + str(new_config.paths.data_dir / "acceptance_inversion" / "cases.txt")
                + "\nOracle: " + str(new_config.paths.data_dir / "acceptance_inversion" / "oracle.json")
            )
            self.m1_ellipsis_button.setToolTip(
                "Discourse reconstruction / ellipsis corpus.\n"
                "Cases: " + str(new_config.paths.data_dir / "acceptance_ellipsis" / "cases.txt")
                + "\nOracle: " + str(new_config.paths.data_dir / "acceptance_ellipsis" / "oracle.json")
            )
            self.m1_typo_button.setToolTip(
                "Lexical Recovery: edits, roles, inversion, ellipsis, protected OOV and ambiguity.\n"
                "Cases: " + str(new_config.paths.data_dir / "acceptance_typo" / "cases.txt")
                + "\nOracle: " + str(new_config.paths.data_dir / "acceptance_typo" / "oracle.json")
            )
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
            self.link_manager.on_canvas_selection(self._selected_uid)
            self.node_inspector.set_node(self._selected_uid, snapshot=self._status_snapshot())
        else:
            self.canvas.set_selected_uid(None)
            self.node_inspector.clear_selection()
        if hasattr(self, "workspace_view"):
            self.workspace_view.set_selected_uid(self._selected_uid)
        if hasattr(self, "all_nodes_view"):
            self.all_nodes_view.set_selected_uid(self._selected_uid)

    def _select_edge(self, key: str) -> None:
        self._selected_edge_key = key or None
        if self._selected_edge_key is not None:
            self._selected_uid = None
            self.canvas.set_selected_edge_key(self._selected_edge_key)
            edge = self.canvas.edge_descriptor(self._selected_edge_key)
            self.node_inspector.set_edge(edge)
        else:
            self.canvas.set_selected_edge_key(None)
            self.node_inspector.clear_selection()

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

    def _refresh_inspector(self, snapshot=None) -> None:
        if self._selected_uid:
            self.node_inspector.set_node(self._selected_uid, snapshot=snapshot)
            return
        if self._selected_edge_key:
            self.node_inspector.set_edge(self.canvas.edge_descriptor(self._selected_edge_key), snapshot=snapshot)
            return
        self.node_inspector.clear_selection()

    def _refresh_llm_status_if_visible(self) -> None:
        if hasattr(self, "llm_dock") and self.llm_dock.isVisible():
            self.llm_panel.refresh_status()

    def _status_snapshot(self):
        # The canvas already builds the expensive GraphInspector snapshot at GUI
        # refresh cadence. Reuse it for docks instead of taking a second full
        # semantic/structural snapshot on the UI thread.
        snap = self.canvas.current_snapshot
        return snap if snap is not None else self.services.graph_inspector.snapshot()

    def _refresh_status(self, force: bool = False) -> None:
        llm_running = bool(self.services.llm and self.services.llm.is_running)
        clock = self.services.clock.stats()
        snap = self._status_snapshot()
        self.action_llm.setText("Остановить LLM" if llm_running else "Запустить LLM")
        self.action_ignition.setText("Остановить Ignition" if clock.running else "Запустить Ignition")
        restart = []
        if self._llm_restart_required:
            restart.append("LLM restart")
        if self._runtime_restart_required:
            restart.append("runtime restart")
        visible_node_count = len(self.canvas.mapper.visible_nodes(snap, self.canvas.settings))
        hidden_symbol_count = len(snap.nodes) - visible_node_count

        if (
            hasattr(self, "workspace_view")
            and hasattr(self, "workspace_dock")
            and self.workspace_dock.isVisible()
        ):
            self.workspace_view.refresh(snap, self.services.config.workspace.threshold, force=force)
            self.workspace_view.set_selected_uid(self._selected_uid)

        if (
            hasattr(self, "all_nodes_view")
            and hasattr(self, "all_nodes_dock")
            and self.all_nodes_dock.isVisible()
        ):
            # ACTIVE semantics are structural and usually unchanged between ticks.
            # The viewer asks only for missing/new UIDs, avoiding an O(all nodes)
            # semantic projection on every 1 Hz UI poll.
            missing = (
                [node.uid for node in snap.nodes]
                if force
                else self.all_nodes_view.missing_semantic_uids(snap)
            )
            semantics = self.services.graph_inspector.active_semantics(missing) if missing else {}
            self.all_nodes_view.refresh(snap, semantics, force=force)
            self.all_nodes_view.set_selected_uid(self._selected_uid)

        if hasattr(self, "diagnostics_panel") and self.runtime_dock.isVisible():
            self.diagnostics_panel.refresh()

        if hasattr(self, "runtime_dock") and self.runtime_dock.isVisible():
            self.runtime_label.setText(
                f"tick={snap.tick} | nodes={visible_node_count} | links={len(snap.links)} | "
                f"workspace={len(snap.workspace_uids)} | LLM={'ON' if llm_running else 'OFF'} | "
                f"Ignition={'ON' if clock.running else 'OFF'}"
                + (f" | hidden lexical S={hidden_symbol_count}" if hidden_symbol_count else "")
                + (" | " + ", ".join(restart) if restart else "")
            )
        if clock.last_error:
            self.statusBar().showMessage(f"Ignition error: {clock.last_error}")
        if not hasattr(self, "inspector_dock") or self.inspector_dock.isVisible():
            self._refresh_inspector(snapshot=snap)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        try:
            self.services.stop(save=True)
        finally:
            super().closeEvent(event)
