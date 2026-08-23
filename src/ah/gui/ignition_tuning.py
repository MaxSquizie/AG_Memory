from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from ah.config import DecaySettings, IgnitionSettings, WorkspaceSettings
from ah.ignition.tuning import midpoint_from_speed, speed_from_midpoint


class IgnitionTuningWidget(QWidget):
    tuning_changed = Signal(float, float, float, float)
    tuning_committed = Signal(float, float, float, float)
    mechanism_changed = Signal(bool, float, float)
    mechanism_committed = Signal(bool, float, float)
    corpus_import_requested = Signal(str, str, bool)
    raw_text_import_requested = Signal(str, bool, bool, bool)  # text, semantics, cold_save, strict
    memory_import_requested = Signal(str, bool)

    def __init__(self, decay: DecaySettings, tick_interval_seconds: float, resolved_symbol_seed: float = 0.95, parent: QWidget | None = None, *, ignition: IgnitionSettings | None = None, workspace: WorkspaceSettings | None = None) -> None:
        super().__init__(parent)
        self._syncing = False
        self._tick_interval_seconds = max(1e-6, float(tick_interval_seconds))
        ignition = ignition or IgnitionSettings()
        workspace = workspace or WorkspaceSettings()

        self.floor_slider = QSlider(Qt.Orientation.Horizontal); self.floor_slider.setRange(0, 90)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal); self.speed_slider.setRange(1, 100)
        self.reactivation_slider = QSlider(Qt.Orientation.Horizontal); self.reactivation_slider.setRange(0, 1000)
        self.symbol_slider = QSlider(Qt.Orientation.Horizontal); self.symbol_slider.setRange(0, 1000)
        self.floor_value = QLabel(); self.speed_value = QLabel(); self.reactivation_value = QLabel(); self.symbol_value = QLabel()

        decay_box = QGroupBox("Затухание")
        dl = QVBoxLayout(decay_box)
        for title, slider, value in (
            ("Плавающий низ", self.floor_slider, self.floor_value),
            ("Скорость спада верха", self.speed_slider, self.speed_value),
            ("Порог сильной реактивации", self.reactivation_slider, self.reactivation_value),
            ("Сильный импульс S", self.symbol_slider, self.symbol_value),
        ):
            row=QHBoxLayout(); row.addWidget(QLabel(title)); row.addWidget(slider,1); row.addWidget(value); dl.addLayout(row)

        self.pacemaker_enabled = QCheckBox("Pacemaker enabled")
        self.pacemaker_slider = QSlider(Qt.Orientation.Horizontal); self.pacemaker_slider.setRange(0, 500)
        self.pacemaker_value = QLabel()
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal); self.threshold_slider.setRange(0, 100)
        self.threshold_value = QLabel()
        mechanism_box = QGroupBox("Ignition / Workspace")
        ml=QVBoxLayout(mechanism_box); ml.addWidget(self.pacemaker_enabled)
        for title, slider, value in (
            ("Амплитуда pacemaker pulse", self.pacemaker_slider, self.pacemaker_value),
            ("Порог Workspace t", self.threshold_slider, self.threshold_value),
        ):
            row=QHBoxLayout(); row.addWidget(QLabel(title)); row.addWidget(slider,1); row.addWidget(value); ml.addLayout(row)
        nu = QLabel("Частота pacemaker ν задаётся отдельно параметром ignition.nu; pulse amplitude ≠ ν.")
        nu.setWordWrap(True); ml.addWidget(nu)

        self.corpus_path = QLineEdit(); self.corpus_path.setPlaceholderText("JSON / .ahm / .prj")
        self.corpus_domain = QComboBox(); self.corpus_domain.addItems(["C","P","H"])
        self.corpus_import = QPushButton("Загрузить структуру")
        st = QWidget(); sl=QVBoxLayout(st); sl.addWidget(self.corpus_path); sl.addWidget(self.corpus_domain); sl.addWidget(self.corpus_import); sl.addStretch(1)

        self.raw_text = QPlainTextEdit(); self.raw_text.setPlaceholderText("Текст/абзацы; пустая строка разделяет chunks")
        self.text_parse_semantics = QCheckBox("Разбирать в C/P через Perception"); self.text_parse_semantics.setChecked(True)
        self.text_strict = QCheckBox("Strict: любая ошибка делает импорт неуспешным"); self.text_strict.setChecked(True)
        self.raw_text_import = QPushButton("Загрузить текст")
        tt=QWidget(); tl=QVBoxLayout(tt); tl.addWidget(self.raw_text); tl.addWidget(self.text_parse_semantics); tl.addWidget(self.text_strict); tl.addWidget(self.raw_text_import)

        self.memory_path = QLineEdit(); self.memory_path.setPlaceholderText("persistence JSON")
        self.memory_cold_restore = QCheckBox("Cold restore: не восстанавливать x/queue"); self.memory_cold_restore.setChecked(True)
        self.memory_import = QPushButton("Загрузить снимок памяти")
        mt=QWidget(); mtl=QVBoxLayout(mt); mtl.addWidget(self.memory_path); mtl.addWidget(self.memory_cold_restore); mtl.addWidget(self.memory_import); mtl.addStretch(1)

        tabs=QTabWidget(); tabs.addTab(st,"Структура"); tabs.addTab(tt,"Текст"); tabs.addTab(mt,"Память")
        self.cold_save = QCheckBox("Сохранить импорт без runtime excitation"); self.cold_save.setChecked(True)
        import_box=QGroupBox("Импорт памяти"); il=QVBoxLayout(import_box); il.addWidget(tabs); il.addWidget(self.cold_save)

        # Runtime monitoring must stay compact on ordinary displays. Tuning is
        # needed frequently; corpus/memory import is operational but not something
        # that must occupy vertical space all the time. Keep both in the same team3
        # visual language, separated by one local tab switch.
        parameters_page = QWidget()
        parameters_layout = QVBoxLayout(parameters_page)
        parameters_layout.setContentsMargins(0, 0, 0, 0)
        parameters_layout.addWidget(mechanism_box)
        parameters_layout.addWidget(decay_box)
        parameters_layout.addStretch(1)

        self.sections = QTabWidget()
        self.sections.addTab(parameters_page, "Параметры")
        self.sections.addTab(import_box, "Импорт")

        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.addWidget(self.sections)

        self._commit_timer=QTimer(self); self._commit_timer.setSingleShot(True); self._commit_timer.setInterval(450); self._commit_timer.timeout.connect(self._emit_commit)
        self._mechanism_timer=QTimer(self); self._mechanism_timer.setSingleShot(True); self._mechanism_timer.setInterval(450); self._mechanism_timer.timeout.connect(self._emit_mechanism_commit)
        for slider in (self.floor_slider,self.speed_slider,self.reactivation_slider,self.symbol_slider):
            slider.valueChanged.connect(self._changed); slider.sliderReleased.connect(self._emit_commit)
        self.pacemaker_enabled.toggled.connect(self._mechanism_changed)
        for slider in (self.pacemaker_slider,self.threshold_slider):
            slider.valueChanged.connect(self._mechanism_changed); slider.sliderReleased.connect(self._emit_mechanism_commit)
        self.corpus_import.clicked.connect(lambda: self.corpus_import_requested.emit(self.corpus_path.text().strip(), self.corpus_domain.currentText(), self.cold_save.isChecked()))
        self.raw_text_import.clicked.connect(lambda: self.raw_text_import_requested.emit(self.raw_text.toPlainText(), self.text_parse_semantics.isChecked(), self.cold_save.isChecked(), self.text_strict.isChecked()))
        self.memory_import.clicked.connect(lambda: self.memory_import_requested.emit(self.memory_path.text().strip(), self.memory_cold_restore.isChecked()))
        self.set_parameters(decay, resolved_symbol_seed, tick_interval_seconds)
        self.set_mechanism(pacemaker_enabled=ignition.pacemaker.enabled, pacemaker_pulse=ignition.seeds.pacemaker, workspace_threshold=workspace.threshold)

    @staticmethod
    def midpoint_from_speed(value: int) -> float: return midpoint_from_speed(value)
    @staticmethod
    def speed_from_midpoint(midpoint_ticks: float) -> int: return speed_from_midpoint(midpoint_ticks)

    def values(self):
        return self.floor_slider.value()/100.0, self.midpoint_from_speed(self.speed_slider.value()), self.reactivation_slider.value()/1000.0, self.symbol_slider.value()/1000.0

    def mechanism_values(self):
        return self.pacemaker_enabled.isChecked(), self.pacemaker_slider.value()/1000.0, self.threshold_slider.value()/100.0

    def set_parameters(self, decay: DecaySettings, resolved_symbol_seed: float, tick_interval_seconds: float | None = None) -> None:
        if tick_interval_seconds is not None: self._tick_interval_seconds=max(1e-6,float(tick_interval_seconds))
        self._syncing=True
        try:
            self.floor_slider.setValue(round(decay.alpha*100)); self.speed_slider.setValue(self.speed_from_midpoint(decay.midpoint_ticks)); self.reactivation_slider.setValue(round(decay.reactivation_min_input*1000)); self.symbol_slider.setValue(round(float(resolved_symbol_seed)*1000)); self._refresh_labels()
        finally: self._syncing=False

    def set_decay(self, decay: DecaySettings, tick_interval_seconds: float | None = None) -> None:
        self.set_parameters(decay, self.symbol_slider.value()/1000.0, tick_interval_seconds)

    def set_mechanism(self, *, pacemaker_enabled: bool, pacemaker_pulse: float, workspace_threshold: float) -> None:
        self._syncing=True
        try:
            self.pacemaker_enabled.setChecked(bool(pacemaker_enabled)); self.pacemaker_slider.setValue(round(max(0.0,float(pacemaker_pulse))*1000)); self.threshold_slider.setValue(round(max(0.0,min(1.0,float(workspace_threshold)))*100)); self._refresh_mechanism_labels()
        finally: self._syncing=False

    def _refresh_labels(self):
        a,m,r,s=self.values(); self.floor_value.setText(f"{a*100:.0f}% x_start"); self.speed_value.setText(f"≈ {m*self._tick_interval_seconds:.2f} s"); self.reactivation_value.setText(f"Δx ≥ {r:.3f}"); self.symbol_value.setText(f"+{s:.3f} x")

    def _refresh_mechanism_labels(self):
        enabled,pulse,t=self.mechanism_values(); self.pacemaker_value.setText(f"+{pulse:.3f} x" if enabled else "off"); self.threshold_value.setText(f"t={t:.2f}")

    def _changed(self, _=None):
        self._refresh_labels()
        if self._syncing: return
        self.tuning_changed.emit(*self.values()); self._commit_timer.start()

    def _emit_commit(self):
        if self._syncing: return
        self._commit_timer.stop(); self.tuning_committed.emit(*self.values())

    def _mechanism_changed(self, _=None):
        self._refresh_mechanism_labels()
        if self._syncing: return
        self.mechanism_changed.emit(*self.mechanism_values()); self._mechanism_timer.start()

    def _emit_mechanism_commit(self):
        if self._syncing: return
        self._mechanism_timer.stop(); self.mechanism_committed.emit(*self.mechanism_values())
