from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDockWidget, QToolBar

from ah.diagnostics import ProofSnapshotBuilder

from .semantic_test_window import MainWindow as _BaseMainWindow
from .metric_history import (
    HistoryEdge,
    HistoryNode,
    M1HistorySnapshot,
    M2HistorySnapshot,
    MetricHistoryWidget,
)


class MainWindow(_BaseMainWindow):
    """Current main GUI plus the uploaded GUI's independent M1/M2 tracing dock.

    The base window remains authoritative for current document continuation,
    acceptance controls, M1-M3 metrics and runtime contracts. This subclass adds
    only operator-facing tracing state and never mutates canonical AH.
    """

    def __init__(self, services, config_path: str | Path) -> None:
        self._metric_history_sequence = 0
        self._history_visibility_before_full_canvas = False
        super().__init__(services, config_path)
        self._build_metric_history_dock()
        self._install_metric_history_action()

    def _install_metric_history_action(self) -> None:
        bar = self.findChild(QToolBar)
        if bar is None:
            return
        self.action_metric_history = QAction("M1/M2 tracing", self)
        self.action_metric_history.setToolTip(
            "Последние 20 формализованных промптов и последние 20 UID traces"
        )
        self.action_metric_history.triggered.connect(self._show_metric_history)
        bar.addAction(self.action_metric_history)

    def _build_metric_history_dock(self) -> None:
        dock = QDockWidget("M1 / M2 tracing", self)
        self.metric_history_dock = dock
        self.metric_history = MetricHistoryWidget(self)
        dock.setWidget(self.metric_history)
        dock.setMinimumWidth(720)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.hide()

    def _show_metric_history(self) -> None:
        if self._workspace_mode != "graph":
            self._set_workspace_mode("graph")
        self.removeDockWidget(self.metric_history_dock)
        self.metric_history_dock.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.metric_history_dock)
        self.metric_history_dock.show()
        self.metric_history_dock.raise_()
        width = max(720, min(980, self.width() // 2))
        self.metric_history_dock.setMinimumWidth(680)
        self.metric_history_dock.setMaximumWidth(width)
        self.resizeDocks(
            [self.metric_history_dock], [width], Qt.Orientation.Horizontal
        )

    def _set_workspace_mode(self, mode: str) -> None:
        super()._set_workspace_mode(mode)
        if hasattr(self, "metric_history_dock") and mode != "graph":
            self.metric_history_dock.hide()

    @Slot(bool)
    def _toggle_full_canvas(self, enabled: bool) -> None:
        if hasattr(self, "metric_history_dock") and enabled:
            self._history_visibility_before_full_canvas = (
                self.metric_history_dock.isVisible()
            )
            self.metric_history_dock.hide()
        super()._toggle_full_canvas(enabled)
        if (
            hasattr(self, "metric_history_dock")
            and not enabled
            and self._history_visibility_before_full_canvas
        ):
            self.metric_history_dock.show()
            self.metric_history_dock.raise_()
            self._history_visibility_before_full_canvas = False

    def _next_history_sequence(self) -> int:
        self._metric_history_sequence += 1
        return self._metric_history_sequence

    @staticmethod
    def _history_record_semantic(item: dict) -> str:
        props = item.get("properties") or {}
        if isinstance(props, dict):
            names = []
            for key, value in props.items():
                if isinstance(value, dict):
                    value = value.get("value", value.get("normalized", value))
                names.append(f"{key}={value}")
            if names:
                return "; ".join(names)
        predicate = item.get("predicate")
        if predicate:
            return str(predicate)
        return f"{item.get('kind', '?')}:{item.get('uid', '')}"

    def _record_m1_history(self, prompt: str, commit) -> None:
        refs: dict[str, HistoryNode] = {}
        edges: list[HistoryEdge] = []

        def add_ref(ref) -> None:
            if ref is None:
                return
            kind = getattr(ref, "kind", None)
            kind_value = getattr(kind, "value", str(kind or "?"))
            if kind_value == "L":
                return
            uid = str(ref.uid)
            if uid in refs:
                return
            domain = self.services.core.store.domain_of(uid)
            try:
                semantic = self.services.graph_inspector.semantic.dependency_text(ref)
            except Exception:
                semantic = f"{kind_value}:{uid}"
            refs[uid] = HistoryNode(
                uid,
                kind_value,
                None if domain is None else domain.value,
                semantic,
            )

        for assertion in getattr(commit, "assertions", ()):
            add_ref(assertion.ref)
            for relation in getattr(assertion, "nominal_relations", ()):
                add_ref(relation.source)
                add_ref(relation.target)
                edges.append(
                    HistoryEdge(
                        relation.ref.uid,
                        relation.relation_id,
                        relation.source.uid,
                        relation.target.uid,
                    )
                )
        for relation in getattr(commit, "relations", ()):
            add_ref(relation.source)
            add_ref(relation.target)
            edges.append(
                HistoryEdge(
                    relation.ref.uid,
                    relation.relation_id,
                    relation.source.uid,
                    relation.target.uid,
                )
            )
        for conditional in getattr(commit, "conditionals", ()):
            add_ref(conditional.antecedent)
            add_ref(conditional.consequent)
            edges.append(
                HistoryEdge(
                    conditional.ref.uid,
                    "CONDITIONAL",
                    conditional.antecedent.uid,
                    conditional.consequent.uid,
                )
            )
        add_ref(getattr(commit, "experience_ref", None))
        self.metric_history.m1.add(
            M1HistorySnapshot(
                self._next_history_sequence(),
                prompt,
                tuple(refs.values()),
                tuple(edges),
            )
        )

    def _record_m1_acceptance_history(self, output_dir: Path, source_label: str) -> None:
        for path in sorted(output_dir.glob("turn_*.json"), key=lambda item: item.name):
            try:
                import json

                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            prompt = str(record.get("input") or "").strip()
            if not prompt:
                continue
            refs: dict[str, HistoryNode] = {}
            edges: list[HistoryEdge] = []
            diff = record.get("ah_diff") or {}
            for uid, item in (diff.get("added") or {}).items():
                if not isinstance(item, dict) or item.get("kind") == "L":
                    continue
                refs[str(uid)] = HistoryNode(
                    str(uid),
                    str(item.get("kind") or "?"),
                    item.get("domain"),
                    self._history_record_semantic(item),
                )
            for uid, item in (diff.get("added") or {}).items():
                if not isinstance(item, dict) or item.get("kind") != "L":
                    continue
                source = item.get("source") or {}
                target = item.get("target") or {}
                source_uid = str(source.get("uid") or "")
                target_uid = str(target.get("uid") or "")
                if source_uid and target_uid:
                    edges.append(
                        HistoryEdge(
                            str(uid),
                            str(item.get("relation_id") or "LINK"),
                            source_uid,
                            target_uid,
                        )
                    )
            self.metric_history.m1.add(
                M1HistorySnapshot(
                    self._next_history_sequence(),
                    f"[{source_label}] {prompt}",
                    tuple(refs.values()),
                    tuple(edges),
                )
            )

    def _record_m2_history(self, proof) -> None:
        nodes = tuple(
            HistoryNode(node.uid, node.kind, node.domain, node.semantic)
            for node in proof.nodes
        )
        edges = tuple(
            HistoryEdge(edge.uid, edge.relation, edge.source_uid, edge.target_uid)
            for edge in proof.edges
        )
        self.metric_history.m2.add(
            M2HistorySnapshot(
                self._next_history_sequence(),
                proof.title,
                proof.status,
                proof.logical_depth,
                proof.goal_text,
                proof.trace_uids,
                nodes,
                edges,
            )
        )

    @Slot(object)
    def _document_ingest_finished(self, result) -> None:
        super()._document_ingest_finished(result)
        try:
            self._record_m1_history(
                result.title or result.source_ref,
                result.integration,
            )
        except Exception:
            pass

    @Slot(object)
    def _acceptance_finished(self, result) -> None:
        label = self._active_acceptance_label
        super()._acceptance_finished(result)
        if label.startswith("M1"):
            try:
                self._record_m1_acceptance_history(Path(result.output_dir), label)
            except Exception as exc:
                self.statusBar().showMessage(
                    f"M1 tracing acceptance: {type(exc).__name__}", 2500
                )

    @Slot(object)
    def _m2_acceptance_finished(self, result) -> None:
        super()._m2_acceptance_finished(result)
        for case in result.cases:
            if case.proof is None:
                continue
            try:
                self._record_m2_history(case.proof)
            except Exception:
                continue

    def _turn_finished(self, result) -> None:
        super()._turn_finished(result)
        try:
            self._record_m1_history(result.user_text, result.integration)
        except Exception as exc:
            self.statusBar().showMessage(f"M1 tracing: {type(exc).__name__}", 2500)

        builder = ProofSnapshotBuilder(self.services.core)
        for index, query in enumerate(result.queries, 1):
            try:
                if query.outcome is None:
                    proof = builder.build_unresolved(
                        chain_id=f"trace:turn:{self._turn_sequence}:query:{index}",
                        source="LIVE",
                        title=f"Turn {self._turn_sequence} · Query {index}",
                        diagnostics=query.diagnostics,
                    )
                else:
                    proof = builder.build(
                        query.outcome,
                        chain_id=f"trace:turn:{self._turn_sequence}:query:{index}",
                        source="LIVE",
                        title=f"Turn {self._turn_sequence} · Query {index}",
                    )
                self._record_m2_history(proof)
            except Exception:
                continue
