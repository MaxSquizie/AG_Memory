from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ah.diagnostics.inference_proof import ProofChainSnapshot


class ProofCanvasView(QGraphicsView):
    """Compact diagnostic canvas for exactly one frozen inference proof."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(24, 29, 38)))
        self._chain: ProofChainSnapshot | None = None

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def set_chain(self, chain: ProofChainSnapshot | None) -> None:
        self._chain = chain
        self._scene.clear()
        if chain is None or not chain.nodes:
            self._scene.addSimpleText("Выберите логическую цепочку")
            return

        node_by_uid = {node.uid: node for node in chain.nodes}
        ordered_uids: list[str] = []
        for uid in chain.trace_uids:
            if uid in node_by_uid and uid not in ordered_uids:
                ordered_uids.append(uid)
        for node in chain.nodes:
            if node.uid not in ordered_uids:
                ordered_uids.append(node.uid)

        width = 250.0
        gap = 115.0
        x0 = 30.0
        y0 = 55.0
        node_rects: dict[str, tuple[float, float, float, float]] = {}

        for index, uid in enumerate(ordered_uids):
            node = node_by_uid[uid]
            x = x0 + index * (width + gap)
            text = QGraphicsTextItem()
            text.setDefaultTextColor(QColor(235, 239, 246))
            text.setTextWidth(width - 24)
            text.setHtml(
                f"<b>{node.kind}:{node.uid}</b><br>"
                f"<span style='color:#c8d0dd'>{self._html(node.semantic)}</span>"
            )
            text.setPos(x + 12, y0 + 10)
            text_height = max(70.0, text.boundingRect().height() + 20)
            rect = QGraphicsRectItem(x, y0, width, text_height)
            rect.setPen(QPen(QColor(105, 187, 255), 2.0))
            rect.setBrush(QBrush(QColor(37, 48, 64)))
            self._scene.addItem(rect)
            self._scene.addItem(text)
            node_rects[uid] = (x, y0, width, text_height)

        for edge in chain.edges:
            source_rect = node_rects.get(edge.source_uid)
            target_rect = node_rects.get(edge.target_uid)
            if source_rect is None or target_rect is None:
                continue
            sx = source_rect[0] + source_rect[2]
            sy = source_rect[1] + source_rect[3] / 2
            tx = target_rect[0]
            ty = target_rect[1] + target_rect[3] / 2
            pen = QPen(QColor(241, 190, 74), 2.2)
            self._scene.addLine(sx, sy, tx, ty, pen)
            arrow = QPolygonF(
                [
                    QPointF(tx, ty),
                    QPointF(tx - 11, ty - 6),
                    QPointF(tx - 11, ty + 6),
                ]
            )
            arrow_item = QGraphicsPolygonItem(arrow)
            arrow_item.setPen(pen)
            arrow_item.setBrush(QBrush(QColor(241, 190, 74)))
            self._scene.addItem(arrow_item)
            label = QGraphicsSimpleTextItem(edge.relation)
            label.setBrush(QBrush(QColor(255, 215, 126)))
            label.setPos((sx + tx) / 2 - 22, min(sy, ty) - 26)
            self._scene.addItem(label)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-30, -30, 30, 30))
        self.fit_proof()

    def fit_proof(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-25, -25, 25, 25), Qt.AspectRatioMode.KeepAspectRatio)

    @staticmethod
    def _html(text: str) -> str:
        import html

        return html.escape(text).replace("\n", "<br>")


class InferenceExplorerWidget(QWidget):
    """Dockable operator widget for live, acceptance and M2 inference proofs."""

    overlay_requested = Signal(object)
    clear_overlay_requested = Signal()


    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chains: list[ProofChainSnapshot] = []
        self._by_id: dict[str, ProofChainSnapshot] = {}

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Источник:"))
        self.source_filter = QComboBox()
        self.source_filter.addItems(("Все", "LIVE", "ACCEPTANCE", "M2"))
        filters.addWidget(self.source_filter)
        filters.addWidget(QLabel("Статус:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(("Все", "PROVED", "DISPROVED", "UNKNOWN"))
        filters.addWidget(self.status_filter)
        filters.addStretch(1)
        self.summary_label = QLabel("Цепочек: 0")
        filters.addWidget(self.summary_label)
        root_layout.addLayout(filters)

        outer = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(outer, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.chain_list = QListWidget()
        self.chain_list.setMinimumWidth(330)
        left_layout.addWidget(self.chain_list, 1)
        outer.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self.selected_label = QLabel("Цепочка не выбрана")
        self.selected_label.setWordWrap(True)
        header.addWidget(self.selected_label, 1)
        self.overlay_button = QPushButton("Показать цепочку на canvas")
        self.clear_overlay_button = QPushButton("Убрать подсветку")
        self.fit_button = QPushButton("Вписать proof-canvas")
        header.addWidget(self.overlay_button)
        header.addWidget(self.clear_overlay_button)
        header.addWidget(self.fit_button)
        right_layout.addLayout(header)

        vertical = QSplitter(Qt.Orientation.Vertical)
        self.proof_canvas = ProofCanvasView()
        vertical.addWidget(self.proof_canvas)

        self.tabs = QTabWidget()
        self.semantic_view = QPlainTextEdit()
        self.semantic_view.setReadOnly(True)
        self.tabs.addTab(self.semantic_view, "Семантика / логика")

        self.goal_view = QPlainTextEdit()
        self.goal_view.setReadOnly(True)
        self.tabs.addTab(self.goal_view, "Цель / остановка")

        self.checks_table = QTableWidget(0, 3)
        self.checks_table.setHorizontalHeaderLabels(("Проверка", "Результат", "Детали"))
        self.checks_table.horizontalHeader().setStretchLastSection(True)
        self.checks_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.checks_table, "Проверки M2")

        self.uid_view = QPlainTextEdit()
        self.uid_view.setReadOnly(True)
        self.tabs.addTab(self.uid_view, "UID trace")
        vertical.addWidget(self.tabs)
        vertical.setSizes((520, 330))
        right_layout.addWidget(vertical, 1)
        outer.addWidget(right)
        outer.setSizes((370, 1080))

        self.source_filter.currentTextChanged.connect(self._rebuild_list)
        self.status_filter.currentTextChanged.connect(self._rebuild_list)
        self.chain_list.currentItemChanged.connect(self._selection_changed)
        self.overlay_button.clicked.connect(self._request_overlay)
        self.clear_overlay_button.clicked.connect(self.clear_overlay_requested.emit)
        self.fit_button.clicked.connect(self.proof_canvas.fit_proof)

    @property
    def chains(self) -> tuple[ProofChainSnapshot, ...]:
        return tuple(self._chains)

    def add_chain(self, chain: ProofChainSnapshot, *, select: bool = False) -> ProofChainSnapshot:
        base_id = chain.chain_id
        chain_id = base_id
        suffix = 2
        while chain_id in self._by_id:
            chain_id = f"{base_id}#{suffix}"
            suffix += 1
        if chain_id != chain.chain_id:
            chain = replace(chain, chain_id=chain_id)
        self._chains.append(chain)
        self._by_id[chain.chain_id] = chain
        self._rebuild_list(select_id=chain.chain_id if select else None)
        return chain

    def add_chains(self, chains, *, select_last: bool = False) -> None:
        added: ProofChainSnapshot | None = None
        for chain in chains:
            added = self.add_chain(chain, select=False)
        self._rebuild_list(select_id=added.chain_id if select_last and added is not None else None)

    def select_chain(self, chain_id: str) -> None:
        self._rebuild_list(select_id=chain_id)

    def _filtered(self) -> list[ProofChainSnapshot]:
        source = self.source_filter.currentText()
        status = self.status_filter.currentText()
        return [
            chain
            for chain in self._chains
            if (source == "Все" or chain.source == source)
            and (status == "Все" or chain.status == status)
        ]

    def _rebuild_list(self, *_args, select_id: str | None = None) -> None:
        current = select_id
        if current is None and self.chain_list.currentItem() is not None:
            current = self.chain_list.currentItem().data(Qt.ItemDataRole.UserRole)
        self.chain_list.clear()
        filtered = self._filtered()
        for chain in reversed(filtered):
            marker = "PASS" if chain.status in {"PROVED", "DISPROVED"} and chain.stop_reason == "GOAL_SATISFIED" else chain.status
            item = QListWidgetItem(
                f"[{chain.source}] {marker} · d={chain.logical_depth} · {chain.title}"
            )
            item.setData(Qt.ItemDataRole.UserRole, chain.chain_id)
            self.chain_list.addItem(item)
            if current == chain.chain_id:
                self.chain_list.setCurrentItem(item)
        self.summary_label.setText(f"Цепочек: {len(filtered)} / {len(self._chains)}")
        if self.chain_list.currentItem() is None and self.chain_list.count():
            self.chain_list.setCurrentRow(0)

    def _selection_changed(self, current, _previous) -> None:
        chain = self._chain_for_item(current)
        self.proof_canvas.set_chain(chain)
        if chain is None:
            self.selected_label.setText("Цепочка не выбрана")
            self.semantic_view.clear()
            self.goal_view.clear()
            self.uid_view.clear()
            self.checks_table.setRowCount(0)
            return

        self.selected_label.setText(
            f"{chain.title} | {chain.status}/{chain.stop_reason} | "
            f"depth={chain.logical_depth} | expanded={chain.expanded_states}"
        )
        self.semantic_view.setPlainText(chain.semantic_text())
        goal_resolved = (
            chain.stop_reason == "GOAL_SATISFIED"
            and chain.status in {"PROVED", "DISPROVED"}
        )
        self.goal_view.setPlainText(
            "Goal фиксируется до начала search.\n\n"
            f"G = {chain.goal_text}\n\n"
            f"Logical status = {chain.status}\n"
            f"Stop reason = {chain.stop_reason}\n"
            f"Satisfied/decided = {goal_resolved}\n"
            f"Logical depth used = {chain.logical_depth}\n"
            f"Expanded states = {chain.expanded_states}\n\n"
            "GOAL_SATISFIED означает, что semantic matcher цели стал истинным "
            "после конкретного rule application (или цель была явно опровергнута). "
            "Workspace/x задают доступность и приоритет, но не являются критерием истины."
        )

        semantic_by_uid = {node.uid: node.semantic for node in chain.nodes}
        edge_by_uid = {edge.uid: edge.semantic for edge in chain.edges if edge.uid}
        uid_lines = []
        for index, uid in enumerate(chain.trace_uids, 1):
            semantic = semantic_by_uid.get(uid, edge_by_uid.get(uid, ""))
            uid_lines.append(f"{index:02d}. {uid}\n    {semantic}")
        self.uid_view.setPlainText("\n".join(uid_lines))

        self.checks_table.setRowCount(len(chain.checks))
        for row, check in enumerate(chain.checks):
            self.checks_table.setItem(row, 0, QTableWidgetItem(check.name))
            self.checks_table.setItem(row, 1, QTableWidgetItem("PASS" if check.passed else "FAIL"))
            self.checks_table.setItem(row, 2, QTableWidgetItem(check.detail))
        self.checks_table.resizeColumnsToContents()

    def _chain_for_item(self, item) -> ProofChainSnapshot | None:
        if item is None:
            return None
        return self._by_id.get(item.data(Qt.ItemDataRole.UserRole))

    def _request_overlay(self) -> None:
        chain = self._chain_for_item(self.chain_list.currentItem())
        if chain is not None:
            self.overlay_requested.emit(chain)


# Backward-compatible symbol for integrations that imported the old modeless window.
InferenceExplorerWindow = InferenceExplorerWidget
