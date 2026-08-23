from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ah.bootstrap import RuntimeServices

from .manual_links import ManualLinkManager, ManualLinkRequest


class LinkManagerWidget(QWidget):
    link_created = Signal(str)

    def __init__(
        self,
        services: RuntimeServices,
        selected_uid: Callable[[], str | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self._selected_uid = selected_uid
        self.manager = ManualLinkManager(services)
        self._canvas_pick_mode = False

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.source = QLineEdit()
        self.source.setReadOnly(True)
        self.target = QLineEdit()
        self.target.setReadOnly(True)

        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.addWidget(self.source, 1)
        source_button = QPushButton("← выбранный")
        source_button.clicked.connect(lambda: self._capture(self.source))
        source_layout.addWidget(source_button)

        target_row = QWidget()
        target_layout = QHBoxLayout(target_row)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.addWidget(self.target, 1)
        target_button = QPushButton("← выбранный")
        target_button.clicked.connect(lambda: self._capture(self.target))
        target_layout.addWidget(target_button)

        self.relation = QComboBox()
        self.relation.setEditable(True)
        self.relation.addItems(["IS-A", "FOLLOW", "CAUSE"])
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0.0, 1.0)
        self.weight.setSingleStep(0.05)
        self.weight.setDecimals(3)
        self.weight.setValue(0.25)

        form.addRow("Источник", source_row)
        form.addRow("Цель", target_row)
        form.addRow("ID L", self.relation)
        form.addRow("w", self.weight)
        root.addLayout(form)

        buttons = QHBoxLayout()
        swap = QPushButton("Поменять местами")
        swap.clicked.connect(self._swap)
        create = QPushButton("Связать")
        create.clicked.connect(self._create)
        clear = QPushButton("Очистить")
        clear.clicked.connect(self._clear)
        buttons.addWidget(swap)
        buttons.addWidget(create)
        buttons.addWidget(clear)
        root.addLayout(buttons)

        self.canvas_pick = QCheckBox("Выбирать источник и цель кликами на Canvas")
        self.canvas_pick.setToolTip(
            "Включите режим и последовательно кликните два узла: первый станет источником, второй — целью."
        )
        self.canvas_pick.toggled.connect(self._set_canvas_pick_mode)
        root.addWidget(self.canvas_pick)
        self.pick_status = QLabel("Готово: выберите источник и цель")
        self.pick_status.setWordWrap(True)
        root.addWidget(self.pick_status)
        root.addStretch(1)

    def _set_canvas_pick_mode(self, enabled: bool) -> None:
        self._canvas_pick_mode = bool(enabled)
        if enabled:
            self.pick_status.setText("Режим выбора включён: кликните источник, затем цель")
        else:
            self.pick_status.setText("Режим выбора выключен")

    def on_canvas_selection(self, uid: str) -> None:
        """Capture sequential canvas selections without losing the first endpoint."""
        if not self._canvas_pick_mode or not uid:
            return
        if not self.source.text():
            self.source.setText(uid)
            self.pick_status.setText(f"Источник: {uid} · теперь выберите цель")
            return
        if not self.target.text() and uid != self.source.text():
            self.target.setText(uid)
            self.pick_status.setText(
                f"Готово: {self.source.text()} → {uid} · нажмите «Связать»"
            )
            return
        if uid == self.source.text():
            self.pick_status.setText("Источник и цель должны быть разными узлами")

    def _capture(self, target: QLineEdit) -> None:
        uid = self._selected_uid()
        if not uid:
            QMessageBox.information(self, "Связь", "Сначала выберите узел на canvas.")
            return
        target.setText(uid)

    def _swap(self) -> None:
        a, b = self.source.text(), self.target.text()
        self.source.setText(b)
        self.target.setText(a)

    def _clear(self) -> None:
        self.source.clear()
        self.target.clear()

    def _create(self) -> None:
        request = ManualLinkRequest(
            source_uid=self.source.text(),
            target_uid=self.target.text(),
            relation_id=self.relation.currentText(),
            weight=self.weight.value(),
        )
        try:
            result = self.manager.create(request)
        except Exception as exc:
            QMessageBox.critical(self, "Связь", f"{type(exc).__name__}: {exc}")
            return
        self.link_created.emit(result.link.uid)
