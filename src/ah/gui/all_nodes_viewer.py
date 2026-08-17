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


_SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_UID_ROLE = int(Qt.ItemDataRole.UserRole)


class _SortableItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(_SORT_ROLE)
        right = other.data(_SORT_ROLE)
        if left is not None and right is not None:
            try:
                return left < right
            except TypeError:
                return str(left) < str(right)
        return super().__lt__(other)


class AllNodesViewerWidget(QWidget):
    """Read-only operator view of every excitable canonical node.

    Default order is newest-added first. `creation_sequence` is diagnostic store
    metadata only; it never affects AH identity, inference, activation or Workspace.
    Clicking any header enables normal interactive sorting by that column.
    """

    node_selected = Signal(str)

    _HEADERS = (
        "Добавлен #",
        "Смысл",
        "Тип",
        "Домен",
        "x",
        "output",
        "1st x tick",
        "age",
        "lifecycle",
        "Workspace",
        "UID",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.summary = QLabel("Все узлы: —")
        self.summary.setWordWrap(True)

        self.table = QTableWidget(0, len(self._HEADERS), self)
        self.table.setHorizontalHeaderLabels(self._HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Avoid ResizeToContents on a live table: it repeatedly measures every cell
        # while x/output/age change. Operator can resize diagnostic columns manually.
        for column in range(len(self._HEADERS)):
            if column != 1:
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        widths = {0: 82, 2: 48, 3: 58, 4: 82, 5: 82, 6: 82, 7: 58, 8: 92, 9: 78, 10: 250}
        for column, width in widths.items():
            self.table.setColumnWidth(column, width)
        self.table.cellClicked.connect(self._cell_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)

        # Newest canonical additions are most useful while debugging a live turn.
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        self._semantic_cache: dict[str, str] = {}
        self._last_render_key = None

    def missing_semantic_uids(self, snapshot: GraphSnapshot) -> list[str]:
        """Return only nodes whose expensive ACTIVE projection is not cached yet."""
        present = {node.uid for node in snapshot.nodes}
        # GC may remove nodes; do not retain unbounded diagnostic strings forever.
        stale = set(self._semantic_cache) - present
        for uid in stale:
            self._semantic_cache.pop(uid, None)
        return [node.uid for node in snapshot.nodes if node.uid not in self._semantic_cache]

    @staticmethod
    def _item(text: str, *, sort_value=None, uid: str | None = None) -> _SortableItem:
        item = _SortableItem(text)
        if sort_value is not None:
            item.setData(_SORT_ROLE, sort_value)
        if uid is not None:
            item.setData(_UID_ROLE, uid)
        return item

    @staticmethod
    def _update_item(item: QTableWidgetItem | None, text: str, *, sort_value=None) -> None:
        if item is None:
            return
        if item.text() != text:
            item.setText(text)
        if item.data(_SORT_ROLE) != sort_value:
            item.setData(_SORT_ROLE, sort_value)

    def refresh(
        self,
        snapshot: GraphSnapshot,
        active_semantics: dict[str, str],
        *,
        force: bool = False,
    ) -> None:
        self._semantic_cache.update(active_semantics)
        selected_uid = self.selected_uid()
        header = self.table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        nodes = list(snapshot.nodes)
        current_rows: dict[str, int] = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            uid = None if item is None else item.data(_UID_ROLE)
            if uid:
                current_rows[str(uid)] = row
        same_membership = len(current_rows) == len(nodes) and all(node.uid in current_rows for node in nodes)

        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        try:
            if same_membership and not force:
                # Fast path: canonical rows are stable; only x/output/age/lifecycle/
                # Workspace and occasionally semantic text need to change. Updating
                # existing QTableWidgetItems avoids allocating ~11*N objects/tick.
                for node in nodes:
                    row = current_rows[node.uid]
                    semantic = self._semantic_cache.get(node.uid, node.semantic)
                    semantic_item = self.table.item(row, 1)
                    self._update_item(semantic_item, semantic, sort_value=semantic.casefold())
                    if semantic_item is not None:
                        semantic_item.setToolTip(semantic)
                    self._update_item(
                        self.table.item(row, 4),
                        "—" if node.excitation is None else f"{node.excitation:.6f}",
                        sort_value=-1.0 if node.excitation is None else float(node.excitation),
                    )
                    self._update_item(
                        self.table.item(row, 5),
                        "—" if node.output is None else f"{node.output:.6f}",
                        sort_value=-1.0 if node.output is None else float(node.output),
                    )
                    self._update_item(
                        self.table.item(row, 6),
                        "—" if node.first_excitation_tick is None else str(node.first_excitation_tick),
                        sort_value=-1 if node.first_excitation_tick is None else int(node.first_excitation_tick),
                    )
                    self._update_item(
                        self.table.item(row, 7),
                        "—" if node.decay_age is None else str(node.decay_age),
                        sort_value=-1 if node.decay_age is None else int(node.decay_age),
                    )
                    self._update_item(
                        self.table.item(row, 8),
                        node.lifecycle_state or "—",
                        sort_value=node.lifecycle_state or "",
                    )
                    self._update_item(
                        self.table.item(row, 9),
                        "ДА" if node.in_workspace else "",
                        sort_value=int(node.in_workspace),
                    )
            else:
                self.table.setRowCount(len(nodes))
                for row, node in enumerate(nodes):
                    semantic = self._semantic_cache.get(node.uid, node.semantic)
                    semantic_item = self._item(semantic, sort_value=semantic.casefold(), uid=node.uid)
                    semantic_item.setToolTip(semantic)
                    values = (
                        self._item(str(node.creation_sequence), sort_value=node.creation_sequence, uid=node.uid),
                        semantic_item,
                        self._item(node.kind, sort_value=node.kind, uid=node.uid),
                        self._item(node.domain or "—", sort_value=node.domain or "", uid=node.uid),
                        self._item(
                            "—" if node.excitation is None else f"{node.excitation:.6f}",
                            sort_value=-1.0 if node.excitation is None else float(node.excitation),
                            uid=node.uid,
                        ),
                        self._item(
                            "—" if node.output is None else f"{node.output:.6f}",
                            sort_value=-1.0 if node.output is None else float(node.output),
                            uid=node.uid,
                        ),
                        self._item(
                            "—" if node.first_excitation_tick is None else str(node.first_excitation_tick),
                            sort_value=-1 if node.first_excitation_tick is None else int(node.first_excitation_tick),
                            uid=node.uid,
                        ),
                        self._item(
                            "—" if node.decay_age is None else str(node.decay_age),
                            sort_value=-1 if node.decay_age is None else int(node.decay_age),
                            uid=node.uid,
                        ),
                        self._item(node.lifecycle_state or "—", sort_value=node.lifecycle_state or "", uid=node.uid),
                        self._item("ДА" if node.in_workspace else "", sort_value=int(node.in_workspace), uid=node.uid),
                        self._item(node.uid, sort_value=node.uid, uid=node.uid),
                    )
                    for column, item in enumerate(values):
                        self.table.setItem(row, column, item)
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)

        self.table.sortItems(sort_column, sort_order)
        self.set_selected_uid(selected_uid)
        self.summary.setText(
            f"Все узлы: {len(snapshot.nodes)} | tick={snapshot.tick} | "
            "по умолчанию: новые сверху; заголовки колонок сортируют список"
        )

    def set_selected_uid(self, uid: str | None) -> None:
        if not uid:
            self.table.clearSelection()
            return
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None and item.data(_UID_ROLE) == uid:
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
        value = item.data(_UID_ROLE)
        return str(value) if value else None

    def _cell_clicked(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        uid = item.data(_UID_ROLE)
        if uid:
            self.node_selected.emit(str(uid))
