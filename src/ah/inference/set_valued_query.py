from __future__ import annotations

from dataclasses import replace

from ah.agent import InteractionContext
from ah.model import Ref

from .attention import InferenceAttention
from .context import ProofContext
from .contracts import (
    CompositeConclusion,
    ExistingRefConclusion,
    InferenceOutcome,
    InferenceQuery,
    LogicalStatus,
    MultiRoleBindingConclusion,
    MultiRoleFillGoal,
    RoleBindingConclusion,
    RoleFillGoal,
    StopReason,
)
from .domain import domain_from_premises
from .identity_query import EntityIdentityQueryGoalBuilder
from .materialization import MaterializationResult
from .quantified_exists import (
    QuantifiedExistsInferenceEngine,
    QuantifiedInferenceMaterializer,
)
from .query_builder import QueryBuildResult
from .runtime import GoalRuntime


class SetValuedQueryGoalBuilder(EntityIdentityQueryGoalBuilder):
    """Mark ordinary user WH retrieval as a request for the complete binding set.

    ``request_all_proofs`` already belongs to GoalSpec and is the right semantic
    distinction here: internal RoleFillGoal callers keep first-proof behaviour,
    while a user question such as ``Что я видел во дворе?`` asks for every value
    satisfying the same formal constraints.
    """

    def build(
        self,
        query,
        context: InteractionContext,
        identity_attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        result = super().build(query, context, identity_attention_refs)
        inference_query = result.goal
        if inference_query is None:
            return result
        if not isinstance(
            inference_query.goal.target,
            (RoleFillGoal, MultiRoleFillGoal),
        ):
            return result
        if inference_query.goal.request_all_proofs:
            return result
        return replace(
            result,
            goal=replace(
                inference_query,
                goal=replace(inference_query.goal, request_all_proofs=True),
            ),
            diagnostics=tuple((*result.diagnostics, "semantic:set_valued_role_query")),
        )


class SetValuedQueryInferenceEngine(QuantifiedExistsInferenceEngine):
    """Collect all direct factual bindings only when GoalSpec explicitly asks for it."""

    @staticmethod
    def _merge_refs(*groups: tuple[Ref, ...]) -> tuple[Ref, ...]:
        out: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        for group in groups:
            for ref in group:
                key = (ref.kind.value, ref.uid)
                if key in seen:
                    continue
                seen.add(key)
                out.append(ref)
        return tuple(out)

    def _solve_goal(
        self,
        goal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        if query.goal.request_all_proofs:
            if isinstance(goal, RoleFillGoal):
                return self._role_fill_all(goal, runtime)
            if isinstance(goal, MultiRoleFillGoal):
                return self._multi_role_fill_all(goal, runtime)
        return super()._solve_goal(
            goal,
            query,
            workspace_refs,
            attention,
            proof_context=proof_context,
            runtime=runtime,
        )

    def _role_fill_all(
        self,
        goal: RoleFillGoal,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        runtime.focus(
            goal.template_ref,
            logical_depth=0,
            reason="goal-generated set-valued template query seed",
        )
        matches = self._matching_hypernodes(
            goal.template_ref.uid,
            goal.known_roles,
            runtime,
        )
        conflicted: list[Ref] = []
        conclusions: list[RoleBindingConclusion] = []
        premise_groups: list[tuple[Ref, ...]] = []
        trace_groups: list[tuple[Ref, ...]] = []
        proof_support = []
        seen_values: set[tuple[str, str]] = set()

        for node in matches:
            fact_ref = self.core.ref(node.uid)
            if self.conflicts.is_conflicted(fact_ref):
                conflicted.append(fact_ref)
                continue
            if self._false_wrapper(node.uid) is not None:
                continue
            value = node.actants.get(goal.requested_role)
            if not isinstance(value, Ref):
                continue
            value_key = (value.kind.value, value.uid)
            if value_key in seen_values:
                continue
            seen_values.add(value_key)

            runtime.focus(
                fact_ref,
                logical_depth=0,
                reason="matched factual premise for set-valued role query",
            )
            runtime.rule(
                "FACT_MATCH",
                logical_depth=0,
                detail=f"requested role={goal.requested_role.value}; collect all",
            )
            subsumption = self._actant_subsumption_support(
                node.actants,
                goal.known_roles,
            ) or ()
            premises = (fact_ref, *subsumption)
            conclusions.append(
                RoleBindingConclusion(goal.requested_role, value, fact_ref)
            )
            premise_groups.append(premises)
            trace_groups.append((fact_ref, *subsumption, value))
            proof_support.extend(
                self._proof_support(premises, rule_id="FACT_MATCH")
            )

        if conclusions:
            conclusion = (
                conclusions[0]
                if len(conclusions) == 1
                else CompositeConclusion(tuple(conclusions))
            )
            premises = self._merge_refs(*premise_groups)
            trace = self._merge_refs(*trace_groups)
            return InferenceOutcome(
                status=LogicalStatus.PROVED,
                stop_reason=StopReason.GOAL_SATISFIED,
                conclusion=conclusion,
                premise_refs=premises,
                uid_trace=trace,
                conclusion_domain=domain_from_premises(self.core, premises),
                expanded_states=len(matches),
                diagnostics=(f"set-valued role bindings:{len(conclusions)}",),
                proof_support=tuple(proof_support),
            )

        conflict = self._conflict_outcome(
            tuple(conflicted),
            expanded=len(matches),
        )
        if conflict is not None:
            return conflict
        return InferenceOutcome(
            status=LogicalStatus.UNKNOWN,
            stop_reason=StopReason.SEARCH_EXHAUSTED,
            conclusion=None,
            premise_refs=(),
            uid_trace=(),
            conclusion_domain=None,
            expanded_states=len(matches),
        )

    def _multi_role_fill_all(
        self,
        goal: MultiRoleFillGoal,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        runtime.focus(
            goal.template_ref,
            logical_depth=0,
            reason="goal-generated set-valued multi-role query seed",
        )
        matches = self._matching_hypernodes(
            goal.template_ref.uid,
            goal.known_roles,
            runtime,
        )
        conflicted: list[Ref] = []
        conclusions: list[MultiRoleBindingConclusion] = []
        premise_groups: list[tuple[Ref, ...]] = []
        trace_groups: list[tuple[Ref, ...]] = []
        proof_support = []
        seen_bindings: set[tuple[tuple[str, str, str], ...]] = set()

        for node in matches:
            fact_ref = self.core.ref(node.uid)
            if self.conflicts.is_conflicted(fact_ref):
                conflicted.append(fact_ref)
                continue
            if self._false_wrapper(node.uid) is not None:
                continue

            bindings: list[tuple] = []
            missing = False
            for role in goal.requested_roles:
                value = node.actants.get(role)
                if not isinstance(value, Ref):
                    missing = True
                    break
                bindings.append((role, value))
            if missing:
                continue
            signature = tuple(
                (role.value, value.kind.value, value.uid)
                for role, value in bindings
            )
            if signature in seen_bindings:
                continue
            seen_bindings.add(signature)

            runtime.focus(
                fact_ref,
                logical_depth=0,
                reason="matched factual premise for set-valued multi-role query",
            )
            runtime.rule(
                "FACT_MATCH",
                logical_depth=0,
                detail="multi-role binding; collect all",
            )
            subsumption = self._actant_subsumption_support(
                node.actants,
                goal.known_roles,
            ) or ()
            premises = (fact_ref, *subsumption)
            conclusions.append(
                MultiRoleBindingConclusion(tuple(bindings), fact_ref)
            )
            premise_groups.append(premises)
            trace_groups.append(
                (fact_ref, *subsumption, *(value for _role, value in bindings))
            )
            proof_support.extend(
                self._proof_support(premises, rule_id="FACT_MATCH")
            )

        if conclusions:
            conclusion = (
                conclusions[0]
                if len(conclusions) == 1
                else CompositeConclusion(tuple(conclusions))
            )
            premises = self._merge_refs(*premise_groups)
            trace = self._merge_refs(*trace_groups)
            return InferenceOutcome(
                status=LogicalStatus.PROVED,
                stop_reason=StopReason.GOAL_SATISFIED,
                conclusion=conclusion,
                premise_refs=premises,
                uid_trace=trace,
                conclusion_domain=domain_from_premises(self.core, premises),
                expanded_states=len(matches),
                diagnostics=(f"set-valued multi-role bindings:{len(conclusions)}",),
                proof_support=tuple(proof_support),
            )

        conflict = self._conflict_outcome(
            tuple(conflicted),
            expanded=len(matches),
        )
        if conflict is not None:
            return conflict
        return InferenceOutcome(
            status=LogicalStatus.UNKNOWN,
            stop_reason=StopReason.SEARCH_EXHAUSTED,
            conclusion=None,
            premise_refs=(),
            uid_trace=(),
            conclusion_domain=None,
            expanded_states=len(matches),
        )


class SetValuedInferenceMaterializer(QuantifiedInferenceMaterializer):
    """Keep multi-binding retrieval read-only; it creates no synthetic semantic node."""

    def materialize(self, outcome: InferenceOutcome) -> MaterializationResult:
        conclusion = outcome.conclusion
        if (
            outcome.status is LogicalStatus.PROVED
            and isinstance(conclusion, CompositeConclusion)
            and conclusion.conclusions
            and all(
                isinstance(
                    item,
                    (
                        ExistingRefConclusion,
                        RoleBindingConclusion,
                        MultiRoleBindingConclusion,
                    ),
                )
                for item in conclusion.conclusions
            )
        ):
            domain = (
                domain_from_premises(self.core, outcome.premise_refs)
                if outcome.premise_refs
                else outcome.conclusion_domain
            )
            return MaterializationResult(None, domain, False)
        return super().materialize(outcome)
