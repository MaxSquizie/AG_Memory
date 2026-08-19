from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from ah.config import AppConfig
from ah.diagnostics.graph_dump import GraphSnapshot

from .graph_canvas import GraphCanvasWidget


class _FrozenGraphInspector:
    def __init__(self, snapshot: GraphSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> GraphSnapshot:
        return self._snapshot


class _NullClock:
    @property
    def running(self) -> bool:
        return False

    def add_listener(self, _callback) -> None:
        return None

    def remove_listener(self, _callback) -> None:
        return None


@dataclass(slots=True)
class _FrozenCanvasServices:
    config: AppConfig
    graph_inspector: _FrozenGraphInspector
    clock: _NullClock


class CanvasBrowserWidget(QWidget):
    """Central browser for the live AH canvas and the last frozen M2 sandbox.

    The sandbox page renders one immutable diagnostic GraphSnapshot. It never owns
    or mutates canonical AH and it never advances Ignition time. A new M2 run simply
    replaces the previous frozen page.
    """

    live_node_selected = Signal(str)
    live_edge_selected = Signal(str)
    sandbox_node_selected = Signal(str)
    sandbox_edge_selected = Signal(str)
    page_changed = Signal(str)

    LIVE_KEY = "LIVE"
    M2_KEY = "M2"

    def __init__(self, live_canvas: GraphCanvasWidget, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.live_canvas = live_canvas
        self.config = config
        self.sandbox_canvas: GraphCanvasWidget | None = None
        self._sandbox_placeholder = QLabel(
            "M2 sandbox ещё не создан. Запустите M2 acceptance, чтобы открыть его полный граф."
        )
        self._sandbox_placeholder.setWordWrap(True)
        self._sandbox_placeholder.setStyleSheet("padding: 24px; color: #aeb8c8;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.setContentsMargins(6, 4, 6, 4)
        header.addWidget(QLabel("Canvas:"))
        self.selector = QComboBox()
        self.selector.addItem("Обычный AH", self.LIVE_KEY)
        self.selector.addItem("M2 sandbox", self.M2_KEY)
        header.addWidget(self.selector)
        self.info = QLabel("LIVE")
        self.info.setStyleSheet("color: #9eabbc;")
        header.addWidget(self.info, 1)
        layout.addLayout(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.live_canvas)
        self.stack.addWidget(self._sandbox_placeholder)
        layout.addWidget(self.stack, 1)

        self.live_canvas.node_selected.connect(self.live_node_selected.emit)
        self.live_canvas.edge_selected.connect(self.live_edge_selected.emit)
        self.selector.currentIndexChanged.connect(self._selection_changed)
        self._selection_changed(0)

    def set_config(self, config: AppConfig) -> None:
        self.config = config
        self.live_canvas.set_settings(config.gui)
        if self.sandbox_canvas is not None:
            self.sandbox_canvas.set_settings(config.gui)
            self.sandbox_canvas.refresh()

    def set_sandbox_snapshot(
        self,
        snapshot: GraphSnapshot | None,
        *,
        total_uids: int | None = None,
        hidden_stress_uids: int = 0,
    ) -> None:
        if self.sandbox_canvas is not None:
            old = self.sandbox_canvas
            self.stack.removeWidget(old)
            old.close()
            old.deleteLater()
            self.sandbox_canvas = None
        if self._sandbox_placeholder.parent() is None:
            self.stack.addWidget(self._sandbox_placeholder)

        if snapshot is None:
            self.info.setText("M2 sandbox отсутствует")
            return

        services = _FrozenCanvasServices(
            config=self.config,
            graph_inspector=_FrozenGraphInspector(snapshot),
            clock=_NullClock(),
        )
        canvas = GraphCanvasWidget(services, auto_refresh=False)  # type: ignore[arg-type]
        canvas.node_selected.connect(self.sandbox_node_selected.emit)
        canvas.edge_selected.connect(self.sandbox_edge_selected.emit)
        placeholder_index = self.stack.indexOf(self._sandbox_placeholder)
        if placeholder_index >= 0:
            self.stack.removeWidget(self._sandbox_placeholder)
        self.stack.addWidget(canvas)
        self.sandbox_canvas = canvas
        canvas.refresh()
        visible = len(snapshot.nodes) + len(snapshot.links)
        total_text = f" / AH={total_uids} UIDs" if total_uids is not None else ""
        hidden_text = (
            f"; synthetic stress-noise hidden={hidden_stress_uids}"
            if hidden_stress_uids > 0
            else ""
        )
        self.info.setText(
            f"M2 snapshot: visible={visible} ({len(snapshot.nodes)} nodes, {len(snapshot.links)} links)"
            f"{total_text}; Workspace={len(snapshot.workspace_uids)}, tick={snapshot.tick}{hidden_text}"
        )
        if self.current_key == self.M2_KEY:
            self.stack.setCurrentWidget(canvas)

    @property
    def current_key(self) -> str:
        value = self.selector.currentData()
        return str(value or self.LIVE_KEY)

    @property
    def active_canvas(self) -> GraphCanvasWidget:
        if self.current_key == self.M2_KEY and self.sandbox_canvas is not None:
            return self.sandbox_canvas
        return self.live_canvas

    def show_live(self) -> None:
        self._select_key(self.LIVE_KEY)

    def show_sandbox(self) -> bool:
        self._select_key(self.M2_KEY)
        return self.sandbox_canvas is not None

    def clear_proof_highlights(self) -> None:
        self.live_canvas.clear_proof_highlight()
        if self.sandbox_canvas is not None:
            self.sandbox_canvas.clear_proof_highlight()

    def _select_key(self, key: str) -> None:
        for index in range(self.selector.count()):
            if self.selector.itemData(index) == key:
                self.selector.setCurrentIndex(index)
                return

    def _selection_changed(self, _index: int) -> None:
        key = self.current_key
        if key == self.M2_KEY:
            widget = self.sandbox_canvas or self._sandbox_placeholder
            self.stack.setCurrentWidget(widget)
            if self.sandbox_canvas is None:
                self.info.setText("M2 sandbox ещё не загружен")
        else:
            self.stack.setCurrentWidget(self.live_canvas)
            self.info.setText("LIVE AH")
        self.page_changed.emit(key)
