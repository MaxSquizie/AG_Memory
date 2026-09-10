from __future__ import annotations

from ah.agent import InteractionContext
from ah.integration.contracts import IntegrationCommit
from ah.model import FunctionSymbol, Ref, RefKind
from ah.perception import PropositionExprCandidate, PropositionOperator, QueryCandidate

from .contracts import GoalSpec, InferenceQuery
from .modal_goal import FormulaPattern, ModalSemanticGoalCompiler
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

    def _pattern_from_expr(
        self,
        expr: PropositionExprCandidate,
        integrated_by_id: dict[str, object],
        assertion_by_id: dict[str, object],
    ) -> FormulaPattern | None:
        # A negative EMBEDDED assertion is already represented by Integration as
        # g_NOT(N). When the proposition AST also explicitly owns that same NOT,
        # remove exactly the Integration wrapper before rebuilding the AST node.
        # For a real double negation, the outer NOT remains a separate parent in
        # the expression tree, so NOT(NOT(N)) is preserved rather than collapsed.
        if (
            expr.operator in {PropositionOperator.NOT, PropositionOperator.FALSE}
            and len(expr.members) == 1
            and expr.members[0].operator is PropositionOperator.REF
        ):
            child = expr.members[0]
            assert child.ref is not None
            integrated = integrated_by_id.get(child.ref)
            ref = getattr(integrated, "ref", None)
            if (
                isinstance(ref, Ref)
                and ref.kind is RefKind.G
                and self.core.store.has_uid(ref.uid)
            ):
                element = self.core.store.get_element_any_domain(ref.uid)
                if isinstance(element, FunctionSymbol):
                    try:
                        operator = self.core.function_registry.canonical_id(
                            element.function_id
                        )
                    except KeyError:
                        operator = ""
                    if (
                        operator == "NOT"
                        and len(element.operands) == 1
                        and isinstance(element.operands[0], Ref)
                    ):
                        return FormulaPattern(
                            operator="NOT",
                            members=(
                                self._pattern_for_canonical_ref(element.operands[0]),
                            ),
                        )
        return super()._pattern_from_expr(
            expr, integrated_by_id, assertion_by_id
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
