"""Dissipative text attention. No epoch, wall clock, cardinality cap or TTL GC.

Stored activation plus pending propagation is a single conserved pool before
leakage. Each source distributes its transfer among all eligible edges. Thus
E(next) <= retention * (E(now) + input_budget), even with fanout and cycles.
Attention loss never retracts canonical facts or expires their support records.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace

from ah.model import Ref, RefKind, FunctionSymbol
from ah.integration.contracts import SeedReason


def targets(core, uid):
    """Typed AH routes; activation through an operand never asserts it."""
    result = []
    ref = core.ref(uid)
    for link in core.store.outgoing_links(uid):
        if link.weight > 0 and link.target.kind is not RefKind.L:
            result.append((link.target, link.weight, link.uid, 'L', link.relation_id))
    if ref.kind is RefKind.S:
        result.extend((core.ref(t.uid), 1.0, uid, 'S', 'PREDICATE_TEMPLATE')
                      for t in core.store.find_templates_by_predicate(uid))
    elif ref.kind is RefKind.T:
        for n in core.store.find_hypernodes_by_template(uid):
            if n.meta.get('semantic_scope') or n.weight <= 0:
                continue
            neg = [g for g in core.store.function_parents(n.uid)
                   if isinstance(g, FunctionSymbol) and g.function_id.upper() in {'NOT', 'FALSE'}
                   and len(g.operands) == 1]
            result.extend((core.ref(t.uid), n.weight, uid, 'T', 'TEMPLATE_REALIZATION') for t in (neg or [n]))
    elif ref.kind is RefKind.N:
        n = core.store.get_hypernode(uid)
        result.extend((r, n.weight, uid, 'N', role.value) for role, r in n.actants.items()
                      if isinstance(r, Ref) and r.kind is not RefKind.L and n.weight > 0)
    elif ref.kind in {RefKind.G,RefKind.K}:
        node=core.store.get_element_any_domain(uid)
        children=node.operands if ref.kind is RefKind.G else node.members
        result.extend((r,1.0,uid,ref.kind.value,'STRUCTURAL_ARGUMENT') for r in children
                      if isinstance(r,Ref) and r.kind is not RefKind.L)
    return sorted(result, key=lambda x: (x[0].uid, x[2], x[4]))


def event_tick(engine):
    from .engine import TickResult, NodeTickTransition, PropagationEvent
    core = engine.core
    cfg = engine.settings
    eps = cfg.activation.epsilon
    external = dict(engine._event_external)
    total_external = sum(external.values())
    scale = min(1.0, cfg.event_input_budget / total_external) if total_external > 0 else 1.0
    incoming = {uid: max(0.0, value-external.get(uid, 0.0))+external.get(uid, 0.0)*scale
                for uid, value in engine._incoming.items()}
    reasons = {uid: tuple(rs) for uid, rs in engine._seed_reasons.items()}
    affected = sorted(uid for uid in engine._active_uids | incoming.keys()
                      if core.store.has_uid(uid) and core.store.kind_of(uid) is not RefKind.L)
    updates = {}
    transitions = []
    scheduled = defaultdict(float)
    propagations = []
    activated = []
    tick = engine.tick_index
    for uid in affected:
        before = deepcopy(core.store.runtime_state(uid))
        after = deepcopy(before)
        z = incoming.get(uid, 0.0)
        available = max(0.0, before.excitation+z) * cfg.event_retention
        edges = targets(core, uid) if available > eps else []
        transfer = available * cfg.event_transfer if edges else 0.0
        after.excitation = min(cfg.x_max, available-transfer)
        if after.excitation <= eps:
            after.excitation = 0.0
        after.output = transfer
        after.activation_event = z > eps
        after.decay_age = before.decay_age+1
        after.decay_origin_excitation = 0.0
        if z > eps:
            activated.append(core.ref(uid))
            after.last_activation_tick = tick
            if before.first_excitation_tick is None:
                after.first_excitation_tick = tick
        if transfer > eps:
            after.last_output_tick = tick
            total = sum(weight for _, weight, *_ in edges)
            for target, weight, via, kind, relation in edges:
                amount = transfer * weight / total
                scheduled[target.uid] += amount
                propagations.append(PropagationEvent(core.ref(uid), target, via, kind, relation, amount))
        updates[uid] = after
        transitions.append(NodeTickTransition(core.ref(uid), z, 0.0, reasons.get(uid, ()), before, after))
    weight_updates = []
    if cfg.plasticity.enabled:
        for uid in sorted(set(reasons) | engine._pending_refutations):
            if not core.store.has_uid(uid) or core.store.kind_of(uid) is not RefKind.N:
                continue
            domain = core.store.domain_of(uid)
            if domain is None:
                continue
            node = core.store.get_hypernode(uid)
            weight = node.weight
            if uid in engine._pending_refutations:
                weight = engine.plasticity_policy.refute_hypernode(weight)
            elif external.get(uid, 0.0) > eps and SeedReason.REACTIVATED_FACT in reasons.get(uid, ()):
                weight = engine.plasticity_policy.confirm_hypernode(weight)
            if weight != node.weight:
                core.store._replace_hypernode(domain, replace(node, weight=weight))
                weight_updates.append((uid, node.weight, weight))
    core.store._update_runtime_states(updates)
    engine._active_uids = {uid for uid, s in updates.items() if s.excitation > eps}
    engine._incoming = defaultdict(float, {uid: x for uid, x in scheduled.items() if x > eps})
    engine._event_external.clear()
    engine._seed_reasons.clear()
    engine._pacemaker_incoming.clear()
    engine._pacemaker_only_excitation.clear()
    # Attention ticks do not run epoch-based GC or learn from recurrent packets.
    engine._pending_refutations.clear()
    engine.tick_index += 1
    return TickResult(tick, tuple(activated), engine._workspace_refs_locked(), incoming,
                      dict(engine._incoming), propagations=tuple(propagations),
                      node_transitions=tuple(transitions), hypernode_weight_updates=tuple(weight_updates))
