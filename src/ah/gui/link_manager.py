from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
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
        root.addStretch(1)

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
