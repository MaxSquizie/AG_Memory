from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ah.config import AppConfig

from .config_store import ApplyMode, ConfigDocument


class ConfigEditor(QWidget):
    config_saved = Signal(object, object)  # AppConfig, tuple[str, ...]

    def __init__(self, config_path: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = ConfigDocument(config_path)
        self._loading = False

        self.status = QLabel()
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Параметр", "Значение", "Применение", "Тип"])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemChanged.connect(self._item_changed)

        self.browse_model = QPushButton("Папка LLM…")
        self.browse_model.clicked.connect(self._browse_llm)
        self.ollama_hint = QLabel("Для backend=ollama модель выбирается на панели LLM.")
        self.ollama_hint.setWordWrap(True)
        self.validate_button = QPushButton("Проверить")
        self.validate_button.clicked.connect(self._validate)
        self.save_button = QPushButton("Сохранить / применить")
        self.save_button.clicked.connect(self._save)
        self.reload_button = QPushButton("Перечитать")
        self.reload_button.clicked.connect(self.reload)

        buttons = QHBoxLayout()
        buttons.addWidget(self.browse_model)
        buttons.addWidget(self.ollama_hint, 1)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.reload_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.tree, 1)
        layout.addLayout(buttons)
        self.reload()

    def _sync_backend_controls(self) -> None:
        try:
            backend = str(self.document.get("llm.backend") or "builtin_process").strip().lower()
        except KeyError:
            backend = "builtin_process"
        pytorch = backend != "ollama"
        self.browse_model.setVisible(pytorch)
        self.ollama_hint.setVisible(not pytorch)

    def reload(self) -> None:
        try:
            self.document.reload()
        except Exception as exc:
            QMessageBox.critical(self, "Config", str(exc))
            return
        self._loading = True
        self.tree.clear()
        sections: dict[str, QTreeWidgetItem] = {}
        for entry in self.document.entries():
            section, _, local = entry.path.partition(".")
            root = sections.get(section)
            if root is None:
                root = QTreeWidgetItem([section, "", "", ""])
                root.setFirstColumnSpanned(True)
                self.tree.addTopLevelItem(root)
                sections[section] = root
            item = QTreeWidgetItem(
                [
                    local,
                    self._display(entry.value),
                    entry.apply_mode.value,
                    entry.value_type.__name__,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, entry.path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            root.addChild(item)
        self.tree.expandAll()
        self._loading = False
        self._sync_backend_controls()
        self._update_status()

    @staticmethod
    def _display(value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            import json
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if column != 1:
            if path and column == 0:
                self._loading = True
                item.setText(0, str(path).partition(".")[2])
                self._loading = False
            return
        if not path:
            return
        try:
            value = self.document.set_from_text(str(path), item.text(1))
            self._loading = True
            item.setText(1, self._display(value))
            self._loading = False
            self._sync_backend_controls()
            self._update_status()
        except Exception as exc:
            self._loading = True
            item.setText(1, self._display(self.document.get(str(path))))
            self._loading = False
            QMessageBox.warning(self, "Config", f"{path}: {exc}")

    def _browse_llm(self) -> None:
        current = str(self.document.get("paths.llm_model_dir") or "")
        chosen = QFileDialog.getExistingDirectory(self, "Папка локальной LLM", current)
        if not chosen:
            return
        self.document.set("paths.llm_model_dir", chosen.replace("\\", "/"))
        self._sync_path("paths.llm_model_dir")
        self._update_status()

    def _sync_path(self, path: str) -> None:
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            for j in range(root.childCount()):
                item = root.child(j)
                if item.data(0, Qt.ItemDataRole.UserRole) == path:
                    self._loading = True
                    item.setText(1, self._display(self.document.get(path)))
                    self._loading = False
                    return

    def set_external_values(self, values: dict[str, object], *, save: bool = False) -> None:
        """Synchronize specialized live controls with the generic TOML editor."""
        try:
            for path, value in values.items():
                self.document.set(path, value)
                self._sync_path(path)
            self._update_status()
            if save:
                self._save()
        except Exception as exc:
            QMessageBox.warning(self, "Config", str(exc))

    def _validate(self) -> None:
        try:
            self.document.validate()
        except Exception as exc:
            QMessageBox.critical(self, "Config", f"Ошибка конфигурации:\n{exc}")
            return
        QMessageBox.information(self, "Config", "Конфигурация валидна.")

    def _save(self) -> None:
        changed = self.document.changed_paths()
        if not changed:
            self._update_status()
            return
        try:
            new_config = self.document.save()
        except Exception as exc:
            QMessageBox.critical(self, "Config", f"Не удалось сохранить:\n{exc}")
            return
        self.config_saved.emit(new_config, changed)
        self.reload()

    def _update_status(self) -> None:
        changed = self.document.changed_paths()
        if not changed:
            self.status.setText("Конфиг синхронизирован")
            return
        modes = {ConfigDocument.apply_mode(path) for path in changed}
        if ApplyMode.RESTART_RUNTIME in modes:
            suffix = "нужен перезапуск runtime"
        elif ApplyMode.RESTART_LLM in modes:
            suffix = "нужен перезапуск LLM"
        elif ApplyMode.NEXT_TURN in modes:
            suffix = "вступит в силу со следующего turn"
        else:
            suffix = "можно применить live"
        self.status.setText(f"Изменено: {len(changed)} · {suffix}")
