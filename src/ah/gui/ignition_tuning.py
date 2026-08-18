from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ah.config import DecaySettings, IgnitionSettings, WorkspaceSettings
from ah.ignition.tuning import midpoint_from_speed, speed_from_midpoint


class IgnitionTuningWidget(QWidget):
    """Operator-facing hot controls for the floating decay epoch.

    alpha controls the retained relative floor, speed is an ergonomic projection
    of sigmoid midpoint_ticks, and reactivation_min_input is deliberately exposed
    because it decides when an incoming impulse is strong enough to rebase the
    local decay origin/floor. All three controls are hot-safe.
    """

    tuning_changed = Signal(float, float, float, float)   # alpha, midpoint, min_input, resolved_S
    tuning_committed = Signal(float, float, float, float) # persist after drag/idle
    mechanism_changed = Signal(bool, float, float)        # pacemaker, pulse, workspace t
    mechanism_committed = Signal(bool, float, float)
    corpus_import_requested = Signal(str, str, bool)      # path, domain, cold_save
    raw_text_import_requested = Signal(str, bool, bool)   # text, parse_semantics, cold_save
    memory_import_requested = Signal(str, bool)           # path, cold_restore

    def __init__(
        self,
        decay: DecaySettings,
        tick_interval_seconds: float,
        resolved_symbol_seed: float = 0.95,
        parent: QWidget | None = None,
        *,
        ignition: IgnitionSettings | None = None,
        workspace: WorkspaceSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._tick_interval_seconds = max(1e-6, float(tick_interval_seconds))
        self._syncing = False
        ignition = ignition or IgnitionSettings()
        workspace = workspace or WorkspaceSettings()

        self.floor_title = QLabel("Плавающий низ")
        self.floor_slider = QSlider(Qt.Orientation.Horizontal)
        self.floor_slider.setRange(0, 90)
        self.floor_slider.setToolTip(
            "Нижняя граница текущей decay-эпохи: x_floor = alpha × x_start. "
            "Она меняется при сильной реактивации или новом prompt. "
            "0% — подсветка гаснет полностью; факты в графе остаются."
        )
        self.floor_value = QLabel()
        self.floor_value.setMinimumWidth(112)

        self.speed_title = QLabel("Скорость спада верха")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setToolTip(
            "Вправо = быстрее уйти с верхнего участка. Технически регулирует "
            "midpoint_ticks sigmoid-кривой в логарифмическом масштабе."
        )
        self.speed_value = QLabel()
        self.speed_value.setMinimumWidth(150)

        self.reactivation_title = QLabel("Порог сильной реактивации")
        self.reactivation_slider = QSlider(Qt.Orientation.Horizontal)
        # 0..1 x units with millesimal resolution. This is intentionally not hidden
        # in the generic config editor: it is an experimental control used together
        # with the floating floor while observing the live graph.
        self.reactivation_slider.setRange(0, 1000)
        self.reactivation_slider.setToolTip(
            "Минимальный прирост x, необходимый для reset локальной decay-эпохи. "
            "Ниже порога импульс временно возбуждает узел, но не поднимает его floor."
        )
        self.reactivation_value = QLabel()
        self.reactivation_value.setMinimumWidth(112)

        self.symbol_title = QLabel("Сильный импульс S")
        self.symbol_slider = QSlider(Qt.Orientation.Horizontal)
        self.symbol_slider.setRange(0, 1000)
        self.symbol_slider.setToolTip(
            "Сильное пост-семантическое возбуждение canonical S, реально "
            "распознанного в новом prompt. Применяется и к S, созданному в этом же turn. "
            "Предварительные омографические surface-кандидаты используют отдельный "
            "ignition.seeds.sensory_symbol."
        )
        self.symbol_value = QLabel()
        self.symbol_value.setMinimumWidth(112)

        floor_row = QHBoxLayout()
        floor_row.addWidget(self.floor_title)
        floor_row.addWidget(self.floor_slider, 1)
        floor_row.addWidget(self.floor_value)
        speed_row = QHBoxLayout()
        speed_row.addWidget(self.speed_title)
        speed_row.addWidget(self.speed_slider, 1)
        speed_row.addWidget(self.speed_value)
        reactivation_row = QHBoxLayout()
        reactivation_row.addWidget(self.reactivation_title)
        reactivation_row.addWidget(self.reactivation_slider, 1)
        reactivation_row.addWidget(self.reactivation_value)
        symbol_row = QHBoxLayout()
        symbol_row.addWidget(self.symbol_title)
        symbol_row.addWidget(self.symbol_slider, 1)
        symbol_row.addWidget(self.symbol_value)

        decay_box = QGroupBox("Затухание")
        decay_layout = QVBoxLayout(decay_box)
        decay_layout.addLayout(floor_row)
        decay_layout.addLayout(speed_row)
        decay_layout.addLayout(reactivation_row)
        decay_layout.addLayout(symbol_row)

        self.pacemaker_enabled = QCheckBox("Фоновый метроном (pacemaker)")
        self.pacemaker_enabled.setToolTip(
            "Пока включён, Ignition периодически слабо подсвечивает случайные узлы. "
            "Выключите, если граф не должен мерцать сам по себе."
        )
        self.pacemaker_title = QLabel("Сила метронома")
        self.pacemaker_slider = QSlider(Qt.Orientation.Horizontal)
        self.pacemaker_slider.setRange(0, 500)
        self.pacemaker_slider.setToolTip("Величина фонового импульса ν. Не записывает факты в память.")
        self.pacemaker_value = QLabel()
        self.pacemaker_value.setMinimumWidth(112)
        pacemaker_row = QHBoxLayout()
        pacemaker_row.addWidget(self.pacemaker_title)
        pacemaker_row.addWidget(self.pacemaker_slider, 1)
        pacemaker_row.addWidget(self.pacemaker_value)

        self.threshold_title = QLabel("Порог Workspace")
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setToolTip(
            "В контекст LLM попадает только то, у чего x выше этого порога. "
            "Сами факты в графе не удаляются."
        )
        self.threshold_value = QLabel()
        self.threshold_value.setMinimumWidth(112)
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(self.threshold_title)
        threshold_row.addWidget(self.threshold_slider, 1)
        threshold_row.addWidget(self.threshold_value)

        mechanism_box = QGroupBox("Механизм Ignition")
        mechanism_layout = QVBoxLayout(mechanism_box)
        mechanism_layout.addWidget(self.pacemaker_enabled)
        mechanism_layout.addLayout(pacemaker_row)
        mechanism_layout.addLayout(threshold_row)

        self.corpus_path = QLineEdit()
        self.corpus_path.setPlaceholderText("JSON / .ahm / .prj — факты без подсветки")
        self.corpus_browse = QPushButton("Файл…")
        self.corpus_browse.clicked.connect(self._browse_corpus)
        path_row = QHBoxLayout()
        path_row.addWidget(self.corpus_path, 1)
        path_row.addWidget(self.corpus_browse)
        self.corpus_domain = QComboBox()
        self.corpus_domain.addItems(["C", "P", "H"])
        self.corpus_import = QPushButton("Загрузить в память")
        self.corpus_import.clicked.connect(self._request_corpus_import)
        structure_tab = QWidget()
        structure_layout = QVBoxLayout(structure_tab)
        structure_layout.addLayout(path_row)
        domain_row = QHBoxLayout()
        domain_row.addWidget(QLabel("Домен"))
        domain_row.addWidget(self.corpus_domain)
        domain_row.addStretch(1)
        structure_layout.addLayout(domain_row)
        structure_layout.addWidget(self.corpus_import)
        structure_layout.addStretch(1)

        self.raw_text = QPlainTextEdit()
        self.raw_text.setPlaceholderText(
            "Текст или абзацы (пустая строка между ними). "
            "С разбором — факты в память; без LLM остаётся только опыт в H."
        )
        self.raw_text.setMinimumHeight(90)
        self.text_parse_semantics = QCheckBox("Разбирать в факты (нужен LLM)")
        self.text_parse_semantics.setChecked(True)
        self.text_parse_semantics.setToolTip(
            "Каждый абзац идёт через Perception в факты C/P и H-опыт. "
            "Без LLM абзац пишется только как опыт пользователя."
        )
        self.raw_text_import = QPushButton("Загрузить текст")
        self.raw_text_import.clicked.connect(self._request_raw_text_import)
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)
        text_layout.addWidget(self.raw_text)
        text_layout.addWidget(self.text_parse_semantics)
        text_layout.addWidget(self.raw_text_import)

        memory_hint = QLabel(
            "Заменяет текущую каноническую память снимком persistence JSON. "
            "Граф, контекст диалога и (если галочка снята) подсветка берутся из файла."
        )
        memory_hint.setWordWrap(True)
        self.memory_import = QPushButton("Импорт снимка…")
        self.memory_import.clicked.connect(self._request_memory_import)
        memory_tab = QWidget()
        memory_layout = QVBoxLayout(memory_tab)
        memory_layout.addWidget(memory_hint)
        memory_layout.addWidget(self.memory_import)
        memory_layout.addStretch(1)

        tabs = QTabWidget()
        tabs.addTab(structure_tab, "Структура")
        tabs.addTab(text_tab, "Текст")
        tabs.addTab(memory_tab, "Память AG")

        self.corpus_cold_save = QCheckBox("Сохранить без подсветки")
        self.corpus_cold_save.setChecked(True)
        self.corpus_cold_save.setToolTip(
            "Пишет канонику в JSON и не сохраняет текущие уровни возбуждения. "
            "Для снимка AG то же: загрузить граф, не восстанавливая x."
        )

        corpus_box = QGroupBox("Холодная загрузка памяти")
        corpus_layout = QVBoxLayout(corpus_box)
        corpus_layout.addWidget(tabs)
        corpus_layout.addWidget(self.corpus_cold_save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(mechanism_box)
        layout.addWidget(decay_box)
        layout.addWidget(corpus_box)

        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(450)
        self._commit_timer.timeout.connect(self._emit_commit)
        self._mechanism_timer = QTimer(self)
        self._mechanism_timer.setSingleShot(True)
        self._mechanism_timer.setInterval(450)
        self._mechanism_timer.timeout.connect(self._emit_mechanism_commit)

        self.floor_slider.valueChanged.connect(self._changed)
        self.speed_slider.valueChanged.connect(self._changed)
        self.reactivation_slider.valueChanged.connect(self._changed)
        self.symbol_slider.valueChanged.connect(self._changed)
        self.floor_slider.sliderReleased.connect(self._emit_commit)
        self.speed_slider.sliderReleased.connect(self._emit_commit)
        self.reactivation_slider.sliderReleased.connect(self._emit_commit)
        self.symbol_slider.sliderReleased.connect(self._emit_commit)

        self.pacemaker_enabled.toggled.connect(self._mechanism_changed)
        self.pacemaker_slider.valueChanged.connect(self._mechanism_changed)
        self.threshold_slider.valueChanged.connect(self._mechanism_changed)
        self.pacemaker_slider.sliderReleased.connect(self._emit_mechanism_commit)
        self.threshold_slider.sliderReleased.connect(self._emit_mechanism_commit)

        self.set_parameters(decay, resolved_symbol_seed, tick_interval_seconds)
        self.set_mechanism(
            pacemaker_enabled=ignition.pacemaker.enabled,
            pacemaker_pulse=ignition.seeds.pacemaker,
            workspace_threshold=workspace.threshold,
        )

    @staticmethod
    def midpoint_from_speed(value: int) -> float:
        return midpoint_from_speed(value)

    @staticmethod
    def speed_from_midpoint(midpoint_ticks: float) -> int:
        return speed_from_midpoint(midpoint_ticks)

    def values(self) -> tuple[float, float, float, float]:
        return (
            self.floor_slider.value() / 100.0,
            self.midpoint_from_speed(self.speed_slider.value()),
            self.reactivation_slider.value() / 1000.0,
            self.symbol_slider.value() / 1000.0,
        )

    def set_parameters(
        self,
        decay: DecaySettings,
        resolved_symbol_seed: float,
        tick_interval_seconds: float | None = None,
    ) -> None:
        if tick_interval_seconds is not None:
            self._tick_interval_seconds = max(1e-6, float(tick_interval_seconds))
        self._syncing = True
        try:
            self.floor_slider.setValue(round(decay.alpha * 100.0))
            self.speed_slider.setValue(self.speed_from_midpoint(decay.midpoint_ticks))
            self.reactivation_slider.setValue(round(decay.reactivation_min_input * 1000.0))
            self.symbol_slider.setValue(round(float(resolved_symbol_seed) * 1000.0))
            self._refresh_labels()
        finally:
            self._syncing = False

    def set_mechanism(
        self,
        *,
        pacemaker_enabled: bool,
        pacemaker_pulse: float,
        workspace_threshold: float,
    ) -> None:
        self._syncing = True
        try:
            self.pacemaker_enabled.setChecked(bool(pacemaker_enabled))
            self.pacemaker_slider.setValue(round(max(0.0, float(pacemaker_pulse)) * 1000.0))
            self.threshold_slider.setValue(round(max(0.0, min(1.0, float(workspace_threshold))) * 100.0))
            self._refresh_mechanism_labels()
        finally:
            self._syncing = False

    def mechanism_values(self) -> tuple[bool, float, float]:
        return (
            self.pacemaker_enabled.isChecked(),
            self.pacemaker_slider.value() / 1000.0,
            self.threshold_slider.value() / 100.0,
        )

    def set_decay(self, decay: DecaySettings, tick_interval_seconds: float | None = None) -> None:
        # Compatibility for callers that only update decay. Preserve current S seed.
        self.set_parameters(decay, self.symbol_slider.value() / 1000.0, tick_interval_seconds)

    def _refresh_labels(self) -> None:
        alpha, midpoint, min_input, resolved_symbol = self.values()
        seconds = midpoint * self._tick_interval_seconds
        self.floor_value.setText(f"{alpha * 100:.0f}% x_start")
        self.speed_value.setText(f"середина ≈ {seconds:.2f} с")
        self.reactivation_value.setText(f"Δx ≥ {min_input:.3f}")
        self.symbol_value.setText(f"+{resolved_symbol:.3f} x")
        if hasattr(self, "pacemaker_value"):
            self._refresh_mechanism_labels()

    def _refresh_mechanism_labels(self) -> None:
        enabled, pulse, threshold = self.mechanism_values()
        self.pacemaker_value.setText("выкл" if not enabled else f"+{pulse:.3f} x")
        self.threshold_value.setText(f"x > {threshold:.2f}")

    def _changed(self, _value: int) -> None:
        self._refresh_labels()
        if self._syncing:
            return
        alpha, midpoint, min_input, resolved_symbol = self.values()
        self.tuning_changed.emit(alpha, midpoint, min_input, resolved_symbol)
        self._commit_timer.start()

    def _mechanism_changed(self, _value=None) -> None:
        self._refresh_mechanism_labels()
        if self._syncing:
            return
        enabled, pulse, threshold = self.mechanism_values()
        self.mechanism_changed.emit(enabled, pulse, threshold)
        self._mechanism_timer.start()

    def _emit_commit(self) -> None:
        if self._syncing:
            return
        self._commit_timer.stop()
        alpha, midpoint, min_input, resolved_symbol = self.values()
        self.tuning_committed.emit(alpha, midpoint, min_input, resolved_symbol)

    def _emit_mechanism_commit(self) -> None:
        if self._syncing:
            return
        self._mechanism_timer.stop()
        enabled, pulse, threshold = self.mechanism_values()
        self.mechanism_committed.emit(enabled, pulse, threshold)

    def _browse_corpus(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Холодная загрузка памяти",
            "",
            "Корпус (*.json *.ahm *.prj);;JSON (*.json);;AHM (*.ahm);;PRJ (*.prj)",
        )
        if path:
            self.corpus_path.setText(path)

    def _request_corpus_import(self) -> None:
        path = self.corpus_path.text().strip()
        if not path:
            self._browse_corpus()
            path = self.corpus_path.text().strip()
        if not path:
            return
        self.corpus_import_requested.emit(
            path,
            self.corpus_domain.currentText(),
            self.corpus_cold_save.isChecked(),
        )

    def _request_raw_text_import(self) -> None:
        text = self.raw_text.toPlainText().strip()
        if not text:
            return
        self.raw_text_import_requested.emit(
            text,
            self.text_parse_semantics.isChecked(),
            self.corpus_cold_save.isChecked(),
        )

    def _request_memory_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт памяти AG",
            "",
            "AH persistence (*.json);;Все файлы (*)",
        )
        if not path:
            return
        self.memory_import_requested.emit(path, self.corpus_cold_save.isChecked())
