from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.integration.entity_resolver import (
    AmbiguousEntityPlan,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)
from ah.integration.identity_entity_resolver import IdentityAwareEntityResolver
from ah.integration.identity_graph import identity_name_refs_for_owner, identity_name_text
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
from .event_query import EventSetInferenceEngine
from .identity_event_query import IdentityAwareEventQueryGoalBuilder
from .query_builder import QueryBuildResult
from .runtime import GoalRuntime
from .context import ProofContext


@dataclass(frozen=True, slots=True)
class EntityIdentityGoal:
    """Read explicit canonical identity-name semantics for one entity M."""

    target: Ref

    def __post_init__(self) -> None:
        if self.target.kind is not RefKind.M:
            raise ValueError("EntityIdentityGoal.target must be canonical M")


class EntityIdentityQueryGoalBuilder(IdentityAwareEventQueryGoalBuilder):
    """Resolve one typed identity-query target through canonical name graph edges."""

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
        resolver = IdentityAwareEntityResolver(self.core)
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
            ("semantic:entity_identity", "semantic:identity_name_graph"),
            tuple(attention),
        )


class EntityIdentityInferenceEngine(EventSetInferenceEngine):
    """Inference extension for explicit canonical entity-name relations."""

    @staticmethod
    def _append_unique(values: list[str], value: object) -> None:
        text = str(value).strip()
        if text and text.casefold() not in {old.casefold() for old in values}:
            values.append(text)

    def _identity_labels(self, ref: Ref, entity: SemanticEntity) -> tuple[tuple[str, ...], tuple[Ref, ...]]:
        values: list[str] = []
        name = entity.properties.get("name")
        if name is not None:
            self._append_unique(values, name.value)
        aliases = entity.properties.get("aliases")
        if aliases is not None:
            raw_aliases = aliases.value
            items = (
                raw_aliases
                if isinstance(raw_aliases, (tuple, list, set, frozenset))
                else (raw_aliases,)
            )
            for item in items:
                self._append_unique(values, item)

        explicit_refs = identity_name_refs_for_owner(self.core, ref)
        for name_ref in explicit_refs:
            try:
                name_entity = self.core.store.get_element_any_domain(name_ref.uid)
            except KeyError:
                continue
            if not isinstance(name_entity, SemanticEntity):
                continue
            value = identity_name_text(name_entity)
            if value is not None:
                self._append_unique(values, value)
        return tuple(values), explicit_refs

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

        labels, explicit_name_refs = self._identity_labels(goal.target, entity)
        runtime.memory_query(
            "ENTITY_IDENTITY",
            goal.target.uid,
            logical_depth=0,
            focus_ref=goal.target,
            candidate_count=len(labels),
            detail="read indexed IDENTITY_NAME edges plus canonical name/alias properties",
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
            detail=(
                f"{len(labels)} identifying label(s); "
                f"{len(explicit_name_refs)} explicit IDENTITY_NAME node(s)"
            ),
        )
        proof_refs = (goal.target, *explicit_name_refs)
        return InferenceOutcome(
            LogicalStatus.PROVED,
            StopReason.GOAL_SATISFIED,
            ExistingRefConclusion(goal.target),
            proof_refs,
            proof_refs,
            self.core.store.domain_of(goal.target.uid),
            1,
            ("Resolved entity identity from explicit canonical identity-name graph",),
            proof_support=(),
            proof_context=proof_context,
        )
