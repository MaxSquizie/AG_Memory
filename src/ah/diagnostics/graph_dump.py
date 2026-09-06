from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, dataclass
import json
from threading import RLock

from ah.config import ContextSettings
from ah.core import AHCore
from ah.ignition import IgnitionEngine
from ah.model import Domain, FunctionSymbol, Group, Hypernode, Link, Ref, RefKind, SemanticEntity, Template
from ah.projection.semantic_projection import SemanticProjector


@dataclass(frozen=True, slots=True)
class NodeDiagnostic:
    uid: str
    kind: str
    domain: str | None
    semantic: str
    creation_sequence: int
    first_excitation_tick: int | None
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
    workspace_semantics: dict[str, str]
    nodes: tuple[NodeDiagnostic, ...]
    links: tuple[LinkDiagnostic, ...]
    structural_edges: tuple[StructuralEdgeDiagnostic, ...]
    pending_incoming: dict[str, float]
    pending_refutations: tuple[str, ...]


class GraphInspector:
    """Read-only graph/runtime snapshot intended for diagnostics and future GUI."""

    def __init__(
        self,
        core: AHCore,
        ignition: IgnitionEngine | None = None,
        *,
        runtime_lock: RLock | None = None,
    ) -> None:
        self.core = core
        self.ignition = ignition
        self.runtime_lock = runtime_lock
        self.semantic = SemanticProjector(core, ContextSettings(include_structural_uids=False))

    def snapshot(self, *, exclude_meta_flag: str | None = None) -> GraphSnapshot:
        lock = self.runtime_lock or nullcontext()
        with lock:
            return self._snapshot_locked(exclude_meta_flag=exclude_meta_flag)

    def _snapshot_locked(self, *, exclude_meta_flag: str | None = None) -> GraphSnapshot:
        workspace = self.ignition.workspace_refs() if self.ignition is not None else ()
        workspace_uids = {ref.uid for ref in workspace}
        hidden_uids: set[str] = set()
        nodes: list[NodeDiagnostic] = []

        for uid in sorted(self.core.store.all_uids()):
            kind = self.core.store.kind_of(uid)
            if kind is RefKind.L:
                continue
            domain = self.core.store.domain_of(uid)
            if exclude_meta_flag and domain is not None:
                try:
                    element_for_filter = self.core.store.get_element_any_domain(uid)
                    if bool(getattr(element_for_filter, "meta", {}).get(exclude_meta_flag)):
                        hidden_uids.add(uid)
                        continue
                except Exception:
                    pass
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
                    creation_sequence=self.core.store.creation_sequence(uid),
                    first_excitation_tick=runtime.first_excitation_tick,
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
            if link.source.uid not in hidden_uids and link.target.uid not in hidden_uids
        )
        structural: list[StructuralEdgeDiagnostic] = []
        for domain in Domain:
            for element in self.core.store.elements(domain):
                if isinstance(element, Template):
                    structural.append(StructuralEdgeDiagnostic(element.uid, element.predicate.uid, "PREDICATE", "T->S"))
                elif isinstance(element, Hypernode):
                    structural.append(StructuralEdgeDiagnostic(element.uid, element.template.uid, "TEMPLATE", "N->T"))
                    for role, ref in element.actants.items():
                        if isinstance(ref, Ref):
                            structural.append(StructuralEdgeDiagnostic(element.uid, ref.uid, role.value, "N->ACTANT"))
                elif isinstance(element, FunctionSymbol):
                    for index, ref in enumerate(element.operands):
                        if isinstance(ref, Ref):
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
        workspace_uids.difference_update(hidden_uids)
        workspace_semantics: dict[str, str] = {}
        for uid in sorted(workspace_uids):
            try:
                workspace_semantics[uid] = self.semantic.active_block(self.core.ref(uid)).semantic
            except Exception:
                workspace_semantics[uid] = self._semantic(uid)

        return GraphSnapshot(
            tick=tick,
            workspace_uids=tuple(sorted(workspace_uids)),
            workspace_semantics=workspace_semantics,
            nodes=tuple(nodes),
            links=links,
            structural_edges=structural_edges,
            pending_incoming=incoming,
            pending_refutations=refutations,
        )

    def active_semantics(self, uids: tuple[str, ...] | list[str]) -> dict[str, str]:
        """Human-readable ACTIVE projection for operator diagnostics only.

        Kept out of the high-frequency canvas snapshot because ACTIVE projection
        may include Pr/text and is more expensive than compact dependency labels.
        """
        lock = self.runtime_lock or nullcontext()
        with lock:
            out: dict[str, str] = {}
            for uid in uids:
                if not self.core.store.has_uid(uid) or self.core.store.kind_of(uid) is RefKind.L:
                    continue
                try:
                    out[uid] = self.semantic.active_block(self.core.ref(uid)).semantic
                except Exception:
                    out[uid] = self._semantic(uid)
            return out

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
        # M2 stress padding deliberately contains tens/hundreds of thousands of
        # semantically empty cold entities. Running the full SemanticProjector for
        # each one makes freezing the test canvas needlessly expensive; the marker
        # is diagnostic-only and has no cognitive semantics.
        try:
            domain = self.core.store.domain_of(uid)
            if domain is not None:
                element = self.core.store.get_element_any_domain(uid)
                if isinstance(element, SemanticEntity) and element.meta.get("m2_stress_noise"):
                    return "M2 cold noise"
        except Exception:
            pass
        ref = self.core.ref(uid)
        try:
            # Minimal projection is sufficient for inspection labels and avoids Pr dumps.
            return self.semantic.dependency_text(ref)
        except Exception:
            return uid
