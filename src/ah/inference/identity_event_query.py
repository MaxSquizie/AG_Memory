from __future__ import annotations

from ah.agent import InteractionContext
from ah.integration.entity_resolver import (
    AmbiguousEntityPlan,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)
from ah.integration.identity_entity_resolver import IdentityAwareEntityResolver
from ah.model import ActantRole, Ref
from ah.perception.query_semantics import EventSetQueryCandidate

from .contracts import GoalSpec, InferenceQuery
from .event_query import EventMatchGoal, EventQueryGoalBuilder
from .query_builder import QueryBuildResult


class IdentityAwareEventQueryGoalBuilder(EventQueryGoalBuilder):
    """Compile open-event constraints through explicit identity-name graph edges."""

    def build(
        self,
        query,
        context: InteractionContext,
        identity_attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        if not isinstance(query, EventSetQueryCandidate):
            return super().build(query, context, identity_attention_refs)

        resolver = IdentityAwareEntityResolver(self.core)
        known: dict[ActantRole, Ref] = {}
        attention: list[Ref] = []
        seen_attention: set[tuple[str, str]] = set()

        def add_attention(ref: Ref) -> None:
            # L is structural/non-excitable; IdentityAwareEntityResolver deliberately
            # returns the excitable name M as support rather than the L itself.
            key = (ref.kind.value, ref.uid)
            if key not in seen_attention:
                seen_attention.add(key)
                attention.append(ref)

        for actant in query.actants:
            if actant.role is ActantRole.TIME and actant.temporal is not None:
                time_ref, diagnostic = self._temporal_constraint(actant)
                if diagnostic is not None or time_ref is None:
                    return QueryBuildResult(
                        None,
                        (diagnostic or "event_query_temporal_unresolved",),
                    )
                known[ActantRole.TIME] = time_ref
                add_attention(time_ref)
                continue

            if (
                actant.candidate_ref is not None
                or actant.proposition is not None
                or actant.composition is not None
                or actant.entity_ref is not None
            ):
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
            ("semantic:open_event_match", "semantic:identity_name_graph"),
            tuple(attention),
        )
