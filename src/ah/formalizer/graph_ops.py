# -*- coding: utf-8 -*-
"""P2 — StoreOp -> live AHCore graph mutations (the op->graph half of the WP0.5 seam).

Counterpart to :mod:`ah.formalizer.ir_to_graph` (which emits ops purely): these handlers resolve each
op against a real ``AHCore`` transaction using find-or-create semantics, so a batch is IDEMPOTENT —
re-committing the same ops does not duplicate symbols/templates/hypernodes.

Handlers are pure functions of ``(core, payload)``: ``_apply_ops`` passes the COW-transaction core on
each call, so no handler holds cross-batch state. Actant/link endpoints default to lexical AbstractSymbol
resolution (S); an entity resolver can be swapped in later without touching the op contract.
"""

from __future__ import annotations

from typing import Any, Callable

from ah.model import ActantRole, Domain, Ref


def _ensure_symbol(core: Any, form: str) -> Ref:
    existing = core.store.find_symbol_by_form(form)
    if existing is None:
        existing = core.add_abstract_symbol({form})
    return core.ref(existing.uid)


def _roles(payload_roles) -> tuple[ActantRole, ...]:
    return tuple(ActantRole(r) for r in payload_roles)


def _get_or_create_template(core: Any, domain: Domain, pred_ref: Ref, roles: tuple[ActantRole, ...]) -> Ref:
    for t in core.store.find_templates_by_predicate(pred_ref.uid):
        if tuple(t.roles) == tuple(roles):
            return core.ref(t.uid)
    template = core.add_template(domain, pred_ref, roles)
    return core.ref(template.uid)


def _operand(core: Any, value: str) -> Ref:
    # default lexical resolution; an entity resolver can replace this without changing the op contract.
    return _ensure_symbol(core, value)


# -- handlers -----------------------------------------------------------------

def handle_add_symbol(core: Any, p: dict) -> None:
    _ensure_symbol(core, p["form"])


def handle_add_template(core: Any, p: dict) -> None:
    domain = Domain(p["domain"])
    pred_ref = _ensure_symbol(core, p["predicate_form"])
    _get_or_create_template(core, domain, pred_ref, _roles(p.get("roles", ())))


def handle_add_hypernode(core: Any, p: dict) -> None:
    domain = Domain(p["domain"])
    pred_ref = _ensure_symbol(core, p["predicate_form"])
    roles = _roles(p.get("roles", ()))
    template_ref = _get_or_create_template(core, domain, pred_ref, roles)
    actants = {ActantRole(k): _operand(core, v) for k, v in p.get("actants", {}).items()}
    core.add_hypernode(domain, template_ref, actants, float(p.get("weight", 0.5)))


def handle_add_link(core: Any, p: dict) -> None:
    source = _operand(core, p["source"])
    target = _operand(core, p["target"])
    core.add_link(str(p["relation_id"]), source, target, float(p.get("weight", 0.5)))


GRAPH_HANDLERS: dict[str, Callable[[Any, dict], Any]] = {
    "ADD_SYMBOL": handle_add_symbol,
    "ADD_TEMPLATE": handle_add_template,
    "ADD_HYPERNODE": handle_add_hypernode,
    "ADD_LINK": handle_add_link,
}


def register_graph_handlers(adapter: Any) -> None:
    """Register all graph op handlers on a Store adapter (idempotent)."""
    for op_type, handler in GRAPH_HANDLERS.items():
        adapter.register_op_handler(op_type, handler)
