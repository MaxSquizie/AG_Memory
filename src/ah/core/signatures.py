from __future__ import annotations

from ah.model import ActantRole, Hypernode, Template


def hypernode_signature(node: Hypernode, template: Template) -> tuple:
    """Semantic identity of an N inside one C/P/H domain.

    Weight, Pr, Mt and occurrence counters are intentionally excluded.
    Roles are normalized according to the canonical Template order.
    """
    scope = node.meta.get("semantic_scope")
    return (
        template.uid,
        tuple(
            (role.value, node.actants[role].kind.value, node.actants[role].uid)
            for role in template.roles
            if role in node.actants
        ),
        # A proposition nested under a logical/semantic operator is not the same
        # canonical assertion occurrence as the same proposition asserted at the
        # world level.  Scope therefore participates in N semantic identity while
        # ordinary metadata (weights, lifecycle, occurrence counters) does not.
        ("semantic_scope", str(scope)) if scope else None,
    )
