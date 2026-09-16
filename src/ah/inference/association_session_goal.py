from __future__ import annotations

from dataclasses import dataclass, replace

from ah.agent.interaction_context import AssociationDiscourseSession, InteractionContext
from ah.association.history import clear_signatures, emitted_signatures
from ah.integration.contracts import IntegrationCommit
from ah.model import ActantRole, Ref, RefKind
from ah.perception.association_continuation import AssociationContinuationQueryCandidate
from ah.perception.contracts import PerceptionResult

from .association_goal import AssociationQueryBuildResult, AssociationTurnGoalCompiler
from .contracts import AssociationGoal


@dataclass(frozen=True, slots=True)
class AssociationConstraint:
    """One explicit typed restriction on supporting association facts.

    The restriction is runtime query structure, not a newly asserted proposition.
    A supporting fact must contain this role with the requested canonical value (or
    a value subsumed by it through canonical IS-A) to participate in the answer.
    """

    role: ActantRole
    value: Ref

    def __post_init__(self) -> None:
        if self.value.kind is RefKind.L:
            raise ValueError("AssociationConstraint.value cannot be L")


@dataclass(frozen=True, slots=True)
class AssociationScopedGoal(AssociationGoal):
    constraints: tuple[AssociationConstraint, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        roles = tuple(item.role for item in self.constraints)
        if len(set(roles)) != len(roles):
            raise ValueError("AssociationScopedGoal constraint roles must be unique")
        ordered = tuple(
            sorted(
                self.constraints,
                key=lambda item: (item.role.value, item.value.kind.value, item.value.uid),
            )
        )
        object.__setattr__(self, "constraints", ordered)


@dataclass(frozen=True, slots=True)
class AssociationContinuationGoal(AssociationScopedGoal):
    """Scoped AssociationGoal that excludes already returned result signatures."""

    excluded_signatures: tuple[str, ...] = ()


class AssociationSessionTurnGoalCompiler(AssociationTurnGoalCompiler):
    """Add typed search scope and cross-turn association continuation."""

    # These roles express restrictions on *where/when/how/under what conditions*
    # the commonality must be supported. STATE is intentionally absent: commonality
    # questions are commonly parsed as BE(STATE=common, ...), and that shell is the
    # query operator rather than a memory restriction.
    _CONSTRAINT_ROLES = frozenset(
        {
            ActantRole.LOCATION,
            ActantRole.TIME,
            ActantRole.DURATION,
            ActantRole.CAUSE,
            ActantRole.PURPOSE,
            ActantRole.TOOL,
            ActantRole.MATERIAL,
            ActantRole.AMOUNT,
            ActantRole.HOW_TO,
        }
    )

    @staticmethod
    def _session_constraints(goal: AssociationScopedGoal) -> tuple[tuple[ActantRole, Ref], ...]:
        return tuple((item.role, item.value) for item in goal.constraints)

    def _resolve_constraints(
        self,
        root,
        context: InteractionContext,
        attention_refs,
    ) -> tuple[tuple[AssociationConstraint, ...] | None, tuple[Ref, ...], tuple[str, ...]]:
        integration = getattr(self, "_association_integration", None)
        if not isinstance(integration, IntegrationCommit):
            return None, (), ("semantic:association_constraint_integration_missing",)

        attention: list[Ref] = list(attention_refs)
        seen = {(ref.kind.value, ref.uid) for ref in attention}

        def add_attention(ref: Ref) -> None:
            key = (ref.kind.value, ref.uid)
            if key not in seen:
                seen.add(key)
                attention.append(ref)

        constraints: list[AssociationConstraint] = []
        role_seen: set[ActantRole] = set()
        for candidate in root.actants:
            if candidate.role not in self._CONSTRAINT_ROLES:
                continue
            if candidate.role in role_seen:
                return None, tuple(attention), (
                    f"semantic:association_constraint_role_ambiguous:{candidate.role.value}",
                )
            role_seen.add(candidate.role)
            if candidate.composition is not None:
                # OR/AND semantics for a multi-value restriction must be explicit;
                # silently choosing one member would widen/narrow the query by guess.
                return None, tuple(attention), (
                    f"semantic:association_constraint_composition_unsupported:{candidate.role.value}",
                )
            resolved = self._resolve_endpoint(
                candidate,
                context,
                integration,
                tuple(attention),
                root,
            )
            if resolved.ref is None:
                diagnostic = resolved.diagnostic or "semantic:association_constraint_unresolved"
                return None, tuple(attention), (
                    f"{diagnostic}:constraint:{candidate.role.value}",
                )
            constraints.append(AssociationConstraint(candidate.role, resolved.ref))
            add_attention(resolved.ref)
            for support in resolved.support_refs:
                add_attention(support)

        constraints.sort(key=lambda item: (item.role.value, item.value.kind.value, item.value.uid))
        return tuple(constraints), tuple(attention), ()

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
        base_goal = result.association_goal
        if base_goal is None:
            return result

        constraint_attention_seed = tuple((*attention_refs, *result.attention_refs))
        constraints, constraint_attention, constraint_diagnostics = self._resolve_constraints(
            root,
            context,
            constraint_attention_seed,
        )
        if constraints is None:
            return replace(
                result,
                association_goal=None,
                diagnostics=tuple((*result.diagnostics, *constraint_diagnostics)),
                attention_refs=constraint_attention,
            )

        goal = AssociationScopedGoal(base_goal.left, base_goal.right, constraints)
        diagnostics = list(result.diagnostics)
        if constraints:
            diagnostics.append(
                "semantic:association_constraints:"
                + ",".join(item.role.value for item in constraints)
            )
        result = replace(
            result,
            association_goal=goal,
            diagnostics=tuple(diagnostics),
            attention_refs=constraint_attention,
        )

        session = context.association_session
        same_goal = session is not None and session.same_goal(
            goal.left,
            goal.right,
            goal.constraints,
        )
        if same_goal:
            # Explicit same-scope rephrasing continues exactly the same result
            # stream. A changed LOCATION/TIME/etc is a new goal, even for the same
            # endpoint pair.
            excluded = emitted_signatures(
                self.core,
                goal.left,
                goal.right,
                goal.constraints,
            )
            result = replace(
                result,
                association_goal=AssociationContinuationGoal(
                    goal.left,
                    goal.right,
                    constraints=goal.constraints,
                    excluded_signatures=excluded,
                ),
                diagnostics=tuple(
                    (*result.diagnostics, "semantic:association_same_scope_continuation")
                ),
            )
        else:
            clear_signatures(
                self.core,
                goal.left,
                goal.right,
                goal.constraints,
            )
            context.association_session = AssociationDiscourseSession(
                goal.left,
                goal.right,
                constraints=self._session_constraints(goal),
            )
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
        constraints = tuple(
            AssociationConstraint(role, value)
            for role, value in session.constraints
        )
        excluded = emitted_signatures(
            self.core,
            session.left,
            session.right,
            constraints,
        )
        goal = AssociationContinuationGoal(
            session.left,
            session.right,
            constraints=constraints,
            excluded_signatures=excluded,
        )
        attention = list(attention_refs)
        seen = {(item.kind.value, item.uid) for item in attention}
        for ref in (
            session.left,
            session.right,
            *(value for _role, value in session.constraints),
        ):
            key = (ref.kind.value, ref.uid)
            if key not in seen:
                attention.append(ref)
                seen.add(key)
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
            results = tuple(
                super().build(
                    integration,
                    context,
                    perception,
                    attention_refs=attention_refs,
                )
            )
            if (
                context.association_session is not None
                and (perception.queries or perception.commands)
                and not any(isinstance(item, AssociationQueryBuildResult) for item in results)
            ):
                context.association_session = None
            return results

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
