from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from threading import RLock

from ah.config import ContextSettings
from ah.core import AHCore
from ah.ignition import IgnitionEngine
from ah.integration.contracts import IntegrationCommit
from ah.model import FunctionSymbol, Group, Hypernode, Ref, RefKind, Template
from ah.projection.semantic_projection import SemanticProjector

from .graph_dump import (
    GraphSnapshot,
    LinkDiagnostic,
    NodeDiagnostic,
    StructuralEdgeDiagnostic,
)


@dataclass(frozen=True, slots=True)
class FormalizationTraceSnapshot:
    """Frozen M1 provenance for one source prompt and its canonical subgraph."""

    trace_id: str
    source: str
    title: str
    source_text: str
    status: str
    graph: GraphSnapshot
    diagnostics: tuple[str, ...] = ()


class FormalizationTraceBuilder:
    """Build a prompt-local graph without enumerating the complete AH.

    Traversal starts only from refs named by the IntegrationCommit and follows
    canonical structural dependencies. Canonical L edges are included when they
    were returned by the commit or both endpoints are already inside the bounded
    subgraph. The snapshot is diagnostic-only and never writes AH.
    """

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
        self.semantic = SemanticProjector(
            core,
            ContextSettings(include_structural_uids=False),
        )

    def build(
        self,
        commit: IntegrationCommit,
        *,
        trace_id: str,
        source: str,
        title: str,
        source_text: str,
        diagnostics: tuple[str, ...] = (),
    ) -> FormalizationTraceSnapshot:
        lock = self.runtime_lock or nullcontext()
        with lock:
            graph = self._build_graph(commit)
        status = "CLARIFICATION_REQUIRED" if commit.clarification_required else "FORMALIZED"
        return FormalizationTraceSnapshot(
            trace_id=trace_id,
            source=source,
            title=title,
            source_text=source_text,
            status=status,
            graph=graph,
            diagnostics=tuple(str(item) for item in diagnostics),
        )

    def _build_graph(self, commit: IntegrationCommit) -> GraphSnapshot:
        queue: list[Ref] = []
        explicit_links: set[str] = set()

        def seed(ref: Ref | None) -> None:
            if ref is None or not self.core.store.has_uid(ref.uid):
                return
            if ref.kind is RefKind.L:
                explicit_links.add(ref.uid)
                try:
                    link = self.core.store.get_link(ref.uid)
                except KeyError:
                    return
                queue.extend((link.source, link.target))
            else:
                queue.append(ref)

        seed(commit.experience_ref)
        for assertion in commit.assertions:
            seed(assertion.ref)
            for relation in assertion.nominal_relations:
                seed(relation.ref)
        for request in commit.activation_seeds:
            seed(request.ref)
        for request in commit.refutations:
            seed(request.target)
        for relation in commit.relations:
            seed(relation.ref)
        for conditional in commit.conditionals:
            seed(conditional.ref)
            seed(conditional.antecedent)
            seed(conditional.consequent)
            for ref in conditional.member_refs:
                seed(ref)
        for existential in commit.existentials:
            seed(existential.ref)
            for ref in existential.member_refs:
                seed(ref)
        for conflict in commit.conflicts:
            seed(conflict.ref)
            for ref in conflict.members:
                seed(ref)
        for clarification in commit.clarifications:
            seed(clarification.ambiguous_ref)
            for option in clarification.options:
                seed(option.ref)

        included: dict[str, Ref] = {}
        structural: dict[tuple[str, str, str, str], StructuralEdgeDiagnostic] = {}

        def dependency(source_ref: Ref, target_ref: Ref, relation: str, kind: str) -> None:
            if not self.core.store.has_uid(target_ref.uid):
                return
            queue.append(target_ref)
            key = (source_ref.uid, target_ref.uid, relation, kind)
            structural[key] = StructuralEdgeDiagnostic(
                source_ref.uid,
                target_ref.uid,
                relation,
                kind,
            )

        cursor = 0
        while cursor < len(queue):
            ref = queue[cursor]
            cursor += 1
            if ref.uid in included or ref.kind is RefKind.L:
                continue
            if not self.core.store.has_uid(ref.uid):
                continue
            included[ref.uid] = ref
            if ref.kind is RefKind.S:
                continue
            obj = self.core.store.get_element_any_domain(ref.uid)
            if isinstance(obj, Template):
                dependency(ref, obj.predicate, "PREDICATE", "T->S")
            elif isinstance(obj, Hypernode):
                dependency(ref, obj.template, "TEMPLATE", "N->T")
                for role, value in obj.actants.items():
                    if isinstance(value, Ref):
                        dependency(ref, value, role.value, "N->ACTANT")
            elif isinstance(obj, FunctionSymbol):
                for index, value in enumerate(obj.operands):
                    if isinstance(value, Ref):
                        dependency(ref, value, f"OPERAND:{index}", "G->OPERAND")
            elif isinstance(obj, Group):
                for index, value in enumerate(obj.members):
                    dependency(ref, value, f"MEMBER:{index}", "K->MEMBER")

        included_uids = set(included)
        links: dict[str, LinkDiagnostic] = {}
        for uid in tuple(included_uids):
            for link in self.core.store.outgoing_links(uid):
                if link.uid not in explicit_links and link.target.uid not in included_uids:
                    continue
                if link.source.uid not in included_uids or link.target.uid not in included_uids:
                    continue
                links[link.uid] = LinkDiagnostic(
                    link.uid,
                    link.relation_id,
                    link.source.uid,
                    link.target.uid,
                    link.weight,
                )
        for uid in explicit_links:
            try:
                link = self.core.store.get_link(uid)
            except KeyError:
                continue
            if link.source.uid in included_uids and link.target.uid in included_uids:
                links[uid] = LinkDiagnostic(
                    link.uid,
                    link.relation_id,
                    link.source.uid,
                    link.target.uid,
                    link.weight,
                )

        workspace_uids = (
            {ref.uid for ref in self.ignition.workspace_refs()}
            if self.ignition is not None
            else set()
        )
        nodes: list[NodeDiagnostic] = []
        for ref in sorted(
            included.values(),
            key=lambda item: self.core.store.creation_sequence(item.uid),
        ):
            domain = self.core.store.domain_of(ref.uid)
            runtime = self.core.store.runtime_state(ref.uid)
            lifecycle = None
            associative_weight = None
            if ref.kind is RefKind.N:
                node = self.core.store.get_hypernode(ref.uid)
                associative_weight = node.weight
                raw_lifecycle = node.meta.get("lifecycle_state")
                lifecycle = None if raw_lifecycle is None else str(raw_lifecycle)
            nodes.append(
                NodeDiagnostic(
                    uid=ref.uid,
                    kind=ref.kind.value,
                    domain=None if domain is None else domain.value,
                    semantic=self._semantic(ref),
                    creation_sequence=self.core.store.creation_sequence(ref.uid),
                    first_excitation_tick=runtime.first_excitation_tick,
                    excitation=runtime.excitation,
                    associative_weight=associative_weight,
                    output=runtime.output,
                    activation_event=runtime.activation_event,
                    decay_age=runtime.decay_age,
                    lifecycle_state=lifecycle,
                    in_workspace=ref.uid in workspace_uids,
                )
            )
        tick = 0
        pending: dict[str, float] = {}
        refutations: tuple[str, ...] = ()
        if self.ignition is not None:
            ignition = self.ignition.export_snapshot(include_pending=True)
            tick = ignition.tick_index
            pending = {
                uid: value
                for uid, value in ignition.incoming.items()
                if uid in included_uids
            }
            refutations = tuple(
                uid for uid in ignition.pending_refutations if uid in included_uids
            )
        return GraphSnapshot(
            tick=tick,
            workspace_uids=tuple(sorted(workspace_uids & included_uids)),
            workspace_semantics={},
            nodes=tuple(nodes),
            links=tuple(links[uid] for uid in sorted(links)),
            structural_edges=tuple(
                structural[key]
                for key in sorted(structural)
                if key[0] in included_uids and key[1] in included_uids
            ),
            pending_incoming=pending,
            pending_refutations=refutations,
        )

    def _semantic(self, ref: Ref) -> str:
        try:
            value = self.semantic.inference_text_for_ref(ref)
            return value[:-2] if value.endswith("()") else value
        except Exception:
            return f"{ref.kind.value}:{ref.uid}"
