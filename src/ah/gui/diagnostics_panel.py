from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)


class DiagnosticsPanel(QWidget):
    """Runtime diagnostics, plasticity history and persistence/export controls."""

    save_requested = Signal()
    reload_requested = Signal()

    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self._last_links: dict[str, float] = {}
        self._last_hypernodes: dict[str, float] = {}
        self._plasticity_rows: list[tuple[int, str, float, float, float, str]] = []
        self._event_rows: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        title = QLabel("DIAGNOSTICS / PERSISTENCE")
        title.setObjectName("runtimeSectionTitle")
        root.addWidget(title)

        persistence_frame = QFrame()
        persistence_frame.setObjectName("runtimeCard")
        pgrid = QGridLayout(persistence_frame)
        pgrid.setContentsMargins(12, 10, 12, 10)
        self.persistence_labels: dict[str, QLabel] = {}
        for row, (name, key) in enumerate((
            ("File", "file"),
            ("Schema", "schema"),
            ("Status", "status"),
            ("Last save", "last_save"),
        )):
            pgrid.addWidget(QLabel(name), row, 0)
            value = QLabel("—")
            value.setWordWrap(True)
            self.persistence_labels[key] = value
            pgrid.addWidget(value, row, 1)
        root.addWidget(persistence_frame)

        controls = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_requested.emit)
        self.reload_button = QPushButton("Reload Memory")
        self.reload_button.clicked.connect(self.reload_requested.emit)
        controls.addWidget(self.reload_button)
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.save_button)
        controls.addWidget(self.refresh_button)
        root.addLayout(controls)

        export_row = QHBoxLayout()
        for label, kind in (
            ("Graph JSON", "graph_json"),
            ("Runtime JSON", "runtime_json"),
            ("DOT", "dot"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, k=kind: self._export(k))
            export_row.addWidget(button)
        root.addLayout(export_row)

        plasticity_title = QLabel("PLASTICITY DIAGNOSTICS")
        plasticity_title.setObjectName("runtimeSectionTitle")
        root.addWidget(plasticity_title)
        self.plasticity_table = QTableWidget(0, 6)
        self.plasticity_table.setHorizontalHeaderLabels(("Tick", "UID", "Old w", "New w", "Δ", "Reason"))
        self.plasticity_table.setMinimumHeight(180)
        self.plasticity_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.plasticity_table)

        events_title = QLabel("LIFECYCLE / GC EVENTS")
        events_title.setObjectName("runtimeSectionTitle")
        root.addWidget(events_title)
        self.events_view = QPlainTextEdit()
        self.events_view.setReadOnly(True)
        self.events_view.setMinimumHeight(130)
        self.events_view.setPlaceholderText("После tick здесь появятся lifecycle / GC события.")
        root.addWidget(self.events_view)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        root.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        path = Path(self.services.config.paths.persistence_file)
        self.persistence_labels["file"].setText(str(path))
        schema = "—"
        status = "NOT FOUND"
        last_save = "—"
        if path.is_file():
            status = "SAVED"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                schema = str(payload.get("schema_version", "—"))
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                last_save = mtime.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as exc:
                status = f"INVALID: {type(exc).__name__}"
        self.persistence_labels["schema"].setText(schema)
        self.persistence_labels["status"].setText(status)
        self.persistence_labels["last_save"].setText(last_save)
        self._refresh_plasticity()

    def record_tick(self, result: Any) -> None:
        tick = int(result.tick)
        lifecycle = result.lifecycle
        if lifecycle is not None:
            for update in lifecycle.updates:
                self._event_rows.append(
                    f"tick {tick}: lifecycle {update.uid}: {update.before or '—'} → {update.after}"
                )
            for uid in lifecycle.expired_candidates:
                self._event_rows.append(f"tick {tick}: lifecycle expired candidate {uid}")
        gc = result.gc
        if gc is not None:
            for uid in gc.deleted:
                self._event_rows.append(f"tick {tick}: GC deleted {uid}")
            for uid in gc.protected:
                self._event_rows.append(f"tick {tick}: GC protected {uid}")
            for uid in gc.orphan_deleted:
                self._event_rows.append(f"tick {tick}: GC orphan deleted {uid}")
        self._event_rows = self._event_rows[-100:]
        self.events_view.setPlainText("\n".join(self._event_rows) if self._event_rows else "Нет lifecycle / GC событий.")
        self.refresh()

    def _refresh_plasticity(self) -> None:
        snap = self.services.graph_inspector.snapshot()
        current_links = {item.uid: float(item.weight) for item in snap.links}
        for uid, new in current_links.items():
            old = self._last_links.get(uid)
            if old is None or abs(new - old) <= 1e-12:
                continue
            delta = new - old
            reason = "Hebbian potentiation" if delta > 0 else "associative depression"
            self._plasticity_rows.append((snap.tick, uid, old, new, delta, reason))
        self._last_links = current_links

        current_n: dict[str, float] = {}
        for node in snap.nodes:
            if node.kind == "N" and node.associative_weight is not None:
                current_n[node.uid] = float(node.associative_weight)
        for uid, new in current_n.items():
            old = self._last_hypernodes.get(uid)
            if old is None or abs(new - old) <= 1e-12:
                continue
            delta = new - old
            reason = "confirmation" if delta > 0 else "refutation"
            self._plasticity_rows.append((snap.tick, uid, old, new, delta, reason))
        self._last_hypernodes = current_n
        self._plasticity_rows = self._plasticity_rows[-100:]

        self.plasticity_table.setRowCount(len(self._plasticity_rows))
        for row, values in enumerate(self._plasticity_rows):
            for col, value in enumerate(values):
                text = f"{value:.4f}" if isinstance(value, float) else str(value)
                self.plasticity_table.setItem(row, col, QTableWidgetItem(text))
        self.summary.setText(
            f"Plasticity events: {len(self._plasticity_rows)}  •  "
            f"Lifecycle/GC events: {len(self._event_rows)}"
        )

    def _export(self, kind: str) -> None:
        if kind == "graph_json":
            content = self.services.graph_inspector.to_json()
            default_name = "graph.json"
        elif kind == "dot":
            content = self.services.graph_inspector.to_dot()
            default_name = "graph.dot"
        else:
            snap = self.services.ignition.export_snapshot(include_pending=True)
            content = json.dumps(
                {
                    "tick_index": snap.tick_index,
                    "incoming": snap.incoming,
                    "seed_reasons": snap.seed_reasons,
                    "pending_refutations": list(snap.pending_refutations),
                    "pacemaker": {
                        "phase": snap.pacemaker.phase,
                        "cursor": snap.pacemaker.cursor,
                        "pulse_count": snap.pacemaker.pulse_count,
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            default_name = "runtime.json"

        path, _ = QFileDialog.getSaveFileName(self, "Экспорт", default_name)
        if not path:
            return
        Path(path).write_text(content, encoding="utf-8")
        self.summary.setText(f"Экспортировано: {path}")
