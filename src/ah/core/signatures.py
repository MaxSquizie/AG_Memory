from __future__ import annotations

from ah.model import BoundVar, Hypernode, Ref, Template


def hypernode_signature(node: Hypernode, template: Template) -> tuple:
    """Semantic identity of an N inside one C/P/H domain.

    Weight, Pr, Mt and occurrence counters are intentionally excluded.
    Roles are normalized according to the canonical Template order.
    """
    scope = node.meta.get("semantic_scope")
    temporal_mode = node.meta.get("temporal_mode")
    def actant_signature(value):
        if isinstance(value, Ref):
            return ("REF", value.kind.value, value.uid)
        if isinstance(value, BoundVar):
            return ("VAR", value.local_id, value.sort.value)
        raise TypeError(f"Unsupported N actant operand: {type(value).__name__}")

    return (
        template.uid,
        tuple(
            (role.value, *actant_signature(node.actants[role]))
            for role in template.roles
            if role in node.actants
        ),
        # A proposition nested under a logical/semantic operator is not the same
        # canonical assertion occurrence as the same proposition asserted at the
        # world level.  Scope therefore participates in N semantic identity while
        # ordinary metadata (weights, lifecycle, occurrence counters) does not.
        ("semantic_scope", str(scope)) if scope else None,
        # Temporal interpretation belongs to this occurrence/proposition, not T.
        # Otherwise one predicate with identical fillers but distinct STATE/EVENT
        # readings would collapse to one canonical proposition.
        ("temporal_mode", str(temporal_mode)) if temporal_mode else None,
    )
