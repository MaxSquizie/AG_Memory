from __future__ import annotations

from ah.agent import InteractionContext
from ah.integration.contracts import IntegrationCommit
from ah.model import Ref
from ah.perception import PropositionExprCandidate, QueryCandidate

from .contracts import GoalSpec, InferenceQuery
from .modal_goal import ModalSemanticGoalCompiler
from .query_builder import QueryBuildResult


class ModalTurnGoalCompiler(ModalSemanticGoalCompiler):
    """Complete modal dispatch around the existing matrix/quantified query paths.

    ``SemanticGoalCompiler.build`` historically gives proposition-valued
    QueryCandidate actants to the matrix-attitude compiler before calling
    ``_compile_scope``. That ordering is correct for BELIEVES(A,P), SAID(A,P), etc.,
    but an impersonal modal shell whose actants are *only* proposition content must
    retain its POSSIBLE/REQUIRED/PERMITTED AST instead of being mistaken for an
    attitude relation.

    This class changes only dispatch. It performs no lexical recognition and no AH
    writes; the modal AST must already be present in Perception.
    """

    @staticmethod
    def _modal_expressions(query: QueryCandidate) -> tuple[PropositionExprCandidate, ...]:
        return tuple(
            actant.proposition
            for actant in query.actants
            if actant.proposition is not None
            and ModalSemanticGoalCompiler._contains_modal(actant.proposition)
        )

    @staticmethod
    def _proposition_only_shell(query: QueryCandidate) -> bool:
        return bool(query.actants) and all(
            actant.proposition is not None or actant.candidate_ref is not None
            for actant in query.actants
        )

    def _build_matrix_proposition_query(
        self,
        query: QueryCandidate,
        context: InteractionContext,
        integrated_by_id: dict[str, object],
        attention_refs: tuple[Ref, ...],
    ) -> QueryBuildResult:
        modal_expressions = self._modal_expressions(query)
        if not modal_expressions or not self._proposition_only_shell(query):
            # Subject-bearing attitudes remain matrix propositions. A modal phrase
            # embedded *inside* BELIEVES(A, M(P)) is not authorization to ask M(P).
            return super()._build_matrix_proposition_query(
                query,
                context,
                integrated_by_id,
                attention_refs,
            )
        if len(modal_expressions) != 1:
            return QueryBuildResult(
                None,
                (
                    "semantic:modal_matrix_shell_scope_not_unique:"
                    f"{len(modal_expressions)}",
                ),
            )

        expression = modal_expressions[0]
        # At this late boundary Integration has already encoded local assertion
        # negation in the referenced N/G. Passing an empty assertion map is safe:
        # _pattern_from_expr expands those ground G wrappers structurally.
        goal = self._goal_from_modal_expr(expression, integrated_by_id, {})
        if goal is None:
            return QueryBuildResult(
                None,
                ("semantic:modal_formula_target_unresolved",),
            )

        pattern = self._pattern_from_expr(expression, integrated_by_id, {})
        attention: list[Ref] = list(attention_refs)
        seen = {(item.kind.value, item.uid) for item in attention}
        if pattern is not None:
            for ref in pattern.refs():
                key = (ref.kind.value, ref.uid)
                if key in seen:
                    continue
                seen.add(key)
                attention.append(ref)
        return QueryBuildResult(
            InferenceQuery(GoalSpec(goal)),
            ("semantic:modal_formula_goal:proposition_shell",),
            tuple(attention),
        )

    def _build_quantified_formula_goal(
        self,
        query: QueryCandidate,
        integration: IntegrationCommit,
    ) -> QueryBuildResult:
        # The current quantified-query materializer creates only the quantified
        # formula. If the same query also carries an explicit modal AST, compiling
        # it as quantified-only would silently erase modal scope. Until a combined
        # quantified-modal FormulaGoal contract exists, fail closed.
        if query.quantified is not None and self._modal_expressions(query):
            return QueryBuildResult(
                None,
                ("semantic:quantified_modal_target_not_supported",),
            )
        return super()._build_quantified_formula_goal(query, integration)
