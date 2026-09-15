from __future__ import annotations

from dataclasses import dataclass, replace

from ah.agent.interaction_context import AssociationDiscourseSession, InteractionContext
from ah.association.history import clear_signatures, emitted_signatures
from ah.integration.contracts import IntegrationCommit
from ah.perception.association_continuation import AssociationContinuationQueryCandidate
from ah.perception.contracts import PerceptionResult

from .association_goal import AssociationQueryBuildResult, AssociationTurnGoalCompiler
from .contracts import AssociationGoal


@dataclass(frozen=True, slots=True)
class AssociationContinuationGoal(AssociationGoal):
    """AssociationGoal that excludes already returned runtime result signatures."""

    excluded_signatures: tuple[str, ...] = ()


class AssociationSessionTurnGoalCompiler(AssociationTurnGoalCompiler):
    """Add cross-turn association continuation without changing canonical AH."""

    def _resolve_association_root(
        self,
        root,
        relation,
        context: InteractionContext,
        attention_refs=(),
    ) -> AssociationQueryBuildResult:
        result = super()._resolve_association_root(
            root,
            relation,
            context,
            attention_refs,
        )
        goal = result.association_goal
        if goal is not None:
            # An explicit binary association request begins a fresh result stream.
            clear_signatures(self.core, goal.left, goal.right)
            context.association_session = AssociationDiscourseSession(goal.left, goal.right)
        return result

    def _continuation_result(
        self,
        context: InteractionContext,
        attention_refs,
    ) -> AssociationQueryBuildResult:
        session = context.association_session
        if session is None:
            return AssociationQueryBuildResult(
                None,
                ("semantic:association_continuation_without_session",),
            )
        excluded = emitted_signatures(self.core, session.left, session.right)
        goal = AssociationContinuationGoal(
            session.left,
            session.right,
            excluded_signatures=excluded,
        )
        attention = list(attention_refs)
        seen = {item.uid for item in attention}
        for ref in (session.left, session.right):
            if ref.uid not in seen:
                attention.append(ref)
                seen.add(ref.uid)
        return AssociationQueryBuildResult(
            None,
            (
                "semantic:association_continuation_goal",
                f"runtime:association_excluded_results:{len(excluded)}",
            ),
            tuple(attention),
            association_goal=goal,
        )

    def build(
        self,
        integration: IntegrationCommit,
        context: InteractionContext,
        perception: PerceptionResult | None = None,
        attention_refs=(),
    ):
        if perception is None:
            return super().build(
                integration,
                context,
                perception=None,
                attention_refs=attention_refs,
            )

        continuations = tuple(
            item
            for item in perception.queries
            if isinstance(item, AssociationContinuationQueryCandidate)
        )
        if not continuations:
            return super().build(
                integration,
                context,
                perception,
                attention_refs=attention_refs,
            )

        ordinary = replace(
            perception,
            queries=tuple(
                item
                for item in perception.queries
                if not isinstance(item, AssociationContinuationQueryCandidate)
            ),
        )
        results = list(
            super().build(
                integration,
                context,
                ordinary,
                attention_refs=attention_refs,
            )
        )
        results.extend(
            self._continuation_result(context, attention_refs)
            for _item in continuations
        )
        return tuple(results)
