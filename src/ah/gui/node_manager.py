from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ah.bootstrap import RuntimeServices
from ah.model import Domain

from .manual_nodes import ManualNodeManager, ManualNodeRequest


class NodeManagerWidget(QWidget):
    node_created = Signal(str)

    def __init__(
        self,
        services: RuntimeServices,
        selected_uid: Callable[[], str | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self._selected_uid = selected_uid
        self.manager = ManualNodeManager(services)

        root = QVBoxLayout(self)
        info = QLabel(
            "Ручное диагностическое создание. S и m пишутся только через AH Core; "
            "T/N/g/k пока создаются через perception/DSL."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form_box = QGroupBox("Новый узел")
        form = QFormLayout(form_box)
        self.kind = QComboBox()
        self.kind.addItem("m — сущность/понятие", "M")
        self.kind.addItem("S — абстрактный символ", "S")
        self.domain = QComboBox()
        for domain in Domain:
            self.domain.addItem(domain.value, domain.value)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Имя m или формы S через запятую")
        self.aliases = QLineEdit()
        self.aliases.setPlaceholderText("алиас 1, алиас 2")
        form.addRow("Тип", self.kind)
        form.addRow("Домен", self.domain)
        form.addRow("Имя / формы", self.text)
        self.duplicate_policy = QComboBox()
        self.duplicate_policy.addItem(
            "Переиспользовать единственный m в этом домене",
            "reuse_same_domain",
        )
        self.duplicate_policy.addItem(
            "Переиспользовать единственный m из любого C/P/H (общая identity)",
            "reuse_any_domain",
        )
        self.duplicate_policy.addItem(
            "Создать новый UID (намеренный тёзка/локальная identity)",
            "create_new",
        )
        form.addRow("Aliases (m)", self.aliases)
        form.addRow("Совпадение имени", self.duplicate_policy)
        root.addWidget(form_box)

        relation_box = QGroupBox("Связь с выделенным узлом")
        relation_form = QFormLayout(relation_box)
        self.make_link = QCheckBox("Создать L одновременно")
        self.relation = QComboBox()
        self.relation.setEditable(True)
        self.relation.addItems(["IS-A", "FOLLOW", "CAUSE"])
        self.direction = QComboBox()
        self.direction.addItem("выделенный → новый", "selected_to_new")
        self.direction.addItem("новый → выделенный", "new_to_selected")
        self.weight = QDoubleSpinBox()
        self.weight.setRange(0.0, 1.0)
        self.weight.setSingleStep(0.05)
        self.weight.setDecimals(3)
        self.weight.setValue(0.25)
        relation_form.addRow(self.make_link)
        relation_form.addRow("ID L", self.relation)
        relation_form.addRow("Направление", self.direction)
        relation_form.addRow("w", self.weight)
        root.addWidget(relation_box)

        seed_box = QGroupBox("Диагностическое возбуждение")
        seed_form = QFormLayout(seed_box)
        self.seed_enabled = QCheckBox("Подать seed после создания")
        self.seed_amount = QDoubleSpinBox()
        self.seed_amount.setRange(0.0, max(1.0, services.config.ignition.x_max * 4.0))
        self.seed_amount.setSingleStep(0.05)
        self.seed_amount.setDecimals(3)
        self.seed_amount.setValue(services.config.ignition.seeds.new_fact)
        seed_form.addRow(self.seed_enabled)
        seed_form.addRow("z", self.seed_amount)
        root.addWidget(seed_box)

        self.add_button = QPushButton("Добавить узел")
        self.add_button.clicked.connect(self._create)
        root.addWidget(self.add_button)
        root.addStretch(1)

        self.kind.currentIndexChanged.connect(self._sync_kind)
        self.make_link.toggled.connect(self._sync_link)
        self._sync_kind()
        self._sync_link()

    def _sync_kind(self) -> None:
        is_entity = self.kind.currentData() == "M"
        self.domain.setEnabled(is_entity)
        self.aliases.setEnabled(is_entity)
        self.duplicate_policy.setEnabled(is_entity)

    def _sync_link(self) -> None:
        enabled = self.make_link.isChecked()
        self.relation.setEnabled(enabled)
        self.direction.setEnabled(enabled)
        self.weight.setEnabled(enabled)

    def _create(self) -> None:
        aliases = tuple(
            value.strip()
            for value in self.aliases.text().replace(";", ",").split(",")
            if value.strip()
        )
        kind = str(self.kind.currentData())
        domain = Domain(str(self.domain.currentData())) if kind == "M" else None
        relation = self.relation.currentText().strip() if self.make_link.isChecked() else None
        seed = self.seed_amount.value() if self.seed_enabled.isChecked() else None
        request = ManualNodeRequest(
            kind=kind,
            text=self.text.text(),
            domain=domain,
            aliases=aliases,
            duplicate_policy=str(self.duplicate_policy.currentData()),
            selected_uid=self._selected_uid(),
            link_relation_id=relation,
            link_direction=str(self.direction.currentData()),
            link_weight=self.weight.value(),
            seed_amount=seed,
        )
        try:
            result = self.manager.create(request)
        except Exception as exc:
            QMessageBox.critical(self, "Добавление узла", f"{type(exc).__name__}: {exc}")
            return

        self.text.clear()
        self.aliases.clear()
        action = "создан" if result.created else "переиспользован"
        message = f"Узел {action}: {result.ref.uid}"
        if result.other_domain_matches:
            message += (
                f"; одноимённые m в других доменах: "
                f"{len(result.other_domain_matches)}"
            )
        if result.link_uid:
            message += f"; L={result.link_uid}"
        self.setToolTip(message)
        self.node_created.emit(result.ref.uid)
