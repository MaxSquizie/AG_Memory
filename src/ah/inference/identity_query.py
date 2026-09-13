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
from ah.model import ActantRole, Domain, Ref, RefKind, SemanticEntity
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
    """Describe one canonical entity from explicit identity/classification evidence."""

    target: Ref

    def __post_init__(self) -> None:
        if self.target.kind is not RefKind.M:
            raise ValueError("EntityIdentityGoal.target must be canonical M")


class EntityIdentityQueryGoalBuilder(IdentityAwareEventQueryGoalBuilder):
    """Resolve one typed identity-query target through canonical entity semantics."""

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
            ("semantic:entity_identity", "semantic:identity_or_description"),
            tuple(attention),
        )


class EntityIdentityInferenceEngine(EventSetInferenceEngine):
    """Inference extension for explicit identity names and factual class descriptors.

    ``Кто X?`` is not merely a request to echo X's lexical label.  A useful answer
    requires canonical evidence that identifies/describes the entity: an explicit
    IDENTITY_NAME edge or an asserted unary conceptual proposition such as
    ``студент(SUBJECT=Алексей)``.  Descriptor lookup is reverse-indexed from the
    target M and therefore does not scan the AH.
    """

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

    def _descriptor_refs(self, target: Ref, runtime: GoalRuntime) -> tuple[Ref, ...]:
        """Return asserted unary C-domain descriptions whose SUBJECT is target."""
        candidates = tuple(self.core.store.hypernodes_for_actant(target.uid))
        runtime.memory_query(
            "ENTITY_DESCRIPTORS",
            f"subject={target.uid}",
            logical_depth=0,
            focus_ref=target,
            candidate_count=len(candidates),
            detail="reverse actant index; only asserted unary conceptual SUBJECT facts qualify",
        )
        out: list[Ref] = []
        for node in candidates:
            if self.core.store.domain_of(node.uid) is not Domain.C:
                continue
            if node.meta.get("semantic_scope"):
                continue
            if int(node.meta.get("occurrence_count", 0)) <= 0:
                continue
            if node.actants.get(ActantRole.SUBJECT) != target:
                continue
            try:
                template = self.core.store.get_template(node.template.uid)
            except KeyError:
                continue
            if tuple(template.roles) != (ActantRole.SUBJECT,):
                continue
            ref = self.core.ref(node.uid)
            if self.conflicts.is_conflicted(ref) or self._false_wrapper(node.uid) is not None:
                continue
            out.append(ref)
        out.sort(key=lambda ref: self.core.store.creation_sequence(ref.uid))
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
        descriptor_refs = self._descriptor_refs(goal.target, runtime)
        runtime.memory_query(
            "ENTITY_IDENTITY",
            goal.target.uid,
            logical_depth=0,
            focus_ref=goal.target,
            candidate_count=len(explicit_name_refs) + len(descriptor_refs),
            detail="explicit IDENTITY_NAME support plus asserted unary conceptual descriptions",
        )

        # A primary ``name`` property alone merely lets lexical resolution find the
        # entity.  It is not by itself an answer to "who/what is X?"; otherwise any
        # freshly mentioned unknown entity would tautologically identify itself.
        if not explicit_name_refs and not descriptor_refs:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (goal.target,),
                (goal.target,),
                self.core.store.domain_of(goal.target.uid),
                1,
                ("Entity is addressable but has no asserted identity/classification evidence",),
                proof_context=proof_context,
            )

        for ref in (*explicit_name_refs, *descriptor_refs):
            runtime.focus(ref, logical_depth=0, reason="entity identity/description support")
        runtime.rule(
            "ENTITY_IDENTITY",
            logical_depth=0,
            detail=(
                f"labels={len(labels)}; explicit_names={len(explicit_name_refs)}; "
                f"descriptors={len(descriptor_refs)}"
            ),
        )
        proof_refs = (goal.target, *explicit_name_refs, *descriptor_refs)
        return InferenceOutcome(
            LogicalStatus.PROVED,
            StopReason.GOAL_SATISFIED,
            ExistingRefConclusion(goal.target),
            proof_refs,
            proof_refs,
            self.core.store.domain_of(goal.target.uid),
            1,
            ("Resolved entity identity/description from explicit canonical evidence",),
            proof_support=(),
            proof_context=proof_context,
        )