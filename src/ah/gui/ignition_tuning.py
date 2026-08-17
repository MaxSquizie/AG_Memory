from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from ah.config import DecaySettings
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

    def __init__(
        self,
        decay: DecaySettings,
        tick_interval_seconds: float,
        resolved_symbol_seed: float = 0.95,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tick_interval_seconds = max(1e-6, float(tick_interval_seconds))
        self._syncing = False

        self.floor_title = QLabel("Плавающий низ")
        self.floor_slider = QSlider(Qt.Orientation.Horizontal)
        self.floor_slider.setRange(0, 90)
        self.floor_slider.setToolTip(
            "Нижняя граница текущей decay-эпохи: x_floor = alpha × x_start. "
            "Она меняется при сильной реактивации или новом prompt."
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(floor_row)
        layout.addLayout(speed_row)
        layout.addLayout(reactivation_row)
        layout.addLayout(symbol_row)

        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(450)
        self._commit_timer.timeout.connect(self._emit_commit)

        self.floor_slider.valueChanged.connect(self._changed)
        self.speed_slider.valueChanged.connect(self._changed)
        self.reactivation_slider.valueChanged.connect(self._changed)
        self.symbol_slider.valueChanged.connect(self._changed)
        self.floor_slider.sliderReleased.connect(self._emit_commit)
        self.speed_slider.sliderReleased.connect(self._emit_commit)
        self.reactivation_slider.sliderReleased.connect(self._emit_commit)
        self.symbol_slider.sliderReleased.connect(self._emit_commit)

        self.set_parameters(decay, resolved_symbol_seed, tick_interval_seconds)

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

    def _changed(self, _value: int) -> None:
        self._refresh_labels()
        if self._syncing:
            return
        alpha, midpoint, min_input, resolved_symbol = self.values()
        self.tuning_changed.emit(alpha, midpoint, min_input, resolved_symbol)
        self._commit_timer.start()

    def _emit_commit(self) -> None:
        if self._syncing:
            return
        self._commit_timer.stop()
        alpha, midpoint, min_input, resolved_symbol = self.values()
        self.tuning_committed.emit(alpha, midpoint, min_input, resolved_symbol)
