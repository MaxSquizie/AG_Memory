from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem,
    QGraphicsView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)


@dataclass(frozen=True, slots=True)
class HistoryNode:
    uid: str
    kind: str
    domain: str | None
    semantic: str


@dataclass(frozen=True, slots=True)
class HistoryEdge:
    uid: str | None
    relation: str
    source_uid: str
    target_uid: str


@dataclass(frozen=True, slots=True)
class M1HistorySnapshot:
    sequence: int
    prompt: str
    nodes: tuple[HistoryNode, ...]
    edges: tuple[HistoryEdge, ...]


@dataclass(frozen=True, slots=True)
class M2HistorySnapshot:
    sequence: int
    title: str
    status: str
    depth: int
    goal: str
    trace_uids: tuple[str, ...]
    nodes: tuple[HistoryNode, ...]
    edges: tuple[HistoryEdge, ...]


class SubgraphCanvas(QGraphicsView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#171c24")))
        self.setMinimumHeight(300)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def show_graph(self, nodes: Iterable[HistoryNode], edges: Iterable[HistoryEdge], trace: tuple[str, ...] = ()) -> None:
        self.scene.clear()
        nodes = tuple(nodes)
        edges = tuple(edges)
        if not nodes:
            self.scene.addText("Подграф пуст")
            return
        by_uid = {n.uid: n for n in nodes}
        order = [uid for uid in trace if uid in by_uid]
        order += [n.uid for n in nodes if n.uid not in order]
        cols = max(1, min(4, int(len(order) ** 0.5) + 1))
        w, h, gx, gy = 250.0, 92.0, 70.0, 70.0
        rects: dict[str, tuple[float, float, float, float]] = {}
        for i, uid in enumerate(order):
            n = by_uid[uid]
            col, row = i % cols, i // cols
            x, y = col * (w + gx), row * (h + gy)
            rect = QGraphicsRectItem(x, y, w, h)
            rect.setPen(QPen(QColor("#5c9ee8") if uid not in trace else QColor("#f1be4a"), 2))
            rect.setBrush(QBrush(QColor("#253247")))
            self.scene.addItem(rect)
            text = QGraphicsTextItem()
            text.setDefaultTextColor(QColor("#e9edf3"))
            text.setTextWidth(w - 14)
            domain = n.domain or "—"
            text.setHtml(f"<b>{n.kind}</b> · <b>{domain}</b><br>{_html(n.semantic)}<br><span style='color:#8998aa'>{n.uid}</span>")
            text.setPos(x + 7, y + 5)
            self.scene.addItem(text)
            rects[uid] = (x, y, w, h)

        for e in edges:
            a, b = rects.get(e.source_uid), rects.get(e.target_uid)
            if not a or not b:
                continue
            sx, sy = a[0] + a[2], a[1] + a[3] / 2
            tx, ty = b[0], b[1] + b[3] / 2
            pen = QPen(QColor("#d6a84f") if e.source_uid in trace and e.target_uid in trace else QColor("#718096"), 2)
            self.scene.addLine(sx, sy, tx, ty, pen)
            arrow = QGraphicsPolygonItem(QPolygonF([QPointF(tx, ty), QPointF(tx-10, ty-5), QPointF(tx-10, ty+5)]))
            arrow.setPen(pen); arrow.setBrush(QBrush(pen.color())); self.scene.addItem(arrow)
            label = self.scene.addSimpleText(e.relation)
            label.setBrush(QBrush(pen.color()))
            label.setPos((sx + tx)/2 - 20, (sy + ty)/2 - 20)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


def _html(value: str) -> str:
    import html
    return html.escape(str(value)).replace("\n", "<br>")


class _HistoryPanel(QWidget):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self); root.setContentsMargins(6, 6, 6, 6); root.setSpacing(5)
        self.header = QLabel(title); self.header.setWordWrap(True); root.addWidget(self.header)
        splitter = QSplitter(Qt.Orientation.Horizontal); root.addWidget(splitter, 1)
        self.list = QListWidget(); self.list.setMinimumWidth(250); splitter.addWidget(self.list)
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0,0,0,0); rl.setSpacing(4)
        self.canvas = SubgraphCanvas(); rl.addWidget(self.canvas, 1)
        self.details = QLabel(); self.details.setWordWrap(True); self.details.setMaximumHeight(110); rl.addWidget(self.details)
        splitter.addWidget(right); splitter.setSizes([300, 900])
        self.list.currentItemChanged.connect(self._selection_changed)

    def _selection_changed(self, current, _previous) -> None:
        snap = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.show_snapshot(snap)

    def show_snapshot(self, snapshot) -> None:
        raise NotImplementedError


class M1HistoryPanel(_HistoryPanel):
    def __init__(self, parent=None) -> None:
        self.snapshots: list[M1HistorySnapshot] = []
        super().__init__("M1 — последние 20 формализованных промптов. Исходный текст хранится рядом с подграфом.", parent)

    def add(self, snapshot: M1HistorySnapshot) -> None:
        self.snapshots.append(snapshot)
        del self.snapshots[:-20]
        self.list.clear()
        for snap in reversed(self.snapshots):
            item = QListWidgetItem(f"#{snap.sequence} · {snap.prompt[:90]}")
            item.setToolTip(snap.prompt); item.setData(Qt.ItemDataRole.UserRole, snap); self.list.addItem(item)
        if self.list.count(): self.list.setCurrentRow(0)

    def show_snapshot(self, snapshot) -> None:
        if snapshot is None:
            self.canvas.show_graph((), ()); self.details.setText("Выберите формализованный промпт."); return
        self.canvas.show_graph(snapshot.nodes, snapshot.edges)
        self.details.setText(f"<b>Исходный промпт:</b> {_html(snapshot.prompt)}<br>Узлов: {len(snapshot.nodes)} · связей: {len(snapshot.edges)}")


class M2HistoryPanel(_HistoryPanel):
    def __init__(self, parent=None) -> None:
        self.snapshots: list[M2HistorySnapshot] = []
        super().__init__("M2 — последние 20 UID tracing. Показывается только путь возбуждения/доказательства.", parent)

    def add(self, snapshot: M2HistorySnapshot) -> None:
        self.snapshots.append(snapshot); del self.snapshots[:-20]
        self.list.clear()
        for snap in reversed(self.snapshots):
            item = QListWidgetItem(f"#{snap.sequence} · {snap.status} · d={snap.depth} · {snap.title}")
            item.setData(Qt.ItemDataRole.UserRole, snap); self.list.addItem(item)
        if self.list.count(): self.list.setCurrentRow(0)

    def show_snapshot(self, snapshot) -> None:
        if snapshot is None:
            self.canvas.show_graph((), ()); self.details.setText("Выберите UID trace."); return
        self.canvas.show_graph(snapshot.nodes, snapshot.edges, snapshot.trace_uids)
        self.details.setText(f"<b>Goal:</b> {_html(snapshot.goal)}<br>Статус: {snapshot.status} · depth={snapshot.depth}<br>Trace: {' → '.join(snapshot.trace_uids)}")


class MetricHistoryWidget(QWidget):
    """Two independent audit canvases; bounded to 20 snapshots each."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self); root.setContentsMargins(4,4,4,4); root.setSpacing(4)
        tabs = QTabWidget()
        self.m1 = M1HistoryPanel(); self.m2 = M2HistoryPanel()
        tabs.addTab(self.m1, "M1 · Formalization")
        tabs.addTab(self.m2, "M2 · UID tracing")
        root.addWidget(tabs, 1)
