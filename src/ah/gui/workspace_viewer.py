from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ah.diagnostics.graph_dump import GraphSnapshot


class WorkspaceViewerWidget(QWidget):
    """Live, human-readable view of the exact x > t Workspace.

    This widget is diagnostics only. It may order rows for operator convenience,
    but it never performs cognitive ranking, filtering, top-k selection, or writes
    to AH/Workspace. `semantic` is the same ACTIVE projection used by AgentContext.
    """

    node_selected = Signal(str)

    _HEADERS = ("Смысл", "Тип", "Домен", "x", "output", "age", "lifecycle", "UID")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.summary = QLabel("Workspace: —")
        self.summary.setWordWrap(True)

        self.table = QTableWidget(0, len(self._HEADERS), self)
        self.table.setHorizontalHeaderLabels(self._HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # ResizeToContents scans table contents after many updates and is expensive
        # on Windows. Keep the semantic column elastic and diagnostics user-resizable.
        for column in range(1, len(self._HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in {1: 46, 2: 54, 3: 78, 4: 78, 5: 52, 6: 88, 7: 240}.items():
            self.table.setColumnWidth(column, width)
        self.table.cellClicked.connect(self._cell_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        self._last_render_key = None

    def refresh(self, snapshot: GraphSnapshot, threshold: float, *, force: bool = False) -> None:
        node_by_uid = {node.uid: node for node in snapshot.nodes}
        rows = [node_by_uid[uid] for uid in snapshot.workspace_uids if uid in node_by_uid]
        # Display order only. Workspace membership remains exactly x > t.
        rows.sort(
            key=lambda node: (
                -(node.excitation if node.excitation is not None else float("-inf")),
                node.uid,
            )
        )
        selected_uid = self.selected_uid()
        render_key = (
            round(float(threshold), 9),
            tuple(
                (
                    node.uid,
                    snapshot.workspace_semantics.get(node.uid, node.semantic),
                    None if node.excitation is None else round(float(node.excitation), 6),
                    None if node.output is None else round(float(node.output), 6),
                    node.decay_age,
                    node.lifecycle_state,
                )
                for node in rows
            ),
        )
        if not force and render_key == self._last_render_key:
            # Tick may advance while all display values stay unchanged. Avoid a full
            # QTableWidget teardown/rebuild in that common case.
            return
        self._last_render_key = render_key

        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(rows))
            selected_row = -1
            for row, node in enumerate(rows):
                semantic = snapshot.workspace_semantics.get(node.uid, node.semantic)
                values = (
                    semantic,
                    node.kind,
                    node.domain or "—",
                    "—" if node.excitation is None else f"{node.excitation:.6f}",
                    "—" if node.output is None else f"{node.output:.6f}",
                    "—" if node.decay_age is None else str(node.decay_age),
                    node.lifecycle_state or "—",
                    node.uid,
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, node.uid)
                        item.setToolTip(semantic)
                    self.table.setItem(row, column, item)
                if node.uid == selected_uid:
                    selected_row = row
            if selected_row >= 0:
                self.table.selectRow(selected_row)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

        self.summary.setText(
            f"Workspace: {len(rows)} элементов | правило: x > {float(threshold):.3f} | tick={snapshot.tick}"
        )

    def set_selected_uid(self, uid: str | None) -> None:
        if not uid:
            self.table.clearSelection()
            return
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == uid:
                    self.table.selectRow(row)
                    self.table.scrollToItem(item)
                    return
            self.table.clearSelection()
        finally:
            self.table.blockSignals(False)

    def selected_uid(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _cell_clicked(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        if uid:
            self.node_selected.emit(str(uid))
