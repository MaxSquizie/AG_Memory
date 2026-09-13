from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from ah.agent import InteractionContext
from ah.integration.entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)
from ah.model import ActantRole, Ref
from ah.perception.query_semantics import EventSetQueryCandidate

from .attention import InferenceAttention
from .contracts import (
    CompositeConclusion,
    ExistingRefConclusion,
    GoalSpec,
    InferenceOutcome,
    InferenceQuery,
    LogicalStatus,
    ProofSupport,
    StopReason,
)
from .domain import domain_from_premises
from .modal_goal import ModalInferenceEngine
from .query_builder import QueryBuildResult, QueryGoalBuilder as _BaseQueryGoalBuilder
from .runtime import GoalRuntime
from .context import ProofContext


@dataclass(frozen=True, slots=True)
class EventMatchGoal:
    """Find asserted events satisfying role constraints with an open predicate.

    The goal intentionally has no template/predicate reference. Candidate
    generation is bounded by the store's reverse actant index, so opening the
    predicate does not authorize a global AH scan. At least one explicit role
    constraint is required.
    """

    known_roles: Mapping[ActantRole, Ref]

    def __post_init__(self) -> None:
        if not self.known_roles:
            raise ValueError("EventMatchGoal requires at least one known role constraint")
        if any(not isinstance(ref, Ref) for ref in self.known_roles.values()):
            raise ValueError("EventMatchGoal constraints must be canonical Refs")


class EventQueryGoalBuilder(_BaseQueryGoalBuilder):
    """Compile an EventSetQueryCandidate without binding it to one predicate T."""

    def build(
        self,
        query,
        context: InteractionContext,
        identity_attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        if not isinstance(query, EventSetQueryCandidate):
            return super().build(query, context, identity_attention_refs)

        resolver = EntityResolver(self.core)
        known: dict[ActantRole, Ref] = {}
        attention: list[Ref] = []
        seen_attention: set[tuple[str, str]] = set()

        def add_attention(ref: Ref) -> None:
            key = (ref.kind.value, ref.uid)
            if key not in seen_attention:
                seen_attention.add(key)
                attention.append(ref)

        for actant in query.actants:
            if actant.candidate_ref is not None or actant.proposition is not None:
                return QueryBuildResult(
                    None,
                    ("event_query_structured_actant_not_supported",),
                )
            resolution = resolver.resolve(
                actant,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
                attention_refs=identity_attention_refs,
            )
            if not isinstance(resolution, ExistingEntity):
                if isinstance(resolution, AmbiguousEntityPlan):
                    diagnostic = (
                        f"event_query_ambiguous_actant:{actant.role.value}:"
                        f"{len(resolution.candidates)}"
                    )
                elif isinstance(resolution, EquivalentLiteralPlan):
                    diagnostic = (
                        f"event_query_literal_not_canonicalized:{actant.role.value}"
                    )
                elif isinstance(resolution, NewEntityPlan):
                    diagnostic = f"event_query_actant_not_found:{actant.role.value}"
                else:
                    diagnostic = f"event_query_unresolved_actant:{actant.role.value}"
                return QueryBuildResult(None, (diagnostic,))
            known[actant.role] = resolution.ref
            add_attention(resolution.ref)
            for support in resolution.support_refs:
                add_attention(support)

        if not known:
            return QueryBuildResult(None, ("event_query_requires_known_constraints",))
        return QueryBuildResult(
            InferenceQuery(
                GoalSpec(
                    EventMatchGoal(known),
                    request_all_proofs=True,
                )
            ),
            ("semantic:open_event_match",),
            tuple(attention),
        )


class EventSetInferenceEngine(ModalInferenceEngine):
    """Inference extension for indexed open-predicate factual event retrieval."""

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
        if isinstance(goal, EventMatchGoal):
            return self._event_match(
                goal,
                query,
                proof_context=proof_context,
                runtime=runtime,
            )
        return super()._solve_goal(
            goal,
            query,
            workspace_refs,
            attention,
            proof_context=proof_context,
            runtime=runtime,
        )

    def _event_match(
        self,
        goal: EventMatchGoal,
        query: InferenceQuery,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        _max_depth, budget = self._limits(query)

        buckets: list[set[str]] = []
        for role, ref in sorted(goal.known_roles.items(), key=lambda item: item[0].value):
            runtime.focus(
                ref,
                logical_depth=0,
                reason=f"open-event constraint {role.value}",
            )
            nodes = self.core.store.hypernodes_for_actant(ref.uid)
            runtime.memory_query(
                "ACTANT_FACTS",
                f"{role.value}={ref.uid}",
                logical_depth=0,
                focus_ref=ref,
                candidate_count=len(nodes),
                detail="reverse actant index lookup; no global AH scan",
            )
            buckets.append({node.uid for node in nodes})

        candidate_uids = set.intersection(*buckets) if buckets else set()
        if len(candidate_uids) > budget:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.BUDGET_EXHAUSTED,
                None,
                (),
                (),
                None,
                len(candidate_uids),
                (
                    f"Open-event candidate set {len(candidate_uids)} exceeds proof budget {budget}; "
                    "partial event lists are not returned",
                ),
                proof_context=proof_context,
            )

        def creation_key(uid: str) -> tuple[int, str]:
            try:
                return self.core.store.creation_sequence(uid), uid
            except KeyError:
                return 10**18, uid

        matched: list[Ref] = []
        conflicted: list[Ref] = []
        expanded = 0
        for uid in sorted(candidate_uids, key=creation_key):
            expanded += 1
            try:
                node = self.core.store.get_hypernode(uid)
            except (KeyError, TypeError):
                continue
            # H dialogue occurrences and proposition content mentioned under a
            # non-factual scope are not world-event answers.
            if bool(node.meta.get("event_instance", False)) or node.meta.get("semantic_scope"):
                continue
            if not all(
                node.actants.get(role) == ref
                for role, ref in goal.known_roles.items()
            ):
                continue
            fact_ref = self.core.ref(uid)
            if self.conflicts.is_conflicted(fact_ref):
                conflicted.append(fact_ref)
                continue
            if self._false_wrapper(uid) is not None:
                continue
            matched.append(fact_ref)

        conflict = self._conflict_outcome(
            tuple(conflicted),
            expanded=expanded,
            logical_depth=0,
        )
        if conflict is not None:
            return replace(conflict, proof_context=proof_context)

        if not matched:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                None,
                expanded,
                ("No asserted event satisfies all open-event role constraints",),
                proof_context=proof_context,
            )

        for ref in matched:
            runtime.focus(ref, logical_depth=0, reason="open-event factual witness")
        runtime.rule(
            "EVENT_MATCH",
            logical_depth=0,
            detail=f"{len(matched)} complete factual witness(es)",
        )

        conclusions = tuple(ExistingRefConclusion(ref) for ref in matched)
        conclusion = (
            conclusions[0]
            if len(conclusions) == 1
            else CompositeConclusion(conclusions)
        )
        premises = tuple(matched)
        supports = tuple(
            ProofSupport((ref,), rule_id="EVENT_MATCH")
            for ref in matched
        )
        return InferenceOutcome(
            LogicalStatus.PROVED,
            StopReason.GOAL_SATISFIED,
            conclusion,
            premises,
            premises,
            domain_from_premises(self.core, premises),
            expanded,
            (f"Resolved {len(matched)} asserted event witness(es) by role constraints",),
            logical_depth=0,
            proof_support=supports,
            proof_context=proof_context,
        )
