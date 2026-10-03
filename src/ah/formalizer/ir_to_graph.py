# -*- coding: utf-8 -*-
"""P2 — CandidateIR -> AHStore graph ops (the WP0.5 seam, §17).

Pure mapping layer: turns the formalizer's semantic IR into a flat list of ``StoreOp``s that the
store adapter interprets against the live ``AHCore`` write API. It carries NO store dependency, so
the *mapping decisions* are unit-testable in isolation; only the adapter resolves descriptors to real
Refs.

Locked design (see the P2 mapping discussion):
- lexical units            -> AbstractSymbol (S)          [global layer, no domain]
- EventFrame              -> Template (T) + Hypernode (N); predicate MUST be S, template MUST be T
- actant value (mention)  -> resolved Ref via an injectable resolver (default: lexical S)
- PropositionNode         -> its head frame materialized in Domain.H when EMBEDDED or
                             epistemic_status != ASSERTED (monotonic quarantine), else routed C/P
- graph edges             -> Link (L); relation_id = edge kind

Two DECLARED structural tables (not lexical-semantic; corpus-testable, per the two-tier invariant):
``ROLE_MAP`` (parser role name -> closed ActantRole) and ``OPERATOR_TO_FUNCTION`` (scope operator ->
registered function id). An unknown role is UNCOVERED (recorded), never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ah.formalizer.candidate_ir import (
    ArgumentSpec,
    EventFrame,
    PropositionNode,
    ScopeTreeCandidate,
    SemanticGraphCandidate,
)
from ah.formalizer.store_interface import StoreOp
from ah.model import ActantRole, Domain, RefKind

# --- declared structural mapping tables ---------------------------------------

#: parser role name -> closed ActantRole. Absent key => UNCOVERED (recorded, not dropped).
ROLE_MAP: dict[str, ActantRole] = {
    "SUBJECT": ActantRole.SUBJECT,
    "OBJECT": ActantRole.OBJECT,
    "AUXILIARY": ActantRole.AUXILLIARY,
    "RECIPIENT": ActantRole.RECIPIENT,
    "SOURCE": ActantRole.SOURCE,
    "ABSENTEE": ActantRole.ABSENTEE,
    "LOCATION": ActantRole.LOCATION,
    "STATE": ActantRole.STATE,
    "TIME": ActantRole.TIME,
    "DURATION": ActantRole.DURATION,
    "CAUSE": ActantRole.CAUSE,
    "PURPOSE": ActantRole.PURPOSE,
    "TOOL": ActantRole.TOOL,
    "MATERIAL": ActantRole.MATERIAL,
    "AMOUNT": ActantRole.AMOUNT,
}

#: scope operator type -> registered core FunctionRegistry id (closed set).
OPERATOR_TO_FUNCTION: dict[str, str] = {
    "NOT": "NOT",
    "EVERY": "FORALL",
    "SOME": "EXISTS",
    "POSSIBLE": "POSSIBLE",
    "NECESSARY": "REQUIRED",
    "IF": "IMPLIES",
}

#: ArgumentSpec.arg_type -> expected RefKind of the resolved actant operand.
ARG_TYPE_TO_REFKIND: dict[str, RefKind] = {
    "ENTITY": RefKind.M,
    "EVENT": RefKind.N,
    "PROPOSITION": RefKind.N,
    "SET": RefKind.K,
}


@dataclass(frozen=True)
class OperandSpec:
    """How to resolve an actant value to a live Ref. ``form`` is the lexical surface (default path)."""

    ref_kind: str = "S"  # S | M | N | K
    form: str = ""


@dataclass
class MappingReport:
    """What the mapping covered and what it could not (honest incompleteness, never silent)."""

    uncovered_roles: tuple[str, ...] = ()
    unresolved_values: tuple[object, ...] = ()
    deferred_nodes: tuple[str, ...] = ()  # e.g. nested propositions / scope trees not yet materialized


class GraphBuilder:
    """Emits StoreOps for one CandidateIR. Pure: no store access; a resolver maps OperandSpec->Ref."""

    def __init__(
        self,
        default_domain: Domain = Domain.C,
        resolver: Callable[[OperandSpec], str] | None = None,
    ) -> None:
        self.default_domain = default_domain
        # resolver returns the store-side key for an operand (default: its lexical form as an S).
        self._resolve = resolver or (lambda spec: spec.form)

    # -- domain decision -------------------------------------------------------
    def proposition_domain(self, prop: PropositionNode) -> Domain:
        """EMBEDDED or non-ASSERTED content is quarantined to H; asserted top-level routes C/P."""
        if prop.status == "EMBEDDED" or prop.epistemic_status != "ASSERTED":
            return Domain.H
        return self.default_domain

    # -- actants ---------------------------------------------------------------
    def _actant_spec(self, arg: ArgumentSpec) -> OperandSpec | None:
        value = arg.value
        if isinstance(value, str):
            kind = ARG_TYPE_TO_REFKIND.get(arg.arg_type, RefKind.S).value
            return OperandSpec(ref_kind=kind, form=value)
        return None  # non-str (nested prop / existential ref) -> unresolved for this slice

    def _covered_roles(self, frame: EventFrame, report: MappingReport):
        roles = []
        actants = {}
        seen = set()
        for arg in frame.participants:
            role = ROLE_MAP.get(arg.slot_ref)
            if role is None or role in seen:
                report.uncovered_roles += (arg.slot_ref,)
                continue
            spec = self._actant_spec(arg)
            if spec is None:
                report.unresolved_values += (arg.value,)
                continue
            seen.add(role)
            roles.append(role)
            actants[role] = self._resolve(spec)
        return tuple(roles), actants

    # -- node emitters ---------------------------------------------------------
    def _frame_ops(self, frame: EventFrame, domain: Domain, report: MappingReport) -> list[StoreOp]:
        roles, actants = self._covered_roles(frame, report)
        ops = [
            StoreOp("ADD_SYMBOL", {"form": frame.predicate}),
            StoreOp(
                "ADD_TEMPLATE",
                {"domain": domain.value, "predicate_form": frame.predicate, "roles": [r.value for r in roles]},
            ),
        ]
        if actants:
            ops.append(
                StoreOp(
                    "ADD_HYPERNODE",
                    {
                        "domain": domain.value,
                        "predicate_form": frame.predicate,
                        "roles": [r.value for r in roles],
                        "actants": {k.value: v for k, v in actants.items()},
                        "weight": 0.5,
                    },
                )
            )
        return ops

    def _node_ops(self, node, domain: Domain, report: MappingReport) -> list[StoreOp]:
        if isinstance(node, EventFrame):
            return self._frame_ops(node, domain, report)
        if isinstance(node, PropositionNode):
            head_domain = self.proposition_domain(node)
            head = node.head
            if isinstance(head, EventFrame):
                return self._frame_ops(head, head_domain, report)
            if isinstance(head, PropositionNode):
                # nested composition: materialize the innermost asserted frame in H (quarantine).
                report.deferred_nodes += ("nested_proposition",)
                return self._node_ops(head, Domain.H, report)
        report.deferred_nodes += (type(node).__name__,)
        return []

    def _edge_ops(self, edges, refmap: dict[str, str]) -> list[StoreOp]:
        ops = []
        for src, tgt, kind in edges:
            if src in refmap and tgt in refmap:
                ops.append(StoreOp("ADD_LINK", {"relation_id": kind, "source": refmap[src], "target": refmap[tgt]}))
        return ops

    # -- top level -------------------------------------------------------------
    def build_ops(self, graph: SemanticGraphCandidate) -> tuple[list[StoreOp], MappingReport]:
        """Materialize one SemanticGraphCandidate into ordered StoreOps + a coverage report."""
        report = MappingReport()
        refmap: dict[str, str] = {}  # node id -> store key (for edge endpoints)
        ops: list[StoreOp] = []

        for node in graph.nodes:
            if isinstance(node, EventFrame):
                ops += self._frame_ops(node, self.default_domain, report)
                refmap[node.frame_id] = node.predicate
            elif isinstance(node, PropositionNode):
                ops += self._node_ops(node, self.default_domain, report)

        # edges reference nodes by id; only emit links whose both endpoints were materialized.
        ops += self._edge_ops(graph.edges, refmap)
        return ops, report


def build_graph_ops(
    graph: SemanticGraphCandidate,
    default_domain: Domain = Domain.C,
    resolver: Callable[[OperandSpec], str] | None = None,
) -> tuple[list[StoreOp], MappingReport]:
    """Convenience wrapper: one candidate graph -> (ops, report)."""
    return GraphBuilder(default_domain=default_domain, resolver=resolver).build_ops(graph)
