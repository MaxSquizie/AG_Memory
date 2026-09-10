from __future__ import annotations

from dataclasses import replace

from ah.agent import InteractionContext
from ah.integration.contracts import IntegrationCommit
from ah.model import Ref
from ah.perception import AssertionStatus, PerceptionResult, QueryCandidate, QueryMode

from .contracts import CounterfactualGoal, FormulaGoal, GoalSpec, InferenceQuery
from .query_builder import QueryBuildResult, SemanticGoalCompiler as _BaseSemanticGoalCompiler


class CounterfactualSemanticGoalCompiler(_BaseSemanticGoalCompiler):
    """Add typed counterfactual scope compilation to SemanticGoalCompiler.

    Counterfactual recognition is deliberately structural. Perception must already
    have marked assumption propositions as ``AssertionStatus.HYPOTHETICAL`` and
    connected them to a QUERY root through non-quoted act dependencies. The compiler
    never looks for lexical markers such as ``если бы`` and never writes canonical
    AH. ``apply_speech_act_scoping`` exposes a direct polar query as one EMBEDDED
    shadow proposition when no explicit target proposition already exists.

    Existing ``CounterfactualGoal`` / ``CounterfactualContext`` then own the actual
    proof sandbox, support suppression and local override semantics.
    """

    @staticmethod
    def _ordered_assertion_ids(
        perception: PerceptionResult,
        allowed: set[str],
        *,
        status: AssertionStatus,
    ) -> tuple[str, ...]:
        return tuple(
            item.local_id
            for item in perception.assertions
            if item.local_id in allowed
            and item.status is status
            and not item.quoted
        )

    def _counterfactual_result(
        self,
        root: QueryCandidate,
        integration: IntegrationCommit,
        perception: PerceptionResult,
    ) -> QueryBuildResult | None:
        if root.local_id is None:
            return None

        descendants = self._descendants(perception, root.local_id)
        hypothetical_ids = self._ordered_assertion_ids(
            perception,
            descendants,
            status=AssertionStatus.HYPOTHETICAL,
        )
        if not hypothetical_ids:
            return None

        # Nested HYPOTHETICAL content belongs to the outer hypothetical proposition
        # instead of becoming a second independent world intervention. Independent
        # sibling hypotheses remain simultaneous assumptions in one overlay.
        outer_assumptions: list[str] = []
        for local_id in hypothetical_ids:
            nested_under_other = any(
                local_id in self._descendants(perception, other)
                for other in hypothetical_ids
                if other != local_id
            )
            if not nested_under_other:
                outer_assumptions.append(local_id)

        if not outer_assumptions:
            return QueryBuildResult(
                None,
                ("semantic:counterfactual_assumption_scope_unresolved",),
            )

        if root.query_mode is not QueryMode.EXISTS:
            return QueryBuildResult(
                None,
                ("semantic:counterfactual_formula_target_required",),
            )
        if getattr(root, "quantified", None) is not None:
            # Counterfactual and quantified target construction are orthogonal
            # features. Do not silently drop either scope merely because both are
            # present in one query; composition can be added with an explicit AST
            # contract later.
            return QueryBuildResult(
                None,
                ("semantic:counterfactual_quantified_target_not_supported",),
            )

        assumption_scope: set[str] = set()
        for local_id in outer_assumptions:
            assumption_scope.add(local_id)
            assumption_scope.update(self._descendants(perception, local_id))

        target_candidates = self._ordered_assertion_ids(
            perception,
            descendants - assumption_scope,
            status=AssertionStatus.EMBEDDED,
        )
        if not target_candidates:
            return QueryBuildResult(
                None,
                ("semantic:counterfactual_target_missing",),
            )
        if len(target_candidates) != 1:
            return QueryBuildResult(
                None,
                (
                    "semantic:counterfactual_target_not_unique:"
                    f"{len(target_candidates)}",
                ),
            )

        target_id = target_candidates[0]
        if any(item.act_ref == target_id for item in perception.act_relations):
            # CounterfactualGoal currently evaluates a FormulaGoal. A typed
            # structural RelationGoal (e.g. IS-A) has different proof semantics and
            # must not be downgraded to existence of its linguistic N wrapper.
            return QueryBuildResult(
                None,
                ("semantic:counterfactual_relation_target_not_supported",),
            )

        integrated_by_id = {
            item.local_id: item for item in integration.assertions
        }
        target_item = integrated_by_id.get(target_id)
        target_ref = getattr(target_item, "ref", None)
        if not isinstance(target_ref, Ref) or target_ref.kind.value not in {"N", "G"}:
            return QueryBuildResult(
                None,
                ("semantic:counterfactual_target_not_materialized",),
            )

        assumptions: list[Ref] = []
        for local_id in outer_assumptions:
            item = integrated_by_id.get(local_id)
            ref = getattr(item, "ref", None)
            if not isinstance(ref, Ref) or ref.kind.value not in {"N", "G"}:
                return QueryBuildResult(
                    None,
                    (
                        "semantic:counterfactual_assumption_not_materialized:"
                        f"{local_id}",
                    ),
                )
            assumptions.append(ref)

        attention: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        for ref in (target_ref, *assumptions):
            key = (ref.kind.value, ref.uid)
            if key in seen:
                continue
            seen.add(key)
            attention.append(ref)

        return QueryBuildResult(
            InferenceQuery(
                GoalSpec(
                    CounterfactualGoal(
                        tuple(assumptions),
                        FormulaGoal(target_ref),
                    )
                )
            ),
            ("semantic:counterfactual_formula_goal",),
            tuple(attention),
        )

    def build(
        self,
        integration: IntegrationCommit,
        context: InteractionContext,
        perception: PerceptionResult | None = None,
        attention_refs: tuple[Ref, ...] = (),
    ) -> tuple[QueryBuildResult, ...]:
        # Counterfactual scope is encoded by act dependencies and assertion status,
        # so it cannot be reconstructed safely from IntegrationCommit alone. The
        # production TurnGoalBuilder path always supplies PerceptionResult. Legacy
        # callers without it retain historical behavior rather than guessing which
        # HYPOTHETICAL proposition belongs to which query.
        if perception is None:
            return super().build(
                integration,
                context,
                perception=None,
                attention_refs=attention_refs,
            )

        results: list[QueryBuildResult] = []
        roots = [
            item
            for item in (*perception.queries, *perception.commands)
            if item.local_id is not None and not item.quoted
        ]

        # Delegate each non-counterfactual root to the mature base compiler in its
        # original order. This avoids copying OR/modal/relation/quantified dispatch
        # and keeps this extension independent from points 3 and 4.
        for root in roots:
            if isinstance(root, QueryCandidate):
                counterfactual = self._counterfactual_result(
                    root, integration, perception
                )
                if counterfactual is not None:
                    results.append(counterfactual)
                    continue

            root_perception = replace(
                perception,
                queries=(root,) if isinstance(root, QueryCandidate) else (),
                commands=() if isinstance(root, QueryCandidate) else (root,),
            )
            root_integration = replace(
                integration,
                unresolved_queries=tuple(
                    item
                    for item in integration.unresolved_queries
                    if isinstance(root, QueryCandidate)
                    and item.local_id == root.local_id
                ),
                unresolved_commands=tuple(
                    item
                    for item in integration.unresolved_commands
                    if not isinstance(root, QueryCandidate)
                    and item.local_id == root.local_id
                ),
            )
            results.extend(
                super().build(
                    root_integration,
                    context,
                    root_perception,
                    attention_refs=attention_refs,
                )
            )

        # Preserve the historical fallback for queries that have no local_id and
        # therefore cannot participate in dependency-scoped counterfactual syntax.
        idless_queries = tuple(
            item for item in integration.unresolved_queries
            if item.local_id is None
        )
        if idless_queries:
            idless_integration = replace(
                integration,
                unresolved_queries=idless_queries,
                unresolved_commands=(),
            )
            empty_roots = replace(perception, queries=(), commands=())
            results.extend(
                super().build(
                    idless_integration,
                    context,
                    empty_roots,
                    attention_refs=attention_refs,
                )
            )

        return tuple(results)
