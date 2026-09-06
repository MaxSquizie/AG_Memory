from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from ah.core import AHCore
from ah.model import Domain, FunctionSymbol, Hypernode, Ref, RefKind


@dataclass(frozen=True, slots=True)
class PropagationEdgeAudit:
    source_uid: str
    target_uid: str
    gain: float
    relation: str


@dataclass(frozen=True, slots=True)
class FanoutAudit:
    source_uid: str
    cumulative_gain: float
    max_single_target_gain: float


@dataclass(frozen=True, slots=True)
class PropagationAudit:
    node_count: int
    edge_count: int
    cyclic_components: tuple[tuple[str, ...], ...]
    max_path_hops: int | None
    fanout: tuple[FanoutAudit, ...]
    edges: tuple[PropagationEdgeAudit, ...]

    @property
    def acyclic(self) -> bool:
        return not self.cyclic_components


def propagation_edges(core: AHCore) -> tuple[PropagationEdgeAudit, ...]:
    """Mirror the engine's deterministic structural propagation topology.

    Pacemaker/external seeds are sources of packets, not graph edges, so they are
    intentionally absent.  The graph includes canonical L direction, lexical
    retrieval S->T->N, and N->actants.  Scoped N are skipped from direct T->N
    lexical recall exactly like IgnitionEngine.
    """
    out: list[PropagationEdgeAudit] = []
    for link in core.store.links():
        if link.weight > 0:
            out.append(
                PropagationEdgeAudit(
                    link.source.uid, link.target.uid, float(link.weight),
                    f"L:{link.relation_id}",
                )
            )

    for symbol_uid in tuple(core.store._state.symbols):
        for template in core.store.find_templates_by_predicate(symbol_uid):
            out.append(
                PropagationEdgeAudit(symbol_uid, template.uid, 1.0, "S->T")
            )

    for domain in Domain:
        for element in core.store.elements(domain):
            if not isinstance(element, Hypernode):
                continue
            if not element.meta.get("semantic_scope") and element.weight > 0:
                false_wrappers = tuple(
                    parent for parent in core.store.function_parents(element.uid)
                    if isinstance(parent, FunctionSymbol)
                    and parent.function_id.upper() in {"FALSE", "NOT"}
                    and len(parent.operands) == 1
                )
                targets = false_wrappers or (element,)
                for target in targets:
                    out.append(
                        PropagationEdgeAudit(
                            element.template.uid,
                            target.uid,
                            float(element.weight),
                            "T->FALSE(N)" if false_wrappers else "T->N",
                        )
                    )
            if element.weight > 0:
                for role, ref in element.actants.items():
                    if not isinstance(ref, Ref):
                        continue
                    out.append(
                        PropagationEdgeAudit(
                            element.uid, ref.uid, float(element.weight),
                            f"N->{role.value}",
                        )
                    )
    return tuple(out)


def _scc(nodes: set[str], edges: tuple[PropagationEdgeAudit, ...]) -> tuple[tuple[str, ...], ...]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source_uid].append(edge.target_uid)

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    low: dict[str, int] = {}
    components: list[tuple[str, ...]] = []

    def visit(uid: str) -> None:
        nonlocal index
        indexes[uid] = index
        low[uid] = index
        index += 1
        stack.append(uid)
        on_stack.add(uid)
        for target in adjacency.get(uid, ()):
            if target not in indexes:
                visit(target)
                low[uid] = min(low[uid], low[target])
            elif target in on_stack:
                low[uid] = min(low[uid], indexes[target])
        if low[uid] != indexes[uid]:
            return
        component: list[str] = []
        while True:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == uid:
                break
        components.append(tuple(component))

    for uid in sorted(nodes):
        if uid not in indexes:
            visit(uid)

    cyclic: list[tuple[str, ...]] = []
    self_loops = {(edge.source_uid, edge.target_uid) for edge in edges if edge.source_uid == edge.target_uid}
    for component in components:
        if len(component) > 1 or (component and (component[0], component[0]) in self_loops):
            cyclic.append(tuple(sorted(component)))
    return tuple(sorted(cyclic))


def analyze_propagation(core: AHCore) -> PropagationAudit:
    edges = propagation_edges(core)
    nodes = {uid for uid, _state in core.store.runtime_items()}
    for edge in edges:
        nodes.add(edge.source_uid)
        nodes.add(edge.target_uid)
    cyclic = _scc(nodes, edges)

    # Longest-path/fanout are meaningful only for a DAG.  They deliberately sum
    # all directed path gains; branching may therefore produce cumulative gain >1
    # even when every individual edge gain <=1.
    max_path_hops: int | None = None
    fanout: tuple[FanoutAudit, ...] = ()
    if not cyclic:
        adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
        indegree = {uid: 0 for uid in nodes}
        for edge in edges:
            adjacency[edge.source_uid].append((edge.target_uid, edge.gain))
            indegree[edge.target_uid] = indegree.get(edge.target_uid, 0) + 1
        queue = deque(uid for uid in nodes if indegree.get(uid, 0) == 0)
        topo: list[str] = []
        while queue:
            uid = queue.popleft()
            topo.append(uid)
            for target, _gain in adjacency.get(uid, ()):
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)

        hops = {uid: 0 for uid in nodes}
        for uid in topo:
            for target, _gain in adjacency.get(uid, ()):
                hops[target] = max(hops[target], hops[uid] + 1)
        max_path_hops = max(hops.values(), default=0)

        fanout_rows: list[FanoutAudit] = []
        for source in nodes:
            gain_to: dict[str, float] = defaultdict(float)
            gain_to[source] = 1.0
            for uid in topo:
                packet = gain_to.get(uid, 0.0)
                if packet <= 0:
                    continue
                for target, gain in adjacency.get(uid, ()):
                    gain_to[target] += packet * gain
            downstream = [value for uid, value in gain_to.items() if uid != source]
            fanout_rows.append(
                FanoutAudit(
                    source,
                    float(sum(downstream)),
                    float(max(downstream, default=0.0)),
                )
            )
        fanout = tuple(sorted(fanout_rows, key=lambda row: row.cumulative_gain, reverse=True))

    return PropagationAudit(
        node_count=len(nodes),
        edge_count=len(edges),
        cyclic_components=cyclic,
        max_path_hops=max_path_hops,
        fanout=fanout,
        edges=edges,
    )
