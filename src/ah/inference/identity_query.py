from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.integration.entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)
from ah.model import Ref, RefKind, SemanticEntity
from ah.perception.query_semantics import EntityIdentityQueryCandidate

from .attention import InferenceAttention
from .contracts import (
    ExistingRefConclusion,
    GoalSpec,
    InferenceOutcome,
    InferenceQuery,
    LogicalStatus,
    StopReason,
)
from .event_query import EventQueryGoalBuilder, EventSetInferenceEngine
from .query_builder import QueryBuildResult
from .runtime import GoalRuntime
from .context import ProofContext


@dataclass(frozen=True, slots=True)
class EntityIdentityGoal:
    """Read the canonical identifying labels already attached to one entity M."""

    target: Ref

    def __post_init__(self) -> None:
        if self.target.kind is not RefKind.M:
            raise ValueError("EntityIdentityGoal.target must be canonical M")


class EntityIdentityQueryGoalBuilder(EventQueryGoalBuilder):
    """Resolve one typed identity-query target without interpreting its copular shell."""

    def build(
        self,
        query,
        context: InteractionContext,
        identity_attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        if not isinstance(query, EntityIdentityQueryCandidate):
            return super().build(query, context, identity_attention_refs)

        target = query.target
        if target is None:
            return QueryBuildResult(None, ("entity_identity_target_missing",))
        resolver = EntityResolver(self.core)
        resolution = resolver.resolve(
            target,
            context,
            first_person_ref=context.user_ref,
            second_person_ref=context.self_ref,
            attention_refs=identity_attention_refs,
        )
        if not isinstance(resolution, ExistingEntity):
            if isinstance(resolution, AmbiguousEntityPlan):
                diagnostic = f"entity_identity_target_ambiguous:{len(resolution.candidates)}"
            elif isinstance(resolution, EquivalentLiteralPlan):
                diagnostic = "entity_identity_target_literal_not_canonicalized"
            elif isinstance(resolution, NewEntityPlan):
                diagnostic = "entity_identity_target_not_found"
            else:
                diagnostic = "entity_identity_target_unresolved"
            return QueryBuildResult(None, (diagnostic,))
        if resolution.ref.kind is not RefKind.M:
            return QueryBuildResult(None, ("entity_identity_target_not_entity",))

        attention: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        for ref in (resolution.ref, *resolution.support_refs):
            key = (ref.kind.value, ref.uid)
            if key in seen:
                continue
            seen.add(key)
            attention.append(ref)
        return QueryBuildResult(
            InferenceQuery(GoalSpec(EntityIdentityGoal(resolution.ref))),
            ("semantic:entity_identity",),
            tuple(attention),
        )


class EntityIdentityInferenceEngine(EventSetInferenceEngine):
    """Inference extension for canonical entity-name/alias retrieval."""

    @staticmethod
    def _identity_labels(entity: SemanticEntity) -> tuple[str, ...]:
        values: list[str] = []
        name = entity.properties.get("name")
        if name is not None:
            raw = str(name.value).strip()
            if raw:
                values.append(raw)
        aliases = entity.properties.get("aliases")
        if aliases is not None:
            raw_aliases = aliases.value
            items = (
                raw_aliases
                if isinstance(raw_aliases, (tuple, list, set, frozenset))
                else (raw_aliases,)
            )
            for item in items:
                value = str(item).strip()
                if value and value.casefold() not in {old.casefold() for old in values}:
                    values.append(value)
        return tuple(values)

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
        if isinstance(goal, EntityIdentityGoal):
            return self._entity_identity(
                goal,
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

    def _entity_identity(
        self,
        goal: EntityIdentityGoal,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        runtime.focus(goal.target, logical_depth=0, reason="entity identity target")
        try:
            entity = self.core.store.get_element_any_domain(goal.target.uid)
        except KeyError:
            entity = None
        if not isinstance(entity, SemanticEntity):
            runtime.memory_query(
                "ENTITY_IDENTITY",
                goal.target.uid,
                logical_depth=0,
                focus_ref=goal.target,
                candidate_count=0,
                detail="target M is unavailable",
            )
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (goal.target,),
                None,
                1,
                ("Canonical identity target is unavailable",),
                proof_context=proof_context,
            )

        labels = self._identity_labels(entity)
        runtime.memory_query(
            "ENTITY_IDENTITY",
            goal.target.uid,
            logical_depth=0,
            focus_ref=goal.target,
            candidate_count=len(labels),
            detail="read canonical name/aliases properties; no graph scan",
        )
        if not labels:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (goal.target,),
                (goal.target,),
                self.core.store.domain_of(goal.target.uid),
                1,
                ("Entity has no asserted canonical identity label",),
                proof_context=proof_context,
            )

        runtime.rule(
            "ENTITY_IDENTITY",
            logical_depth=0,
            detail=f"{len(labels)} canonical identifying label(s)",
        )
        return InferenceOutcome(
            LogicalStatus.PROVED,
            StopReason.GOAL_SATISFIED,
            ExistingRefConclusion(goal.target),
            (goal.target,),
            (goal.target,),
            self.core.store.domain_of(goal.target.uid),
            1,
            ("Resolved entity identity from canonical name/aliases",),
            # Retrieval of properties from the target M does not derive a new
            # canonical object, so materialization has no dependency support to add.
            proof_support=(),
            proof_context=proof_context,
        )
