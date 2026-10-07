# -*- coding: utf-8 -*-
"""WP2.x — typed execution layer for a commit plan (I19, §7.4/SOM).

The mapping half (:mod:`ir_to_graph`) emits *opaque* ``StoreOp``s whose payloads flatten every type to a
string (``domain.value``, ``role.value``) and carry no truth-ground support; the materialization half
(:mod:`graph_ops`) then blindly re-parses them (``Domain(p["domain"])``, ``ActantRole(r)``). Two defects fall
out of that split:

* **D1 — types are not validated before materialization.** An invalid role/operator/domain is either a crash
  that rolls back the whole transaction or, worse, silently constructs a wrong element. There is no per-op,
  named diagnostic.
* **D2 — asserted facts get no §7.4 truth-ground support.** ``handle_add_hypernode`` materializes an N root but
  never attaches its O/C/W direct support to the proof graph, so a committed fact is not F-visible by its own
  ground (support_som: only O/C/W assert a fact; R/D/M/A/P are interpretation-only).

This module is the *typed execution layer* that sits between mapping and materialization. It is pure (no store
dependency) so both properties are unit-testable in isolation, exactly like the rest of the seam:

* :func:`validate_plan` — every op's domain/role/operator is checked against the CLOSED sets before anything is
  written; an unknown value yields a named ``PlanIssue`` and the plan is refused (fail-closed), never partially
  materialized. This is the "proper types" half of I19.
* :func:`attach_fact_supports` — each asserted fact (an N root) has its O/C/W ground attached to a
  :class:`~ah.formalizer.support_som.ProofGraph`; an interpretation-only ground (R/D/M/A/P) is rejected by the
  ledger and grounds nothing, so a fact whose only "grounds" are M-traces/D-derivations is NOT F-visible. This is
  the "proper supports" half of I19 and ties the writer to §7.4/SOM.

:func:`from_store_ops` lifts opaque ``StoreOp``s into typed mutations, so this layer composes with the existing
mapping instead of duplicating it. The single production route (I01) will drive commits through here; until then
the legacy handler path is left untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ah.model import ActantRole, Domain

from .ir_to_graph import OPERATOR_TO_FUNCTION
from .store_interface import StoreOp
from .support_som import FACT_GROUNDS, InvalidFactGround, Node, ProofGraph

# op types that materialize an ASSERTED fact (an N root) and therefore need a §7.4 O/C/W ground.
FACT_OP_TYPES = frozenset({"ADD_HYPERNODE", "ADD_SCOPE"})

_DOMAINS = frozenset(d.value for d in Domain)
_ROLES = frozenset(r.value for r in ActantRole)
# declared scope operators: the operator table plus ONLY / AT_LEAST_N (handled by graph_ops).
_OPERATORS = frozenset(OPERATOR_TO_FUNCTION) | {"ONLY", "AT_LEAST_N"}


@dataclass(frozen=True)
class TypedMutation:
    """One typed plan op. Values are carried as their string form (as the mapping emits them) and validated
    against the closed sets before materialization; ``supports`` are ground-type tokens."""

    op_id: str
    op_type: str
    domain: str | None = None          # a Domain value, or None for domain-less ops (e.g. ADD_SYMBOL)
    roles: tuple[str, ...] = ()        # ActantRole values; each must be in the closed set
    operators: tuple[str, ...] = ()    # scope-chain operator types (ADD_SCOPE); each declared
    supports: tuple[str, ...] = ()     # ground-type tokens; only O/C/W assert a fact (§7.4)


@dataclass(frozen=True)
class MutationPlanV2:
    """An ordered set of typed mutations to be validated and executed as one unit."""

    ops: tuple[TypedMutation, ...] = ()


@dataclass(frozen=True)
class PlanIssue:
    """A named type violation on one op (D1): the plan is refused, not partially applied."""

    op_id: str
    field: str        # "op_id" | "domain" | "role" | "operator"
    value: object
    reason: str


class PlanValidationError(ValueError):
    """Raised by :func:`execute_plan` when the plan fails type validation (fail-closed)."""

    def __init__(self, issues: Sequence[PlanIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("plan failed type validation: " + "; ".join(f"{i.op_id}.{i.field}={i.value!r}" for i in self.issues))


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of executing a validated plan against the proof graph (D2)."""

    f_visible: dict[str, bool] = field(default_factory=dict)   # fact op_id -> F-visible by its own ground
    ungrounded_facts: tuple[str, ...] = ()                    # asserted facts with no O/C/W ground


def validate_plan(plan: MutationPlanV2) -> tuple[PlanIssue, ...]:
    """D1: check every op's domain/role/operator against the closed sets. Empty result == plan is well-typed."""
    issues: list[PlanIssue] = []
    seen: set[str] = set()
    for op in plan.ops:
        if op.op_id in seen:
            issues.append(PlanIssue(op.op_id, "op_id", op.op_id, "duplicate op_id"))
        seen.add(op.op_id)

        if op.domain is not None and op.domain not in _DOMAINS:
            issues.append(PlanIssue(op.op_id, "domain", op.domain, f"not a Domain ({sorted(_DOMAINS)})"))
        for role in op.roles:
            if role not in _ROLES:
                issues.append(PlanIssue(op.op_id, "role", role, "not an ActantRole (closed set)"))
        for operator in op.operators:
            if operator not in _OPERATORS:
                issues.append(PlanIssue(op.op_id, "operator", operator, f"unregistered operator ({sorted(_OPERATORS)})"))
    return tuple(issues)


def attach_fact_supports(plan: MutationPlanV2, graph: ProofGraph | None = None) -> ExecutionResult:
    """D2: attach each asserted fact's O/C/W ground to the proof graph (§7.4).

    A fact is F-visible iff it gains at least one live, complete ROOT support; only O/C/W qualify (the ledger
    rejects R/D/M/A/P via ``InvalidFactGround``). A fact whose only grounds are interpretation-only therefore
    stays ungrounded and is reported in ``ungrounded_facts`` — it must not be committed as an asserted fact.
    """
    if graph is None:
        nodes = [Node(node_id=op.op_id, kind="N", asserted=True) for op in plan.ops if op.op_type in FACT_OP_TYPES]
        graph = ProofGraph(nodes)

    # Attach every ground; the ledger rejects interpretation-only types (R/D/M/A/P) via InvalidFactGround.
    for op in plan.ops:
        if op.op_type not in FACT_OP_TYPES:
            continue
        node = graph.nodes.get(op.op_id) or Node(node_id=op.op_id, kind="N", asserted=True)
        graph.nodes[op.op_id] = node
        for ground in op.supports:
            try:
                graph.add_root_support(op.op_id, ground, tag=("obs", 0), record_id=f"{op.op_id}:{ground}")
            except InvalidFactGround:
                continue  # interpretation-only ground never asserts a fact (§7.4)

    visible = set(graph.f_visible())
    f_visible_map = {op.op_id: (op.op_id in visible) for op in plan.ops if op.op_type in FACT_OP_TYPES}
    ungrounded = tuple(oid for oid, is_vis in f_visible_map.items() if not is_vis)
    return ExecutionResult(f_visible=f_visible_map, ungrounded_facts=ungrounded)


def execute_plan(plan: MutationPlanV2, graph: ProofGraph | None = None) -> ExecutionResult:
    """Validate (D1) then attach fact supports (D2). Raises ``PlanValidationError`` on any type issue — the plan
    is refused whole, never partially materialized."""
    issues = validate_plan(plan)
    if issues:
        raise PlanValidationError(issues)
    return attach_fact_supports(plan, graph)


def from_store_ops(ops: Sequence[StoreOp]) -> MutationPlanV2:
    """Lift opaque ``StoreOp``s into typed mutations (composes with :func:`ir_to_graph.build_ops`).

    Supports are read from the payload when present; an op that materializes a fact but carries no O/C/W ground
    is lifted as-is and will surface in ``ungrounded_facts`` — the honest record of the legacy writer's gap.
    """
    out: list[TypedMutation] = []
    for i, op in enumerate(ops):
        p = op.payload
        roles = tuple(p.get("roles", ()) or p.get("base_roles", ()))
        operators: tuple[str, ...] = ()
        if op.op_type == "ADD_SCOPE":
            operators = tuple(step.get("op_type") for step in p.get("chain", ()) if step.get("op_type"))
        out.append(
            TypedMutation(
                op_id=str(p.get("uid") or f"op{i}"),
                op_type=op.op_type,
                domain=p.get("domain"),
                roles=roles,
                operators=operators,
                supports=tuple(p.get("supports", ())),
            )
        )
    return MutationPlanV2(tuple(out))
