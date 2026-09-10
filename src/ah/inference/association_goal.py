from __future__ import annotations

from dataclasses import dataclass, replace

from ah.agent import InteractionContext
from ah.integration.contracts import IntegrationCommit
from ah.integration.entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)
from ah.model import Ref
from ah.perception import (
    ActRelationCandidate,
    CommandCandidate,
    PerceptionResult,
    QueryCandidate,
)

from .contracts import AssociationGoal
from .modal_dispatch import ModalTurnGoalCompiler
from .query_builder import QueryBuildResult


@dataclass(frozen=True, slots=True)
class AssociationQueryBuildResult(QueryBuildResult):
    """GoalCompiler result executed by AssociationCoordinator, never InferenceEngine."""

    association_goal: AssociationGoal | None = None


class AssociationTurnGoalCompiler(ModalTurnGoalCompiler):
    """Compile typed ASSOCIATION act relations into AssociationGoal(A, B).

    Perception owns the semantic decision that the user requested associative
    convergence and supplies only endpoint roles. This compiler performs deterministic
    canonical entity resolution. It never recognizes lexical markers, never scans the
    graph for a plausible pair and never creates a missing entity merely to formulate
    a search goal.
    """

    def _resolve_association_root(
        self,
        root: QueryCandidate | CommandCandidate,
        relation: ActRelationCandidate,
        context: InteractionContext,
        attention_refs: tuple[Ref, ...] = (),
    ) -> AssociationQueryBuildResult:
        by_role = {item.role: item for item in root.actants}
        source_candidate = by_role.get(relation.source_role)
        target_candidate = by_role.get(relation.target_role)
        if source_candidate is None or target_candidate is None:
            return AssociationQueryBuildResult(
                None,
                ("semantic:association_endpoint_missing",),
            )

        resolver = EntityResolver(self.core)
        endpoints: list[Ref] = []
        attention: list[Ref] = []
        seen: set[tuple[str, str]] = set()

        def add_attention(ref: Ref) -> None:
            key = (ref.kind.value, ref.uid)
            if key not in seen:
                seen.add(key)
                attention.append(ref)

        for ref in attention_refs:
            add_attention(ref)

        for candidate in (source_candidate, target_candidate):
            # The point-6 Perception contract currently admits explicit entity-like
            # endpoint actants only. A local proposition ref must not be reinterpreted
            # as an entity by the ordinary resolver.
            if candidate.candidate_ref is not None or candidate.proposition is not None:
                return AssociationQueryBuildResult(
                    None,
                    (
                        "semantic:association_endpoint_proposition_not_supported:"
                        f"{candidate.role.value}",
                    ),
                )
            resolved = resolver.resolve(
                candidate,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
                attention_refs=attention_refs,
            )
            if not isinstance(resolved, ExistingEntity):
                if isinstance(resolved, AmbiguousEntityPlan):
                    diagnostic = (
                        f"semantic:association_endpoint_ambiguous:{candidate.role.value}:"
                        f"{len(resolved.candidates)}"
                    )
                elif isinstance(resolved, EquivalentLiteralPlan):
                    diagnostic = (
                        "semantic:association_endpoint_literal_not_canonicalized:"
                        f"{candidate.role.value}"
                    )
                elif isinstance(resolved, NewEntityPlan):
                    diagnostic = (
                        f"semantic:association_endpoint_not_found:{candidate.role.value}"
                    )
                else:
                    diagnostic = (
                        f"semantic:association_endpoint_unresolved:{candidate.role.value}"
                    )
                return AssociationQueryBuildResult(None, (diagnostic,))
            endpoints.append(resolved.ref)
            add_attention(resolved.ref)
            for support in resolved.support_refs:
                add_attention(support)

        if endpoints[0] == endpoints[1]:
            return AssociationQueryBuildResult(
                None,
                ("semantic:association_endpoints_identical",),
                tuple(attention),
            )

        goal = AssociationGoal(endpoints[0], endpoints[1])
        return AssociationQueryBuildResult(
            None,
            ("semantic:association_goal",),
            tuple(attention),
            association_goal=goal,
        )

    def _resolve_query_relation(
        self,
        query: QueryCandidate,
        relation: ActRelationCandidate,
        context: InteractionContext,
        attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        if relation.canonical_relation_id == "ASSOCIATION":
            return self._resolve_association_root(
                query, relation, context, attention_refs
            )
        return super()._resolve_query_relation(
            query, relation, context, attention_refs
        )

    def build(
        self,
        integration: IntegrationCommit,
        context: InteractionContext,
        perception: PerceptionResult | None = None,
        attention_refs: tuple[Ref, ...] = (),
    ) -> tuple[QueryBuildResult, ...]:
        if perception is None:
            return super().build(
                integration,
                context,
                perception=None,
                attention_refs=attention_refs,
            )

        association_relations = {
            item.act_ref: item
            for item in perception.act_relations
            if item.canonical_relation_id == "ASSOCIATION"
        }
        association_command_ids = {
            item.local_id
            for item in perception.commands
            if item.local_id in association_relations and not item.quoted
        }

        # Base SemanticGoalCompiler does not execute bare commands, while commands
        # with embedded content may create ordinary inference goals. Once Perception
        # has typed the command itself as ASSOCIATION, remove that root from base
        # dispatch so its descendants cannot accidentally become a second proof goal.
        base_perception = (
            perception
            if not association_command_ids
            else replace(
                perception,
                commands=tuple(
                    item
                    for item in perception.commands
                    if item.local_id not in association_command_ids
                ),
            )
        )
        results = list(
            super().build(
                integration,
                context,
                base_perception,
                attention_refs=attention_refs,
            )
        )

        for command in perception.commands:
            relation = association_relations.get(command.local_id)
            if relation is None or command.quoted:
                continue
            results.append(
                self._resolve_association_root(
                    command, relation, context, attention_refs
                )
            )
        return tuple(results)
