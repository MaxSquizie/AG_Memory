from __future__ import annotations

from ah.agent import InteractionContext
from ah.integration.contracts import IntegrationCommit
from ah.integration.entity_resolver import EntityResolver, ExistingEntity
from ah.model import FunctionSymbol, Ref, RefKind
from ah.perception import (
    PropositionExprCandidate,
    PropositionOperator,
    QueryCandidate,
    QueryMode,
)

from .contracts import GoalSpec, InferenceQuery
from .modal_goal import (
    FormulaPattern,
    MatrixFormulaPatternGoal,
    ModalSemanticGoalCompiler,
)
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
        pattern_expressions = tuple(
            actant.proposition
            for actant in query.actants
            if actant.proposition is not None
            and self._requires_pattern_goal(actant.proposition)
        )
        if not pattern_expressions:
            return super()._build_matrix_proposition_query(
                query,
                context,
                integrated_by_id,
                attention_refs,
            )
        if self._proposition_only_shell(query) and not query.requested_roles:
            if len(pattern_expressions) != 1:
                return QueryBuildResult(
                    None,
                    (
                        "semantic:formula_matrix_shell_scope_not_unique:"
                        f"{len(pattern_expressions)}",
                    ),
                )
            expression = pattern_expressions[0]
            goal = self._goal_from_modal_expr(expression, integrated_by_id, {})
            if goal is None:
                return QueryBuildResult(
                    None,
                    ("semantic:formula_pattern_target_unresolved",),
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
            diagnostic = (
                "semantic:modal_formula_goal:proposition_shell"
                if self._contains_modal(expression)
                else "semantic:proposition_formula_goal:proposition_shell"
            )
            return QueryBuildResult(
                InferenceQuery(GoalSpec(goal)),
                (diagnostic,),
                tuple(attention),
            )

        selection = query.predicate.template_selection
        if selection is None or selection.existing_template_uid is None:
            return QueryBuildResult(
                None,
                ("semantic:matrix_query_template_unresolved",),
            )
        try:
            template = self.core.store.get_template(selection.existing_template_uid)
        except KeyError:
            return QueryBuildResult(
                None,
                ("semantic:matrix_query_template_missing",),
            )

        resolver = EntityResolver(self.core)
        known = {}
        proposition_roles = {}
        attention: list[Ref] = list(attention_refs)
        seen = {(item.kind.value, item.uid) for item in attention}

        def add_attention(ref: Ref) -> None:
            key = (ref.kind.value, ref.uid)
            if key not in seen:
                seen.add(key)
                attention.append(ref)

        for actant in query.actants:
            if actant.proposition is not None:
                if actant.proposition.operator is PropositionOperator.REF:
                    assert actant.proposition.ref is not None
                    integrated = integrated_by_id.get(actant.proposition.ref)
                    ref = getattr(integrated, "ref", None)
                    if not isinstance(ref, Ref):
                        return QueryBuildResult(
                            None,
                            (
                                "semantic:matrix_query_content_missing:"
                                f"{actant.proposition.ref}",
                            ),
                        )
                    known[actant.role] = ref
                    add_attention(ref)
                    continue
                pattern = self._pattern_from_expr(
                    actant.proposition, integrated_by_id, {}
                )
                if pattern is None:
                    return QueryBuildResult(
                        None,
                        ("semantic:matrix_query_formula_pattern_unresolved",),
                    )
                proposition_roles[actant.role] = pattern
                for ref in pattern.refs():
                    add_attention(ref)
                continue
            if actant.candidate_ref is not None:
                integrated = integrated_by_id.get(actant.candidate_ref)
                ref = getattr(integrated, "ref", None)
                if not isinstance(ref, Ref):
                    return QueryBuildResult(
                        None,
                        (
                            "semantic:matrix_query_content_missing:"
                            f"{actant.candidate_ref}",
                        ),
                    )
                known[actant.role] = ref
                add_attention(ref)
                continue
            resolved = resolver.resolve(
                actant,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
                attention_refs=attention_refs,
            )
            if not isinstance(resolved, ExistingEntity):
                return QueryBuildResult(
                    None,
                    (
                        "semantic:matrix_query_actant_unresolved:"
                        f"{actant.role.value}",
                    ),
                )
            known[actant.role] = resolved.ref
            add_attention(resolved.ref)
            for ref in resolved.support_refs:
                add_attention(ref)

        required_roles = (
            set(known) | set(proposition_roles) | set(query.requested_roles)
        )
        if not required_roles.issubset(set(template.roles)):
            return QueryBuildResult(
                None,
                ("semantic:matrix_query_template_role_mismatch",),
            )
        if query.query_mode is QueryMode.FILL_ROLE and not query.requested_roles:
            return QueryBuildResult(
                None,
                ("semantic:matrix_query_requested_role_missing",),
            )
        target = MatrixFormulaPatternGoal(
            self.core.ref(template.uid),
            known,
            proposition_roles,
            query.requested_roles,
        )
        return QueryBuildResult(
            InferenceQuery(GoalSpec(target)),
            ("semantic:matrix_proposition_pattern_query",),
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
