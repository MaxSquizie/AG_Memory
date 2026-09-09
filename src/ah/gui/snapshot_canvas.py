from __future__ import annotations

import html

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
)

from ah.diagnostics import GraphSnapshot


_DOMAIN_COLORS = {
    "P": QColor(48, 95, 138),
    "C": QColor(75, 89, 142),
    "H": QColor(113, 75, 135),
}


class SnapshotCanvasView(QGraphicsView):
    """Small read-only canvas for one frozen prompt-local AH subgraph."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(24, 29, 38)))

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def set_snapshot(self, snapshot: GraphSnapshot | None) -> None:
        self._scene.clear()
        if snapshot is None or not snapshot.nodes:
            placeholder = self._scene.addSimpleText("Выберите формализованный промпт")
            placeholder.setBrush(QBrush(QColor(190, 198, 211)))
            return

        by_domain: dict[str, list] = {}
        for node in sorted(snapshot.nodes, key=lambda item: item.creation_sequence):
            by_domain.setdefault(node.domain or "—", []).append(node)
        domains = sorted(by_domain, key=lambda value: ({"P": 0, "C": 1, "H": 2}.get(value, 3), value))

        width = 250.0
        height = 92.0
        x_gap = 105.0
        y_gap = 42.0
        rects: dict[str, tuple[float, float, float, float]] = {}
        for column, domain in enumerate(domains):
            x = 30.0 + column * (width + x_gap)
            heading = self._scene.addSimpleText(f"Домен {domain}")
            heading.setBrush(QBrush(QColor(224, 230, 240)))
            heading.setPos(x, 12)
            for row, node in enumerate(by_domain[domain]):
                y = 48.0 + row * (height + y_gap)
                rect = QGraphicsRectItem(x, y, width, height)
                color = _DOMAIN_COLORS.get(domain, QColor(66, 75, 91))
                rect.setBrush(QBrush(color))
                rect.setPen(QPen(QColor(126, 196, 255), 2.0))
                self._scene.addItem(rect)
                label = QGraphicsTextItem()
                label.setDefaultTextColor(QColor(240, 244, 250))
                label.setTextWidth(width - 20)
                label.setHtml(
                    f"<b>{html.escape(node.kind)} · {html.escape(node.uid)}</b><br>"
                    f"<span style='color:#d5deea'>{html.escape(node.semantic)}</span>"
                )
                label.setPos(x + 10, y + 7)
                self._scene.addItem(label)
                rects[node.uid] = (x, y, width, height)

        edges = [
            (edge.source_uid, edge.target_uid, edge.relation_id, QColor(106, 189, 255))
            for edge in snapshot.structural_edges
        ] + [
            (edge.source_uid, edge.target_uid, edge.relation_id, QColor(244, 193, 77))
            for edge in snapshot.links
        ]
        for source_uid, target_uid, relation, color in edges:
            source = rects.get(source_uid)
            target = rects.get(target_uid)
            if source is None or target is None:
                continue
            sx = source[0] + source[2] / 2
            sy = source[1] + source[3] / 2
            tx = target[0] + target[2] / 2
            ty = target[1] + target[3] / 2
            if tx >= sx:
                sx = source[0] + source[2]
                tx = target[0]
            else:
                sx = source[0]
                tx = target[0] + target[2]
            pen = QPen(color, 1.8)
            line = self._scene.addLine(sx, sy, tx, ty, pen)
            line.setZValue(-2)
            direction = 1 if tx >= sx else -1
            arrow = QPolygonF(
                [
                    QPointF(tx, ty),
                    QPointF(tx - direction * 10, ty - 5),
                    QPointF(tx - direction * 10, ty + 5),
                ]
            )
            arrow_item = QGraphicsPolygonItem(arrow)
            arrow_item.setBrush(QBrush(color))
            arrow_item.setPen(pen)
            arrow_item.setZValue(-1)
            self._scene.addItem(arrow_item)
            edge_label = QGraphicsSimpleTextItem(relation)
            edge_label.setBrush(QBrush(color.lighter(125)))
            edge_label.setPos((sx + tx) / 2, (sy + ty) / 2 - 18)
            self._scene.addItem(edge_label)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-30, -30, 30, 30))
        self.fit_snapshot()

    def fit_snapshot(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if not rect.isNull():
            self.fitInView(rect.adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)
