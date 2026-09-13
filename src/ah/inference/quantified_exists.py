from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ah.core import SupportRecord
from ah.model import ActantRole, Domain, Hypernode, Ref, RefKind

from .bindings import BindingEnvironment
from .contracts import (
    ExistsGoal,
    InferenceOutcome,
    InferenceQuery,
    LogicalStatus,
    ProofSupport,
    StopReason,
)
from .domain import domain_from_premises
from .formula import GroundFormulaReasoner
from .identity_query import EntityIdentityInferenceEngine
from .materialization import (
    InferenceMaterializer as _BaseInferenceMaterializer,
    MaterializationResult,
)
from .attention import InferenceAttention
from .context import ProofContext
from .runtime import GoalRuntime


@dataclass(frozen=True, slots=True)
class DerivedAtomConclusion:
    """Runtime proof of one fully ground atomic proposition not yet canonical N.

    Inference stays read-only.  The conclusion carries only an existing canonical T
    and ground M/N/g role fillers; ``QuantifiedInferenceMaterializer`` is the sole
    boundary allowed to create/reuse the corresponding canonical N afterwards.
    """

    template_ref: Ref
    actants: tuple[tuple[ActantRole, Ref], ...]

    def __post_init__(self) -> None:
        if self.template_ref.kind is not RefKind.T:
            raise ValueError("DerivedAtomConclusion.template_ref must be T")
        roles = tuple(role for role, _ in self.actants)
        if len(set(roles)) != len(roles):
            raise ValueError("DerivedAtomConclusion actant roles must be unique")

    @classmethod
    def from_mapping(
        cls,
        template_ref: Ref,
        actants: Mapping[ActantRole, Ref],
    ) -> "DerivedAtomConclusion":
        return cls(
            template_ref,
            tuple(sorted(actants.items(), key=lambda item: item[0].value)),
        )

    def role_map(self) -> dict[ActantRole, Ref]:
        return dict(self.actants)


class RuntimeGroundFormulaReasoner(GroundFormulaReasoner):
    """Ground a quantified implication against a runtime atomic query target.

    ``GroundFormulaReasoner`` already implements the sound FORALL/IMPLIES binding
    machinery for an existing zero-occurrence canonical target N.  Ordinary EXISTS
    queries intentionally do not create such an N merely by being asked.  This
    adapter supplies an ephemeral Hypernode only for unification, reusing the same
    reverse T/function indexes and antecedent proof machinery.  Nothing is inserted
    into AH during search.
    """

    def solve_ground_atom(
        self,
        template_ref: Ref,
        known_roles: Mapping[ActantRole, Ref],
        *,
        depth: int = 0,
    ) -> InferenceOutcome | None:
        if template_ref.kind is not RefKind.T:
            return None
        try:
            template = self.core.store.get_template(template_ref.uid)
        except KeyError:
            return None

        # A yes/no ground atom must bind every role of the target T.  Partial EXISTS
        # has existentially open fillers and requires a different witness contract;
        # do not silently universal-instantiate it here.
        if set(known_roles) != set(template.roles):
            return None
        if any(not isinstance(ref, Ref) for ref in known_roles.values()):
            return None

        ground = Hypernode(
            uid="__RUNTIME_GROUND_ATOM__",
            weight=0.0,
            template=template_ref,
            actants=dict(known_roles),
            properties={},
            meta={},
        )
        patterns = tuple(self.core.store.find_hypernodes_by_template(template_ref.uid))
        if self.runtime is not None:
            self.runtime.memory_query(
                "RULE_HEAD_TEMPLATE",
                f"T={template_ref.uid}|runtime_ground_atom",
                logical_depth=depth,
                focus_ref=template_ref,
                candidate_count=len(patterns),
                detail="backward quantified rule-head lookup for a non-materialized query atom",
            )

        for pattern in patterns:
            if not self._has_bound_actants(pattern):
                continue
            pattern_ref = self.core.ref(pattern.uid)
            for implication in self.core.store.function_parents(pattern.uid):
                try:
                    canonical = self.core.function_registry.canonical_id(implication.function_id)
                except KeyError:
                    continue
                if canonical != "IMPLIES" or len(implication.operands) != 2:
                    continue
                antecedent, consequent = implication.operands
                if consequent != pattern_ref or not isinstance(antecedent, Ref):
                    continue
                implication_ref = self.core.ref(implication.uid)

                for chain in self._quantifier_parent_chains(implication_ref):
                    if not chain:
                        continue
                    outer_ref, outer_obj, _ = chain[0]
                    if not self._asserted_function(outer_ref, outer_obj):
                        continue

                    env = BindingEnvironment()
                    for _qref, _qobj, variable in chain:
                        env = env.child(variable)
                    matched = self._match_pattern_node(pattern, ground, env)
                    if matched is None:
                        continue

                    self._focus(outer_ref, depth)
                    antecedent_proofs = self._prove_bound(
                        antecedent,
                        matched,
                        depth=depth + 1,
                        stack=(implication_ref.uid,),
                    )
                    if not antecedent_proofs:
                        continue
                    proof = antecedent_proofs[0]
                    self._focus(implication_ref, depth + 1)
                    self._focus(pattern_ref, depth + 1)
                    quantifier_refs = tuple(item[0] for item in chain)
                    premises = self._merge_refs(
                        proof.premise_refs,
                        quantifier_refs,
                        (implication_ref,),
                    )
                    trace = (
                        *proof.uid_trace,
                        *quantifier_refs,
                        implication_ref,
                        pattern_ref,
                        template_ref,
                    )
                    logical_depth = max(proof.logical_depth + 1, depth + 1)
                    if self.runtime is not None:
                        self.runtime.rule(
                            "FORALL_IMPLIES_MP",
                            logical_depth=logical_depth,
                            detail="runtime-ground quantified modus ponens",
                        )
                    conclusion = DerivedAtomConclusion.from_mapping(
                        template_ref,
                        known_roles,
                    )
                    return InferenceOutcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        conclusion,  # type: ignore[arg-type]
                        premises,
                        trace,
                        domain_from_premises(self.core, premises) if premises else None,
                        self.state.expanded,
                        ("FORALL-instantiated IMPLIES modus ponens for runtime ground atom",),
                        logical_depth=logical_depth,
                        proof_support=(
                            ProofSupport(premises, rule_id="FORALL_IMPLIES_MP"),
                        ),
                        bindings=proof.bindings.copy(),
                        proof_context=self.proof_context,
                    )
        return None


class QuantifiedExistsInferenceEngine(EntityIdentityInferenceEngine):
    """Production inference engine with quantified derivation for precise EXISTS."""

    def _exists(
        self,
        goal: ExistsGoal,
        query: InferenceQuery,
        attention: InferenceAttention | None,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        direct = super()._exists(
            goal,
            query,
            attention,
            proof_context=proof_context,
            runtime=runtime,
        )
        if direct.status is not LogicalStatus.UNKNOWN:
            return direct

        reasoner = RuntimeGroundFormulaReasoner(
            self.core,
            self.settings,
            query,
            attention=attention,
            proof_context=proof_context,
            runtime=runtime,
        )
        derived = reasoner.solve_ground_atom(goal.template_ref, goal.known_roles)
        return direct if derived is None else derived


class QuantifiedInferenceMaterializer(_BaseInferenceMaterializer):
    """Materialize only a final proved runtime ground atom, never search states."""

    def materialize(self, outcome: InferenceOutcome) -> MaterializationResult:
        conclusion = outcome.conclusion
        if not (
            outcome.status is LogicalStatus.PROVED
            and isinstance(conclusion, DerivedAtomConclusion)
        ):
            return super().materialize(outcome)
        if outcome.proof_context is not None and outcome.proof_context.is_counterfactual():
            return MaterializationResult(None, None, False)

        domain = (
            domain_from_premises(self.core, outcome.premise_refs)
            if outcome.premise_refs
            else self.core.store.domain_of(conclusion.template_ref.uid)
        )
        if domain not in {Domain.C, Domain.P}:
            domain = Domain.C
        node, created = self.core.add_hypernode(
            domain,
            conclusion.template_ref,
            conclusion.role_map(),
            self.integration.initial_hypernode_weight,
            count_occurrence=False,
        )
        ref = self.core.ref(node.uid)
        for support in outcome.proof_support:
            self.core.add_support(
                ref,
                SupportRecord(
                    premise_refs=support.premise_refs,
                    rule_id=support.rule_id,
                    relation_id=support.relation_id,
                ),
            )
        return MaterializationResult(ref, domain, created)
