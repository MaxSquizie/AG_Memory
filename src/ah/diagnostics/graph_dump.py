from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from ah.config import ContextSettings
from ah.core import AHCore
from ah.ignition import IgnitionEngine
from ah.model import Domain, FunctionSymbol, Group, Hypernode, Link, RefKind, SemanticEntity, Template
from ah.projection.semantic_projection import SemanticProjector


@dataclass(frozen=True, slots=True)
class NodeDiagnostic:
    uid: str
    kind: str
    domain: str | None
    semantic: str
    excitation: float | None
    associative_weight: float | None
    output: float | None
    activation_event: bool | None
    decay_age: int | None
    lifecycle_state: str | None
    in_workspace: bool


@dataclass(frozen=True, slots=True)
class LinkDiagnostic:
    uid: str
    relation_id: str
    source_uid: str
    target_uid: str
    weight: float


@dataclass(frozen=True, slots=True)
class StructuralEdgeDiagnostic:
    source_uid: str
    target_uid: str
    relation_id: str
    edge_kind: str


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    tick: int
    workspace_uids: tuple[str, ...]
    nodes: tuple[NodeDiagnostic, ...]
    links: tuple[LinkDiagnostic, ...]
    structural_edges: tuple[StructuralEdgeDiagnostic, ...]
    pending_incoming: dict[str, float]
    pending_refutations: tuple[str, ...]


class GraphInspector:
    """Read-only graph/runtime snapshot intended for diagnostics and future GUI."""

    def __init__(self, core: AHCore, ignition: IgnitionEngine | None = None) -> None:
        self.core = core
        self.ignition = ignition
        self.semantic = SemanticProjector(core, ContextSettings(include_structural_uids=False))

    def snapshot(self) -> GraphSnapshot:
        workspace = self.ignition.workspace_refs() if self.ignition is not None else ()
        workspace_uids = {ref.uid for ref in workspace}
        nodes: list[NodeDiagnostic] = []

        for uid in sorted(self.core.store.all_uids()):
            kind = self.core.store.kind_of(uid)
            if kind is RefKind.L:
                continue
            domain = self.core.store.domain_of(uid)
            runtime = self.core.store.runtime_state(uid)
            semantic = self._semantic(uid)
            lifecycle = None
            associative_weight = None
            if kind is RefKind.N:
                hypernode = self.core.store.get_hypernode(uid)
                associative_weight = hypernode.weight
                lifecycle = str(hypernode.meta.get("lifecycle_state")) if hypernode.meta.get("lifecycle_state") is not None else None
            nodes.append(
                NodeDiagnostic(
                    uid=uid,
                    kind=kind.value,
                    domain=domain.value if domain is not None else None,
                    semantic=semantic,
                    excitation=runtime.excitation,
                    associative_weight=associative_weight,
                    output=runtime.output,
                    activation_event=runtime.activation_event,
                    decay_age=runtime.decay_age,
                    lifecycle_state=lifecycle,
                    in_workspace=uid in workspace_uids,
                )
            )

        links = tuple(
            LinkDiagnostic(link.uid, link.relation_id, link.source.uid, link.target.uid, link.weight)
            for link in sorted(self.core.store.links(), key=lambda x: x.uid)
        )
        structural: list[StructuralEdgeDiagnostic] = []
        for domain in Domain:
            for element in self.core.store.elements(domain):
                if isinstance(element, Template):
                    structural.append(StructuralEdgeDiagnostic(element.uid, element.predicate.uid, "PREDICATE", "T->S"))
                elif isinstance(element, Hypernode):
                    structural.append(StructuralEdgeDiagnostic(element.uid, element.template.uid, "TEMPLATE", "N->T"))
                    for role, ref in element.actants.items():
                        structural.append(StructuralEdgeDiagnostic(element.uid, ref.uid, role.value, "N->ACTANT"))
                elif isinstance(element, FunctionSymbol):
                    for index, ref in enumerate(element.operands):
                        structural.append(StructuralEdgeDiagnostic(element.uid, ref.uid, f"OPERAND:{index}", "G->OPERAND"))
                elif isinstance(element, Group):
                    for index, ref in enumerate(element.members):
                        structural.append(StructuralEdgeDiagnostic(element.uid, ref.uid, f"MEMBER:{index}", "K->MEMBER"))
        structural_edges = tuple(sorted(structural, key=lambda e: (e.source_uid, e.target_uid, e.relation_id)))
        if self.ignition is None:
            tick = 0
            incoming: dict[str, float] = {}
            refutations: tuple[str, ...] = ()
        else:
            snap = self.ignition.export_snapshot(include_pending=True)
            tick = snap.tick_index
            incoming = dict(snap.incoming)
            refutations = snap.pending_refutations
        return GraphSnapshot(
            tick=tick,
            workspace_uids=tuple(sorted(workspace_uids)),
            nodes=tuple(nodes),
            links=links,
            structural_edges=structural_edges,
            pending_incoming=incoming,
            pending_refutations=refutations,
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(asdict(self.snapshot()), ensure_ascii=False, indent=indent, sort_keys=True)

    def to_dot(self) -> str:
        snap = self.snapshot()
        lines = ["digraph AH {", "  rankdir=LR;"]
        for node in snap.nodes:
            label = node.semantic.replace('"', '\\"')
            attrs = [f'label="{node.uid}\\n{label}"']
            if node.in_workspace:
                attrs.append('penwidth="2"')
            lines.append(f'  "{node.uid}" [{", ".join(attrs)}];')
        for link in snap.links:
            rel = link.relation_id.replace('"', '\\"')
            lines.append(
                f'  "{link.source_uid}" -> "{link.target_uid}" '
                f'[label="{rel} w={link.weight:.3f}"];'
            )
        lines.append("}")
        return "\n".join(lines)

    def _semantic(self, uid: str) -> str:
        ref = self.core.ref(uid)
        try:
            # Minimal projection is sufficient for inspection labels and avoids Pr dumps.
            return self.semantic.dependency_text(ref)
        except Exception:
            return uid
