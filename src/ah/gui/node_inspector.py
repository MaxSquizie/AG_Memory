from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ah.model import (
    AbstractSymbol,
    FunctionSymbol,
    Group,
    Hypernode,
    Link,
    SemanticEntity,
    Template,
)

from .graph_state import VisualEdge


class NodeInspectorWidget(QWidget):
    """Read-only, structured inspector for nodes and links.

    The inspector only projects existing AH/Core and runtime state into GUI widgets.
    It never writes canonical state or runtime values.
    """

    def __init__(self, services, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self._raw_payload: dict[str, Any] = {}
        self._title = QLabel("ИНСПЕКТОР")
        self._title.setObjectName("inspectorTitle")
        self._subtitle = QLabel("Выберите узел или связь на 3D-графе")
        self._subtitle.setObjectName("inspectorSubtitle")
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(6, 6, 6, 8)
        self._layout.setSpacing(4)
        self._scroll.setWidget(self._body)

        header = QHBoxLayout()
        header.addWidget(self._title)
        header.addStretch(1)
        self._refresh_button = QPushButton("Обновить")
        self._refresh_button.clicked.connect(self.refresh)
        self._copy_button = QPushButton("Копировать JSON")
        self._copy_button.clicked.connect(self._copy_json)
        header.addWidget(self._refresh_button)
        header.addWidget(self._copy_button)

        root = QVBoxLayout(self)
        root.setContentsMargins(5, 5, 5, 5)
        root.setSpacing(3)
        root.addLayout(header)
        root.addWidget(self._subtitle)
        root.addWidget(self._scroll, 1)
        self._clear_body()

        self._selected_uid: str | None = None
        self._selected_edge: VisualEdge | None = None
        self._snapshot = None

    def set_node(self, uid: str | None, snapshot=None) -> None:
        self._selected_uid = uid or None
        self._selected_edge = None
        self._snapshot = snapshot
        self.refresh()

    def set_edge(self, edge: VisualEdge | None, snapshot=None) -> None:
        self._selected_edge = edge
        self._selected_uid = None
        self._snapshot = snapshot
        self.refresh()

    def set_raw_payload(self, payload: dict[str, Any]) -> None:
        self._selected_uid = None
        self._selected_edge = None
        self._snapshot = None
        self._raw_payload = dict(payload)
        self._subtitle.setText(str(payload.get("canvas", "Raw diagnostic payload")))
        self._set_json_body(self._raw_payload)

    def clear_selection(self) -> None:
        self._selected_uid = None
        self._selected_edge = None
        self._raw_payload = {}
        self._snapshot = None
        self._subtitle.setText("Выберите узел или связь на 3D-графе")
        self._clear_body()

    def refresh(self) -> None:
        if self._selected_uid:
            self._refresh_node(self._selected_uid)
            return
        if self._selected_edge:
            self._refresh_edge(self._selected_edge)
            return
        self.clear_selection()

    def _refresh_node(self, uid: str) -> None:
        snap = self._snapshot if self._snapshot is not None else self.services.graph_inspector.snapshot()
        node = next((item for item in snap.nodes if item.uid == uid), None)
        if node is None:
            self._raw_payload = {"selection": "node", "uid": uid, "status": "GC / not found"}
            self._subtitle.setText(f"Узел {uid} больше не существует")
            self._set_json_body(self._raw_payload)
            return

        store = self.services.core.store
        self._subtitle.setText(f"{node.kind} · {node.uid}")
        runtime = store.runtime_state(uid)
        element = None
        if node.kind == "S":
            element = store.get_symbol(uid)
        elif node.kind != "L":
            try:
                element = store.get_element_any_domain(uid)
            except Exception:
                element = None

        self._raw_payload = {"selection": "node", **asdict(node)}
        self._raw_payload["pending_incoming"] = snap.pending_incoming.get(uid, 0.0)
        self._raw_payload["runtime"] = {
            "excitation": runtime.excitation,
            "output": runtime.output,
            "activation_function_id": runtime.activation_function_id,
            "activation_event": runtime.activation_event,
            "decay_age": runtime.decay_age,
            "first_excitation_tick": runtime.first_excitation_tick,
            "last_activation_tick": runtime.last_activation_tick,
            "last_output_tick": runtime.last_output_tick,
        }
        if isinstance(element, AbstractSymbol):
            self._raw_payload["forms"] = sorted(element.forms)
        elif isinstance(element, SemanticEntity):
            self._raw_payload["properties"] = self._plain_properties(element.properties)
            self._raw_payload["meta"] = self._plain_mapping(element.meta)
        elif isinstance(element, Template):
            self._raw_payload["predicate"] = asdict(element.predicate)
            self._raw_payload["roles"] = [role.value for role in element.roles]
        elif isinstance(element, Hypernode):
            self._raw_payload["template"] = asdict(element.template)
            self._raw_payload["actants"] = {
                role.value: asdict(ref) for role, ref in element.actants.items()
            }
            self._raw_payload["properties"] = self._plain_properties(element.properties)
            self._raw_payload["meta"] = self._plain_mapping(element.meta)
        elif isinstance(element, FunctionSymbol):
            self._raw_payload["function_id"] = element.function_id
            self._raw_payload["operands"] = [asdict(ref) for ref in element.operands]
        elif isinstance(element, Group):
            self._raw_payload["members"] = [asdict(ref) for ref in element.members]
            self._raw_payload["properties"] = self._plain_properties(element.properties)
            self._raw_payload["meta"] = self._plain_mapping(element.meta)

        self._clear_body()
        self._add_card("Общее", [
            ("UID", uid),
            ("Тип", node.kind),
            ("Домен", node.domain or "—"),
            ("Semantic", node.semantic or "—"),
        ])
        self._add_card("Runtime", [
            ("x — возбуждение", self._fmt(node.excitation)),
            ("output", self._fmt(node.output)),
            ("Activation event", self._fmt(node.activation_event)),
            ("Decay age", self._fmt(node.decay_age)),
            ("Last activation tick", self._fmt(runtime.last_activation_tick)),
            ("Workspace", "YES" if node.in_workspace else "NO"),
            ("Pending incoming", self._fmt(self._raw_payload["pending_incoming"])),
        ])

        if node.kind == "S" and isinstance(element, AbstractSymbol):
            self._add_text_card("Forms", "\n".join(sorted(element.forms)))
        elif node.kind == "m" and isinstance(element, SemanticEntity):
            self._add_entity_card(element)
        elif node.kind == "T" and isinstance(element, Template):
            self._add_card("Template", [
                ("Predicate S", f"{element.predicate.uid} ({element.predicate.kind.value})"),
                ("Roles", ", ".join(role.value for role in element.roles) or "—"),
            ])
        elif node.kind == "N" and isinstance(element, Hypernode):
            self._add_card("Hypernode", [
                ("Template T", element.template.uid),
                ("N.w", self._fmt(element.weight)),
                ("Actants", self._format_ref_map(element.actants)),
                ("Lifecycle", str(element.meta.get("lifecycle_state", "—"))),
                ("Occurrence count", str(element.meta.get("occurrence_count", "—"))),
            ])
            self._add_mapping_card("Pr", element.properties)
            self._add_mapping_card("Mt", element.meta)
        elif node.kind == "g" and isinstance(element, FunctionSymbol):
            self._add_card("Function", [
                ("Function ID", element.function_id),
                ("Operands", self._format_refs(element.operands)),
            ])
        elif node.kind == "k" and isinstance(element, Group):
            self._add_card("Group", [
                ("Members", self._format_refs(element.members)),
            ])
            self._add_mapping_card("Pr", element.properties)
            self._add_mapping_card("Mt", element.meta)
        else:
            self._add_card("Details", [("Data", "Нет специальной схемы для этого типа")])

    def _refresh_edge(self, edge: VisualEdge) -> None:
        self._subtitle.setText(f"{edge.edge_kind} · {edge.source_uid} → {edge.target_uid}")
        snap = self._snapshot if self._snapshot is not None else self.services.graph_inspector.snapshot()
        source_state = self.services.core.store.runtime_state(edge.source_uid)
        target_state = self.services.core.store.runtime_state(edge.target_uid)
        payload: dict[str, Any] = {
            "selection": "canonical_link" if edge.canonical_link else "structural_edge",
            "key": edge.key,
            "uid": edge.uid,
            "relation_id": edge.relation_id,
            "source_uid": edge.source_uid,
            "target_uid": edge.target_uid,
            "edge_kind": edge.edge_kind,
            "runtime_activity": {
                "source_x": source_state.excitation,
                "source_active": source_state.activation_event,
                "target_x": target_state.excitation,
                "target_active": target_state.activation_event,
            },
        }
        if edge.canonical_link and edge.uid:
            link = next((item for item in snap.links if item.uid == edge.uid), None)
            if link is not None:
                payload["weight"] = link.weight
        self._raw_payload = payload

        self._clear_body()
        title = "Canonical L" if edge.canonical_link else "Structural edge"
        rows = [
            ("UID", edge.uid or "—"),
            ("Relation ID", edge.relation_id or "—"),
            ("Source", edge.source_uid),
            ("Target", edge.target_uid),
            ("Edge type", edge.edge_kind),
        ]
        if edge.canonical_link:
            rows.append(("w", self._fmt(payload.get("weight"))))
        self._add_card(title, rows)
        self._add_card("Runtime activity", [
            ("Source x", self._fmt(source_state.excitation)),
            ("Source active", self._fmt(source_state.activation_event)),
            ("Target x", self._fmt(target_state.excitation)),
            ("Target active", self._fmt(target_state.activation_event)),
        ])

    def _add_entity_card(self, element: SemanticEntity) -> None:
        props = dict(element.properties)
        self._add_card("m — Semantic Entity", [
            ("Name", self._fmt(props.get("name").value if props.get("name") else "—")),
            ("Aliases", self._fmt(props.get("aliases").value if props.get("aliases") else "—")),
        ])
        self._add_mapping_card("Pr", element.properties)
        self._add_mapping_card("Mt", element.meta)

    def _add_mapping_card(self, title: str, mapping) -> None:
        if not mapping:
            self._add_card(title, [("—", "нет данных")])
            return
        rows = [(name, self._fmt(getattr(value, "value", value))) for name, value in mapping.items()]
        self._add_card(title, rows)

    def _add_card(self, title: str, rows: list[tuple[str, str]]) -> None:
        frame = QFrame()
        frame.setObjectName("inspectorCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(7, 6, 7, 6)
        heading = QLabel(title.upper())
        heading.setObjectName("inspectorSectionTitle")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(2)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key, value in rows:
            label = QLabel(str(key))
            label.setObjectName("inspectorKey")
            label.setMinimumWidth(100)
            value_label = QLabel(str(value))
            value_label.setObjectName("inspectorValue")
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_label.setWordWrap(True)
            form.addRow(label, value_label)
        layout.addLayout(form)
        self._layout.addWidget(frame)

    def _add_text_card(self, title: str, text: str) -> None:
        frame = QFrame()
        frame.setObjectName("inspectorCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(7, 6, 7, 6)
        heading = QLabel(title.upper())
        heading.setObjectName("inspectorSectionTitle")
        layout.addWidget(heading)
        body = QPlainTextEdit(text)
        body.setReadOnly(True)
        body.setMaximumHeight(130)
        layout.addWidget(body)
        self._layout.addWidget(frame)

    def _set_json_body(self, payload: dict[str, Any]) -> None:
        self._clear_body()
        self._add_text_card("Raw JSON", json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    def _clear_body(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


    def _copy_json(self) -> None:
        if self._raw_payload:
            QGuiApplication.clipboard().setText(
                json.dumps(self._raw_payload, ensure_ascii=False, indent=2, default=str)
            )

    @staticmethod
    def _plain_properties(mapping) -> dict[str, Any]:
        return {
            name: getattr(value, "value", value)
            for name, value in mapping.items()
        }

    @staticmethod
    def _plain_mapping(mapping) -> dict[str, Any]:
        return dict(mapping)

    @staticmethod
    def _fmt(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, (list, tuple, set, frozenset)):
            return ", ".join(str(item) for item in value) if value else "—"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    @staticmethod
    def _format_refs(refs) -> str:
        return ", ".join(f"{ref.uid} ({ref.kind.value})" for ref in refs) or "—"

    @staticmethod
    def _format_ref_map(refs) -> str:
        if not refs:
            return "—"
        return "; ".join(f"{role.value}: {ref.uid}" for role, ref in refs.items())
