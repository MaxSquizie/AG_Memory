from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ah.diagnostics import (
    BoundedHistory,
    FormalizationTraceSnapshot,
    M1Report,
    M2QuestionObservation,
    M2ScoreReport,
    M3Report,
    ProofChainSnapshot,
    score_m2_explainability,
)

from .inference_explorer import ProofCanvasView
from .snapshot_canvas import SnapshotCanvasView


class MetricCard(QFrame):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.title = QLabel(title)
        self.title.setObjectName("metricCardTitle")
        self.value = QLabel("NOT MEASURED")
        self.value.setObjectName("metricCardValue")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setWordWrap(True)
        self.subtitle.setObjectName("metricCardSubtitle")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)

    def set_value(self, value: str, subtitle: str = "") -> None:
        self.value.setText(value)
        self.subtitle.setText(subtitle)


class MetricsPanelWidget(QWidget):
    """Separate operator workspace for M1–M3 and their frozen evidence."""

    m1_score_requested = Signal(str)
    m2_run_requested = Signal()
    m3_run_requested = Signal()

    _M1_RUN_DIRS = {
        "Основной": "acceptance_runs",
        "Adversarial": "acceptance_runs_m1_adversarial",
        "Inversion": "acceptance_runs_m1_inversion",
        "Ellipsis": "acceptance_runs_m1_ellipsis",
        "Typo / noise": "acceptance_runs_m1_typo",
        "Quantifiers": "acceptance_runs_m1_quantifiers",
        "Temporal modes": "acceptance_runs_m1_temporal_modes",
    }

    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.m1_history: BoundedHistory[FormalizationTraceSnapshot] = BoundedHistory(20)
        self.m2_history: BoundedHistory[ProofChainSnapshot] = BoundedHistory(20)
        self._m1_by_id: dict[str, FormalizationTraceSnapshot] = {}
        self._m2_by_id: dict[str, ProofChainSnapshot] = {}
        self._m2_cases: list[Any] = []
        self._m2_table_updating = False
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        intro = QLabel(
            "Диагностика метрик отделена от обычного мониторинга. M1 и M2 хранят "
            "только последние 20 замороженных снимков; эти данные не записываются в AH."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        cards = QGridLayout()
        self.m1_card = MetricCard("M1 · Actant Role F1", "Role-weighted F1")
        self.m2_card = MetricCard("M2 · ExplainScore", "ровно N=20, d_max=6")
        self.m3_card = MetricCard("M3 · GC lifecycle", "200 orphan / 100 live")
        for column, card in enumerate((self.m1_card, self.m2_card, self.m3_card)):
            cards.addWidget(card, 0, column)
        root.addLayout(cards)

        self.metric_tabs = QTabWidget()
        self.metric_tabs.addTab(self._build_m1_tab(), "M1 · Formalization")
        self.metric_tabs.addTab(self._build_m2_tab(), "M2 · UID tracing")
        self.metric_tabs.addTab(self._build_m3_tab(), "M3 · GC")
        root.addWidget(self.metric_tabs, 1)

        self.detail = QLabel("Выберите метрику и запустите расчёт.")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.detail)

    def _build_m1_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.m1_suite = QComboBox()
        self.m1_suite.addItems(tuple(self._M1_RUN_DIRS))
        row.addWidget(self.m1_suite)
        latest = QPushButton("Последний run")
        latest.clicked.connect(self._set_latest_m1)
        row.addWidget(latest)
        self.m1_path = QLineEdit()
        self.m1_path.setPlaceholderText("Папка run: oracle_used.json + turn_*.json")
        row.addWidget(self.m1_path, 1)
        browse = QPushButton("Выбрать…")
        browse.clicked.connect(self._choose_m1_dir)
        row.addWidget(browse)
        score = QPushButton("Посчитать M1")
        score.clicked.connect(lambda: self.m1_score_requested.emit(self.m1_path.text().strip()))
        row.addWidget(score)
        layout.addLayout(row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.m1_trace_list = QListWidget()
        self.m1_trace_list.setMinimumWidth(250)
        splitter.addWidget(self.m1_trace_list)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.m1_trace_label = QLabel("Подграф не выбран")
        self.m1_trace_label.setWordWrap(True)
        head.addWidget(self.m1_trace_label, 1)
        fit = QPushButton("Вписать canvas")
        fit.clicked.connect(lambda: self.m1_canvas.fit_snapshot())
        head.addWidget(fit)
        right_layout.addLayout(head)
        self.m1_view_tabs = QTabWidget()
        self.m1_canvas = SnapshotCanvasView()
        self.m1_view_tabs.addTab(self.m1_canvas, "Подграф")
        self.m1_prompt = QPlainTextEdit()
        self.m1_prompt.setReadOnly(True)
        self.m1_view_tabs.addTab(self.m1_prompt, "Исходный промпт")
        self.m1_nodes = QTableWidget(0, 4)
        self.m1_nodes.setHorizontalHeaderLabels(("UID", "Тип", "Домен", "Семантика"))
        self.m1_nodes.horizontalHeader().setStretchLastSection(True)
        self.m1_nodes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.m1_view_tabs.addTab(self.m1_nodes, "Узлы")
        self.m1_edges = QTableWidget(0, 5)
        self.m1_edges.setHorizontalHeaderLabels(("От", "К", "Связь", "Вид", "UID"))
        self.m1_edges.horizontalHeader().setStretchLastSection(True)
        self.m1_edges.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.m1_view_tabs.addTab(self.m1_edges, "Связи")
        right_layout.addWidget(self.m1_view_tabs, 1)
        self.m1_details = QLabel("История: 0/20")
        self.m1_details.setWordWrap(True)
        right_layout.addWidget(self.m1_details)
        splitter.addWidget(right)
        splitter.setSizes((270, 900))
        layout.addWidget(splitter, 1)
        self.m1_trace_list.currentItemChanged.connect(self._show_m1_trace)
        return body

    def _build_m2_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)
        self.m2_tabs = QTabWidget()

        history = QWidget()
        history_layout = QVBoxLayout(history)
        run_row = QHBoxLayout()
        run = QPushButton("Запустить M2 acceptance")
        run.clicked.connect(self.m2_run_requested.emit)
        run_row.addWidget(run)
        run_row.addStretch(1)
        self.m2_history_label = QLabel("История: 0/20")
        run_row.addWidget(self.m2_history_label)
        history_layout.addLayout(run_row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.m2_trace_list = QListWidget()
        self.m2_trace_list.setMinimumWidth(270)
        splitter.addWidget(self.m2_trace_list)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self.m2_trace_label = QLabel("Proof path не выбран")
        self.m2_trace_label.setWordWrap(True)
        head.addWidget(self.m2_trace_label, 1)
        fit = QPushButton("Вписать canvas")
        head.addWidget(fit)
        right_layout.addLayout(head)
        self.m2_canvas = ProofCanvasView()
        fit.clicked.connect(self.m2_canvas.fit_proof)
        right_layout.addWidget(self.m2_canvas, 2)
        details = QTabWidget()
        self.m2_semantic = QPlainTextEdit()
        self.m2_semantic.setReadOnly(True)
        details.addTab(self.m2_semantic, "Семантика")
        self.m2_uid = QPlainTextEdit()
        self.m2_uid.setReadOnly(True)
        details.addTab(self.m2_uid, "UID trace")
        self.m2_cognitive = QPlainTextEdit()
        self.m2_cognitive.setReadOnly(True)
        details.addTab(self.m2_cognitive, "Возбуждение")
        right_layout.addWidget(details, 1)
        splitter.addWidget(right)
        splitter.setSizes((290, 900))
        history_layout.addWidget(splitter, 1)
        self.m2_tabs.addTab(history, "Последние proof paths")

        score_tab = QWidget()
        score_layout = QVBoxLayout(score_tab)
        score_layout.addWidget(QLabel(
            "Acceptance содержит 40 cases. Для опубликованной формулы ExplainScore "
            "выберите ровно 20 наблюдений."
        ))
        self.m2_table = QTableWidget(0, 6)
        self.m2_table.setHorizontalHeaderLabels(("✓", "Scenario", "Relation", "Depth", "Correct", "Trace"))
        self.m2_table.horizontalHeader().setStretchLastSection(True)
        self.m2_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.m2_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.m2_table.itemChanged.connect(self._update_m2_count)
        score_layout.addWidget(self.m2_table, 1)
        buttons = QHBoxLayout()
        self.m2_count = QLabel("Выбрано: 0/20")
        buttons.addWidget(self.m2_count)
        buttons.addStretch(1)
        clear = QPushButton("Снять выбор")
        clear.clicked.connect(self._clear_m2_selection)
        buttons.addWidget(clear)
        self.m2_score_button = QPushButton("Посчитать ExplainScore")
        self.m2_score_button.setEnabled(False)
        self.m2_score_button.clicked.connect(self._score_selected_m2)
        buttons.addWidget(self.m2_score_button)
        score_layout.addLayout(buttons)
        self.m2_tabs.addTab(score_tab, "ExplainScore · N=20")
        layout.addWidget(self.m2_tabs, 1)
        self.m2_trace_list.currentItemChanged.connect(self._show_m2_trace)
        return body

    def _build_m3_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)
        info = QLabel(
            "Committee-shape harness: 200 изолированных orphan nodes, 100 live nodes, "
            "не более 50 ticks. Проверяются удаление orphan и сохранность live component."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        run = QPushButton("Запустить M3 GC acceptance")
        run.clicked.connect(self.m3_run_requested.emit)
        layout.addWidget(run)
        self.m3_details = QLabel("Результат ещё не получен.")
        self.m3_details.setWordWrap(True)
        layout.addWidget(self.m3_details)
        layout.addStretch(1)
        return body

    def _choose_m1_dir(self) -> None:
        if path := QFileDialog.getExistingDirectory(self, "Выберите acceptance run"):
            self.m1_path.setText(path)
            self.m1_score_requested.emit(path)

    def _set_latest_m1(self) -> None:
        dirname = self._M1_RUN_DIRS[self.m1_suite.currentText()]
        root = Path(self.services.config.paths.data_dir) / dirname
        candidate: Path | None = None
        latest_file = root / "latest.txt"
        if latest_file.is_file():
            raw = latest_file.read_text(encoding="utf-8-sig").strip()
            if raw and Path(raw).is_dir():
                candidate = Path(raw)
        if candidate is None and root.is_dir():
            runs = [item for item in root.iterdir() if item.is_dir() and (item / "oracle_used.json").is_file()]
            if runs:
                candidate = max(runs, key=lambda item: item.stat().st_mtime)
        if candidate is None:
            QMessageBox.information(self, "M1", f"В {root} нет готового acceptance run.")
            return
        self.m1_path.setText(str(candidate))
        self.m1_score_requested.emit(str(candidate))

    def add_m1_trace(self, trace: FormalizationTraceSnapshot, *, select: bool = False) -> None:
        self.m1_history.append(trace)
        self._m1_by_id = {item.trace_id: item for item in self.m1_history.items}
        self.m1_trace_list.clear()
        for item in reversed(self.m1_history.items):
            row = QListWidgetItem(f"{item.title} · {item.status}")
            row.setData(Qt.ItemDataRole.UserRole, item.trace_id)
            row.setToolTip(item.source_text)
            self.m1_trace_list.addItem(row)
        self.m1_details.setText(f"История: {len(self.m1_history)}/20")
        if select and self.m1_trace_list.count():
            self.m1_trace_list.setCurrentRow(0)

    def add_m1_traces(self, traces, *, select_last: bool = True) -> None:
        for trace in traces:
            self.add_m1_trace(trace, select=False)
        if select_last and self.m1_trace_list.count():
            self.m1_trace_list.setCurrentRow(0)

    def _show_m1_trace(self, current, _previous) -> None:
        trace = None if current is None else self._m1_by_id.get(current.data(Qt.ItemDataRole.UserRole))
        self.m1_canvas.set_snapshot(None if trace is None else trace.graph)
        self.m1_prompt.setPlainText("" if trace is None else trace.source_text)
        self.m1_nodes.setRowCount(0)
        self.m1_edges.setRowCount(0)
        if trace is None:
            self.m1_trace_label.setText("Подграф не выбран")
            return
        self.m1_trace_label.setText(
            f"{trace.title} · {trace.source} · {trace.status} · "
            f"{len(trace.graph.nodes)} nodes"
        )
        self.m1_nodes.setRowCount(len(trace.graph.nodes))
        for row, node in enumerate(trace.graph.nodes):
            for column, value in enumerate((node.uid, node.kind, node.domain or "—", node.semantic)):
                self.m1_nodes.setItem(row, column, QTableWidgetItem(str(value)))
        edge_rows = [
            (edge.source_uid, edge.target_uid, edge.relation_id, edge.edge_kind, "—")
            for edge in trace.graph.structural_edges
        ] + [
            (edge.source_uid, edge.target_uid, edge.relation_id, "L", edge.uid)
            for edge in trace.graph.links
        ]
        self.m1_edges.setRowCount(len(edge_rows))
        for row, values in enumerate(edge_rows):
            for column, value in enumerate(values):
                self.m1_edges.setItem(row, column, QTableWidgetItem(str(value)))

    def add_m2_chain(self, chain: ProofChainSnapshot, *, select: bool = False) -> None:
        self.m2_history.append(chain)
        self._m2_by_id = {item.chain_id: item for item in self.m2_history.items}
        self.m2_trace_list.clear()
        for item in reversed(self.m2_history.items):
            row = QListWidgetItem(f"{item.title} · {item.status} · d={item.logical_depth}")
            row.setData(Qt.ItemDataRole.UserRole, item.chain_id)
            self.m2_trace_list.addItem(row)
        self.m2_history_label.setText(f"История: {len(self.m2_history)}/20")
        if select and self.m2_trace_list.count():
            self.m2_trace_list.setCurrentRow(0)

    def add_m2_chains(self, chains, *, select_last: bool = True) -> None:
        for chain in chains:
            self.add_m2_chain(chain, select=False)
        if select_last and self.m2_trace_list.count():
            self.m2_trace_list.setCurrentRow(0)

    def _show_m2_trace(self, current, _previous) -> None:
        chain = None if current is None else self._m2_by_id.get(current.data(Qt.ItemDataRole.UserRole))
        self.m2_canvas.set_chain(chain)
        if chain is None:
            self.m2_trace_label.setText("Proof path не выбран")
            self.m2_semantic.clear()
            self.m2_uid.clear()
            self.m2_cognitive.clear()
            return
        self.m2_trace_label.setText(
            f"{chain.title} · {chain.status}/{chain.stop_reason} · depth={chain.logical_depth}"
        )
        self.m2_semantic.setPlainText(chain.semantic_text())
        node_domains = {node.uid: node.domain or "—" for node in chain.nodes}
        self.m2_uid.setPlainText("\n".join(
            f"{index + 1:02d}. {uid} · domain={node_domains.get(uid, 'L/—')}"
            for index, uid in enumerate(chain.trace_uids)
        ))
        self.m2_cognitive.setPlainText("\n".join(chain.cognitive_events))

    def set_m1_report(self, report: M1Report) -> None:
        self.m1_card.set_value(
            f"{report.weighted_mean:.3f}",
            "PASS ≥ 0.600" if report.weighted_mean >= 0.6 else "BELOW 0.600",
        )
        rows = [
            f"{row.role}: F1={row.f1:.3f} (P={row.precision:.3f}, R={row.recall:.3f}, w={row.weight:g})"
            for row in report.roles
        ]
        self.m1_details.setText(
            f"История: {len(self.m1_history)}/20\n"
            f"weighted_sum={report.weighted_sum_as_stated:.3f}; "
            f"mandatory={report.mandatory_roles_present}\n" + "\n".join(rows)
        )
        self.detail.setText("M1 рассчитана diagnostics scorer; GUI формулу не дублирует.")

    def set_m2_acceptance_result(self, result) -> None:
        self._m2_cases = list(result.cases)
        proofs = [case.proof for case in self._m2_cases if case.proof is not None]
        self.add_m2_chains(proofs, select_last=bool(proofs))
        self._m2_table_updating = True
        self.m2_table.setRowCount(len(self._m2_cases))
        for row, case in enumerate(self._m2_cases):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.m2_table.setItem(row, 0, check)
            values = (
                case.scenario,
                case.relation,
                str(case.goal_depth),
                "PASS" if case.passed else "FAIL",
                "OK" if case.trace_uids else "MISSING",
            )
            for column, value in enumerate(values, start=1):
                self.m2_table.setItem(row, column, QTableWidgetItem(str(value)))
        self._m2_table_updating = False
        self._update_m2_count()
        self.m2_card.set_value(f"{result.passed}/{result.total}", f"acceptance; AH={result.ah_uids} UIDs")
        self.detail.setText(
            f"M2 acceptance: PASS {result.passed}/{result.total}, FAIL {result.failed}. "
            "Последние 20 proof paths сохранены в отдельном canvas."
        )

    def _clear_m2_selection(self) -> None:
        self._m2_table_updating = True
        for row in range(self.m2_table.rowCount()):
            if item := self.m2_table.item(row, 0):
                item.setCheckState(Qt.CheckState.Unchecked)
        self._m2_table_updating = False
        self._update_m2_count()

    def _update_m2_count(self, _item=None) -> None:
        if self._m2_table_updating:
            return
        count = sum(
            self.m2_table.item(row, 0) is not None
            and self.m2_table.item(row, 0).checkState() == Qt.CheckState.Checked
            for row in range(self.m2_table.rowCount())
        )
        self.m2_count.setText(f"Выбрано: {count}/20")
        self.m2_score_button.setEnabled(count == 20)

    def _score_selected_m2(self) -> None:
        selected = [
            case for row, case in enumerate(self._m2_cases)
            if self.m2_table.item(row, 0) is not None
            and self.m2_table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        if len(selected) != 20:
            QMessageBox.information(self, "M2 ExplainScore", f"Нужно ровно 20 cases; сейчас {len(selected)}.")
            return
        observations = [
            M2QuestionObservation(
                bool(case.passed),
                int(case.logical_depth),
                bool(case.proof and case.trace_uids)
                and (not case.proof.checks or all(check.passed for check in case.proof.checks)),
                str(case.scenario),
            )
            for case in selected
        ]
        try:
            report = score_m2_explainability(observations, d_max=6, expected_count=20)
        except Exception as exc:
            QMessageBox.critical(self, "M2 ExplainScore", f"{type(exc).__name__}: {exc}")
            return
        self.set_m2_score(report, selected)

    def set_m2_score(self, report: M2ScoreReport, selected_cases: list[Any]) -> None:
        self.m2_card.set_value(
            f"{report.explain_score:.3f}",
            f"N={report.question_count}, d_max={report.d_max}; all_correct={report.all_correct}",
        )
        labels = ", ".join(f"{case.scenario}/d{case.logical_depth}" for case in selected_cases)
        self.detail.setText(
            f"M2 ExplainScore={report.explain_score:.6f}; contributions="
            f"{', '.join(f'{value:.3f}' for value in report.contributions)}\n{labels}"
        )

    def set_m3_report(self, report: M3Report) -> None:
        status = "PASS" if report.passed else "FAIL"
        self.m3_card.set_value(
            status,
            f"orphans {report.orphan_nodes_before}→{report.orphan_nodes_after}; "
            f"live {report.live_nodes_before}→{report.live_nodes_after}",
        )
        self.m3_details.setText(
            f"{status}\n"
            f"ticks={report.ticks_budget}; gone_at={report.ticks_until_orphans_gone}\n"
            f"GC efficiency={report.gc_efficiency:.3f}; live preservation={report.live_preservation:.3f}\n"
            f"elapsed={report.elapsed_ms:.2f} ms"
        )
        self.detail.setText("M3 рассчитана существующим GC acceptance harness.")
