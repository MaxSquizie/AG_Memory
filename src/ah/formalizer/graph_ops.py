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

from ah.formalizer.ir_to_graph import OPERATOR_TO_FUNCTION, ROLE_MAP
from ah.model import ActantRole, BoundVar, Domain, Property, Ref, VariableSort, TimeLiteral, CountLiteral


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


def _value_token(core: Any, n) -> Ref:
    """Lightweight value token for a numeric bound (a number is a value, not a lexical symbol)."""
    return _ensure_symbol(core, f"n{float(n):g}")


def handle_add_group(core: Any, p: dict) -> None:
    """Materialize a K-group (e.g. a COREF_CLUSTER): resolve member forms to Refs, then group them."""
    domain = Domain(p["domain"])
    members = tuple(_operand(core, form) for form in p.get("member_forms", ()))
    meta = {"kind": p["kind"]} if p.get("kind") else None
    core.add_group(domain, members, meta=meta)


def handle_add_scope(core: Any, p: dict) -> None:
    """Materialize a base frame then wrap it with an inner->outer operator chain (G-nodes).

    Quantifiers bind their target slot with a fresh BoundVar on a QUANTIFIED-scoped instance and
    register the var as an operand of EXISTS/FORALL. AT_LEAST_N adds a value token + one Link from
    the scope to its threshold (the brain-faithful "bounded concept": no separate cardinality node).
    Modal scopes (POSSIBLE/NECESSARY) are quarantined to Domain.H; ONLY attaches a uniqueness property
    to the restricted instance. Unregistered operators are skipped (reported upstream as uncovered).
    """
    domain = Domain(p["domain"])
    pred_ref = _ensure_symbol(core, p["base_predicate_form"])
    roles = _roles(p.get("base_roles", ()))
    template_ref = _get_or_create_template(core, domain, pred_ref, roles)
    base_actants = {ActantRole(k): _operand(core, v) for k, v in p.get("base_actants", {}).items()}
    base_node, _ = core.add_hypernode(domain, template_ref, base_actants, 0.5)
    current = core.ref(base_node.uid)

    for step in p.get("chain", ()):
        op = step["op_type"]
        if op == "ONLY":
            core.add_property(base_node.uid, Property(name="only", value=True, type_name="bool"))
            continue
        fid = "EXISTS" if op == "AT_LEAST_N" else OPERATOR_TO_FUNCTION.get(op)
        if fid is None:
            raise ValueError("SCOPE_NOT_COVERED:"+op)
        node_domain = Domain.H if op in ("POSSIBLE", "NECESSARY") else domain
        if op in ("SOME", "EVERY", "AT_LEAST_N"):
            raw_vid = step.get("variable_id")
            try:
                vid: int | None = int(raw_vid) if raw_vid is not None else None
            except (TypeError, ValueError):
                vid = None
            var = BoundVar(vid or 0, VariableSort.ENTITY)
            q_actants = dict(base_actants)
            slot = step.get("target_slot")
            if slot and slot in ROLE_MAP:
                q_actants[ROLE_MAP[slot]] = var
            qnode, _ = core.add_hypernode(
                domain, template_ref, q_actants, 0.5, meta={"semantic_scope": "QUANTIFIED"}
            )
            gref = core.ref(core.add_function(node_domain, fid, (var, core.ref(qnode.uid))).uid)
            if op == "AT_LEAST_N" and step.get("bound_value") is not None:
                core.add_link("AT_LEAST", gref, _value_token(core, step["bound_value"]), 0.5)
            current = gref
        else:  # NOT / POSSIBLE / REQUIRED (unary); IF deferred to a two-operand slice
            if op == "IF":
                raise ValueError("IMPLIES_REQUIRES_TWO_OPERANDS")
            current = core.ref(core.add_function(node_domain, fid, (current,)).uid)


GRAPH_HANDLERS: dict[str, Callable[[Any, dict], Any]] = {
    "ADD_SYMBOL": handle_add_symbol,
    "ADD_TEMPLATE": handle_add_template,
    "ADD_HYPERNODE": handle_add_hypernode,
    "ADD_LINK": handle_add_link,
    "ADD_GROUP": handle_add_group,
    "ADD_SCOPE": handle_add_scope,
}


def register_graph_handlers(adapter: Any) -> None:
    """Register all graph op handlers on a Store adapter (idempotent)."""
    for op_type, handler in GRAPH_HANDLERS.items():
        adapter.register_op_handler(op_type, handler)

# Native operations carry typed references and preassigned stable IDs. They never
# resolve an ENTITY argument to an S token or fabricate a known TemplateMap entry.
def ensure_entity(core,p):
    uid=p['uid']
    if p.get('reference_existing') and not core.store.has_uid(uid): raise ValueError('STALE_PLAN')
    if not core.store.has_uid(uid):
        props={}
        if p.get('name'): props['name']=Property('name',p['name'],'str')
        core.add_entity(Domain(p.get('domain','C')),props,meta={'source_tag':p.get('source_tag'),'mention_ref':p.get('mention_ref')},uid=uid)
    elif core.store.kind_of(uid).value!='M': raise ValueError('ENTITY_REF_TYPE_MISMATCH')
    return uid


def ensure_template(core,p):
    uid=p['uid']
    if core.store.has_uid(uid):
        if core.store.kind_of(uid).value!='T': raise ValueError('TEMPLATE_REF_TYPE_MISMATCH')
        return uid
    if p.get('semantic_status')!='UNLINKED': raise ValueError('CANONICAL_MAPPING_MISSING')
    pred=_ensure_symbol(core,p['predicate_form'])
    core.add_template(Domain(p.get('domain','C')),pred,_roles(p['roles']),uid=uid)
    return uid


def native_operand(core,value):
    if isinstance(value,dict) and 'count_literal' in value:
        return CountLiteral(value['count_literal'])
    if isinstance(value,dict) and 'time_literal' in value:
        return TimeLiteral(tuple(value['time_literal']))
    if isinstance(value,dict) and 'bound_var' in value:
        return BoundVar(value['bound_var'],VariableSort(value.get('sort','ENTITY')))
    uid=value['ref'] if isinstance(value,dict) else value
    return core.ref(uid)


def ensure_node(core,p):
    uid=p['uid']
    if core.store.has_uid(uid):
        if core.store.kind_of(uid).value!='N': raise ValueError('NODE_REF_TYPE_MISMATCH')
        old=core.store.get_hypernode(uid)
        actants={ActantRole(k):native_operand(core,v) for k,v in p['actants'].items()}
        if old.template!=core.ref(p['template_ref']) or dict(old.actants)!=actants:
            raise ValueError('INTEGRITY_ERROR: node content changed')
        return uid
    core.add_hypernode(Domain(p.get('domain','C')),core.ref(p['template_ref']),{ActantRole(k):native_operand(core,v) for k,v in p['actants'].items()},float(p.get('weight',0.5)),meta={'semantic_status':p.get('semantic_status','KNOWN'),'identity_key':p.get('identity_key'), 'temporal_mode':p.get('temporal_mode','UNKNOWN'),'source_tag':p.get('source_tag')},uid=uid,deduplicate=False,count_occurrence=False)
    return uid


def ensure_function(core,p):
    uid=p['uid']; fid=core.function_registry.canonical_id(p['function_id'])
    operands=tuple(native_operand(core,x) for x in p['operands'])
    core.function_registry.validate(fid,operands)
    if fid in {'BEFORE','AFTER','DURING'} and all(isinstance(x,TimeLiteral) for x in operands):
        from .temporal_order import compare_anchors
        if compare_anchors(fid,*operands) is False: raise ValueError('CONSTRAINT_CONFLICT')
    if fid in {'AND','OR','XOR'}:
        operands=tuple(sorted(operands,key=lambda x:(getattr(x,'kind',None).value if isinstance(x,Ref) else 'VAR',getattr(x,'uid',str(x)))))
    if fid in {'FORALL','EXISTS'} and len(operands)!=2: raise ValueError('QUANTIFIER_ARITY_INVALID')
    if core.store.has_uid(uid):
        old=core.store.get_element_any_domain(uid)
        if getattr(old,'function_id',None)!=fid or old.operands!=operands: raise ValueError('INTEGRITY_ERROR: function content changed')
    else: core.add_function(Domain(p.get('domain','C')),fid,operands,uid=uid)
    return uid


def ensure_group(core,p):
    if not core.store.has_uid(p['uid']):
        core.add_group(Domain(p.get('domain','C')),tuple(core.ref(r) for r in p['members']),uid=p['uid'])
    return p['uid']

GRAPH_HANDLERS.update(ENSURE_ENTITY=ensure_entity,ENSURE_TEMPLATE=ensure_template,ENSURE_NODE=ensure_node,ENSURE_FUNCTION=ensure_function,ENSURE_GROUP=ensure_group)
