from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from ah.agent import InteractionContext
from ah.integration.contracts import IntegrationCommit
from ah.model import ActantRole, FunctionSymbol, Ref, RefKind
from ah.perception import (
    AssertionStatus,
    PerceptionResult,
    PropositionExprCandidate,
    PropositionOperator,
    QueryCandidate,
)

from .attention import InferenceAttention
from .context import ProofContext
from .contracts import (
    AllOfGoal,
    FormulaGoal,
    GoalSpec,
    ExistingRefConclusion,
    InferenceOutcome,
    InferenceQuery,
    LogicalStatus,
    MultiRoleBindingConclusion,
    ProofSupport,
    RoleBindingConclusion,
    StopReason,
)
from .counterfactual_goal import CounterfactualSemanticGoalCompiler
from .engine import InferenceEngine as _BaseInferenceEngine
from .domain import domain_from_premises
from .query_builder import QueryBuildResult
from .runtime import GoalRuntime


_MODAL_OPERATORS = frozenset({"POSSIBLE", "REQUIRED", "PERMITTED"})
_COMMUTATIVE_OPERATORS = frozenset({"AND", "OR", "XOR"})


@dataclass(frozen=True, slots=True)
class FormulaPattern:
    """Runtime-only structural formula target over already canonical leaf refs.

    Unlike a canonical ``g`` this object is not AH memory and has no UID. It lets a
    question ask about a modal/compound proposition without creating that proposition
    merely because it was queried. Operator nodes are matched through the derived
    reverse ``function_parents`` index; N leaves are matched by canonical semantic
    shape (domain + T + actants), so a query-scoped N can refer to the same content
    as a previously asserted LOGICAL leaf with a different UID.
    """

    operator: str | None = None
    ref: Ref | None = None
    members: tuple["FormulaPattern", ...] = ()

    def __post_init__(self) -> None:
        if self.operator is None:
            if self.ref is None or self.members:
                raise ValueError("FormulaPattern leaf requires exactly one ref")
            if self.ref.kind not in {RefKind.N, RefKind.G}:
                raise ValueError("FormulaPattern leaf must reference N or G")
            return
        normalized = self.operator.strip().upper()
        if not normalized or self.ref is not None or not self.members:
            raise ValueError("FormulaPattern operator requires members and no ref")
        object.__setattr__(self, "operator", normalized)

    @classmethod
    def leaf(cls, ref: Ref) -> "FormulaPattern":
        return cls(ref=ref)

    def refs(self) -> tuple[Ref, ...]:
        if self.operator is None:
            assert self.ref is not None
            return (self.ref,)
        out: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        for child in self.members:
            for ref in child.refs():
                key = (ref.kind.value, ref.uid)
                if key in seen:
                    continue
                seen.add(key)
                out.append(ref)
        return tuple(out)


@dataclass(frozen=True, slots=True)
class FormulaPatternGoal:
    """Read-only query goal for a formula that must not be materialized by asking."""

    pattern: FormulaPattern


@dataclass(frozen=True, slots=True)
class MatrixFormulaPatternGoal:
    """Read-only matrix proposition match with structural formula-valued roles."""

    template_ref: Ref
    known_roles: Mapping[ActantRole, Ref]
    proposition_roles: Mapping[ActantRole, FormulaPattern]
    requested_roles: tuple[ActantRole, ...] = ()

    def __post_init__(self) -> None:
        if self.template_ref.kind is not RefKind.T:
            raise ValueError("MatrixFormulaPatternGoal.template_ref must reference T")
        if not self.proposition_roles:
            raise ValueError("MatrixFormulaPatternGoal requires a proposition role")
        if set(self.known_roles) & set(self.proposition_roles):
            raise ValueError("MatrixFormulaPatternGoal role constraints must not overlap")
        if len(set(self.requested_roles)) != len(self.requested_roles):
            raise ValueError("MatrixFormulaPatternGoal.requested_roles must be unique")
        if set(self.requested_roles) & (
            set(self.known_roles) | set(self.proposition_roles)
        ):
            raise ValueError("Requested matrix roles cannot also be constrained")


class ModalSemanticGoalCompiler(CounterfactualSemanticGoalCompiler):
    """Compile typed modal query AST into a read-only structural formula goal.

    Perception already owns semantic recognition and scope choice for POSSIBLE /
    REQUIRED / PERMITTED. This compiler never inspects lexical markers. It only
    converts the existing proposition AST into a query pattern over canonical leaf
    content and preserves the modal operator as part of the goal.

    The pattern is deliberately runtime-only: Integration remains the sole canonical
    write boundary, and a question such as ``POSSIBLE(P)?`` must not manufacture a
    canonical POSSIBLE(P) assertion or promote P to factual truth.
    """

    @staticmethod
    def _contains_modal(expr: PropositionExprCandidate) -> bool:
        if expr.operator.value in _MODAL_OPERATORS:
            return True
        return any(ModalSemanticGoalCompiler._contains_modal(item) for item in expr.members)

    @staticmethod
    def _requires_pattern_goal(expr: PropositionExprCandidate) -> bool:
        if expr.operator in {
            PropositionOperator.OR,
            PropositionOperator.XOR,
            PropositionOperator.POSSIBLE,
            PropositionOperator.REQUIRED,
            PropositionOperator.PERMITTED,
        }:
            return True
        return any(
            ModalSemanticGoalCompiler._requires_pattern_goal(item)
            for item in expr.members
        )

    def _pattern_for_canonical_ref(self, ref: Ref) -> FormulaPattern:
        """Expand ground g wrappers so scoped N identity can be matched underneath."""
        if ref.kind is not RefKind.G or not self.core.store.has_uid(ref.uid):
            return FormulaPattern.leaf(ref)
        element = self.core.store.get_element_any_domain(ref.uid)
        if not isinstance(element, FunctionSymbol):
            return FormulaPattern.leaf(ref)
        try:
            operator = self.core.function_registry.canonical_id(element.function_id)
        except KeyError:
            return FormulaPattern.leaf(ref)
        operands = tuple(item for item in element.operands if isinstance(item, Ref))
        if len(operands) != len(element.operands) or not operands:
            # Bound-variable/other non-ground formulae belong to quantified goal
            # compilation, not to this ground modal pattern.
            return FormulaPattern.leaf(ref)
        return FormulaPattern(
            operator=operator,
            members=tuple(self._pattern_for_canonical_ref(item) for item in operands),
        )

    def _pattern_from_expr(
        self,
        expr: PropositionExprCandidate,
        integrated_by_id: dict[str, object],
        assertion_by_id: dict[str, object],
    ) -> FormulaPattern | None:
        if expr.operator is PropositionOperator.REF:
            assert expr.ref is not None
            integrated = integrated_by_id.get(expr.ref)
            ref = getattr(integrated, "ref", None)
            if not isinstance(ref, Ref) or ref.kind not in {RefKind.N, RefKind.G}:
                return None
            return self._pattern_for_canonical_ref(ref)

        # Integration wraps an EMBEDDED negative assertion as canonical NOT(N).
        # If the proposition AST already owns the NOT node, peel that integration
        # wrapper once so the query pattern remains NOT(N), never NOT(NOT(N)).
        if (
            expr.operator in {PropositionOperator.NOT, PropositionOperator.FALSE}
            and len(expr.members) == 1
            and expr.members[0].operator is PropositionOperator.REF
        ):
            child = expr.members[0]
            assert child.ref is not None
            candidate = assertion_by_id.get(child.ref)
            integrated = integrated_by_id.get(child.ref)
            integrated_ref = getattr(integrated, "ref", None)
            if (
                getattr(candidate, "negated", False)
                and isinstance(integrated_ref, Ref)
                and integrated_ref.kind is RefKind.G
                and self.core.store.has_uid(integrated_ref.uid)
            ):
                element = self.core.store.get_element_any_domain(integrated_ref.uid)
                if isinstance(element, FunctionSymbol):
                    try:
                        canonical = self.core.function_registry.canonical_id(element.function_id)
                    except KeyError:
                        canonical = ""
                    if (
                        canonical == "NOT"
                        and len(element.operands) == 1
                        and isinstance(element.operands[0], Ref)
                    ):
                        child_pattern = self._pattern_for_canonical_ref(element.operands[0])
                        return FormulaPattern(operator="NOT", members=(child_pattern,))

        members: list[FormulaPattern] = []
        for member in expr.members:
            pattern = self._pattern_from_expr(member, integrated_by_id, assertion_by_id)
            if pattern is None:
                return None
            members.append(pattern)
        operator = (
            "NOT"
            if expr.operator is PropositionOperator.FALSE
            else expr.operator.value
        )
        return FormulaPattern(operator=operator, members=tuple(members))

    def _goal_from_modal_expr(
        self,
        expr: PropositionExprCandidate,
        integrated_by_id: dict[str, object],
        assertion_by_id: dict[str, object],
    ):
        # Preserve the already-supported conjunctive query semantics. A top-level
        # AND is a request for every child, not necessarily for one historically
        # asserted AND wrapper. Modal children remain structural pattern goals;
        # ordinary REF children use the mature FormulaGoal path.
        if expr.operator is PropositionOperator.AND:
            children = []
            for member in expr.members:
                if member.operator is PropositionOperator.REF:
                    assert member.ref is not None
                    integrated = integrated_by_id.get(member.ref)
                    ref = getattr(integrated, "ref", None)
                    if not isinstance(ref, Ref) or ref.kind not in {RefKind.N, RefKind.G}:
                        return None
                    children.append(FormulaGoal(ref))
                    continue
                pattern = self._pattern_from_expr(member, integrated_by_id, assertion_by_id)
                if pattern is None:
                    return None
                children.append(FormulaPatternGoal(pattern))
            if len(children) < 2:
                return None
            return AllOfGoal(tuple(children))

        pattern = self._pattern_from_expr(expr, integrated_by_id, assertion_by_id)
        return None if pattern is None else FormulaPatternGoal(pattern)

    def _counterfactual_result(
        self,
        root: QueryCandidate,
        integration: IntegrationCommit,
        perception: PerceptionResult,
    ) -> QueryBuildResult | None:
        descendants = (
            set()
            if root.local_id is None
            else self._descendants(perception, root.local_id)
        )
        has_hypothesis = any(
            item.local_id in descendants
            and item.status is AssertionStatus.HYPOTHETICAL
            and not item.quoted
            for item in perception.assertions
        )
        if has_hypothesis and any(
            self._contains_modal(expr) for expr in self._root_expressions(root)
        ):
            # Counterfactual+modal scope composition needs an explicit combined
            # proof contract. Dropping either operator would be semantically wrong.
            return QueryBuildResult(
                None,
                ("semantic:counterfactual_modal_target_not_supported",),
            )
        return super()._counterfactual_result(root, integration, perception)

    def _compile_scope(
        self,
        *,
        root,
        target_ids: set[str],
        perception: PerceptionResult,
        integrated_by_id: dict[str, object],
    ) -> list[QueryBuildResult]:
        expressions = self._root_expressions(root)
        pattern_owners = tuple(
            expr
            for expr in expressions
            if self._contains_modal(expr) and set(expr.leaf_refs()) == target_ids
        )
        if not pattern_owners:
            return super()._compile_scope(
                root=root,
                target_ids=target_ids,
                perception=perception,
                integrated_by_id=integrated_by_id,
            )
        if len(pattern_owners) != 1:
            return [
                QueryBuildResult(
                    None,
                    (
                        "semantic:formula_pattern_scope_not_unique:"
                        f"{len(pattern_owners)}",
                    ),
                )
            ]

        assertion_by_id = {item.local_id: item for item in perception.assertions}
        goal = self._goal_from_modal_expr(
            pattern_owners[0], integrated_by_id, assertion_by_id
        )
        if goal is None:
            return [
                QueryBuildResult(
                    None,
                    ("semantic:modal_formula_target_unresolved",),
                )
            ]

        attention: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        pattern = self._pattern_from_expr(
            pattern_owners[0], integrated_by_id, assertion_by_id
        )
        if pattern is not None:
            for ref in pattern.refs():
                key = (ref.kind.value, ref.uid)
                if key in seen:
                    continue
                seen.add(key)
                attention.append(ref)

        operators = sorted(
            {
                item.operator
                for item in self._walk_patterns(pattern)
                if item.operator in (_MODAL_OPERATORS | {"OR", "XOR"})
            }
        ) if pattern is not None else []
        if operators and set(operators).issubset(_MODAL_OPERATORS):
            diagnostic = "semantic:modal_formula_goal:" + "+".join(operators)
        else:
            diagnostic = (
                "semantic:proposition_formula_goal:"
                + ("+".join(operators) if operators else "COMPOUND")
            )
        return [
            QueryBuildResult(
                InferenceQuery(GoalSpec(goal)),
                (diagnostic,),
                tuple(attention),
            )
        ]

    @staticmethod
    def _walk_patterns(pattern: FormulaPattern | None) -> tuple[FormulaPattern, ...]:
        if pattern is None:
            return ()
        out = [pattern]
        for child in pattern.members:
            out.extend(ModalSemanticGoalCompiler._walk_patterns(child))
        return tuple(out)


class _FormulaPatternResolver:
    """Bounded-by-index structural matcher; never scans arbitrary AH elements."""

    def __init__(self, engine: "ModalInferenceEngine") -> None:
        self.engine = engine
        self.core = engine.core

    def _equivalent_leaf_refs(self, ref: Ref) -> tuple[Ref, ...]:
        if not self.core.store.has_uid(ref.uid):
            return ()
        if ref.kind is not RefKind.N:
            return (ref,)
        node = self.core.store.get_hypernode(ref.uid)
        domain = self.core.store.domain_of(ref.uid)
        matches = [
            self.core.ref(item.uid)
            for item in self.core.store.find_hypernodes_by_template(node.template.uid)
            if self.core.store.domain_of(item.uid) is domain
            and dict(item.actants) == dict(node.actants)
        ]
        matches.sort(key=lambda item: item.uid)
        return tuple(matches)

    def _operator_of(self, ref: Ref) -> tuple[str, tuple[Ref, ...]] | None:
        if ref.kind is not RefKind.G or not self.core.store.has_uid(ref.uid):
            return None
        element = self.core.store.get_element_any_domain(ref.uid)
        if not isinstance(element, FunctionSymbol):
            return None
        try:
            operator = self.core.function_registry.canonical_id(element.function_id)
        except KeyError:
            return None
        operands = tuple(item for item in element.operands if isinstance(item, Ref))
        if len(operands) != len(element.operands):
            return None
        return operator, operands

    def _matches(self, ref: Ref, pattern: FormulaPattern) -> bool:
        if pattern.operator is None:
            assert pattern.ref is not None
            return any(item == ref for item in self._equivalent_leaf_refs(pattern.ref))

        described = self._operator_of(ref)
        if described is None:
            return False
        operator, operands = described
        if operator != pattern.operator or len(operands) != len(pattern.members):
            return False

        if operator not in _COMMUTATIVE_OPERATORS:
            return all(
                self._matches(operand, child)
                for operand, child in zip(operands, pattern.members)
            )

        # AND/OR/XOR are semantically commutative even though canonical g retains
        # source order. Match by one-to-one structural assignment so paraphrasing
        # operand order does not create a false mismatch.
        used = [False] * len(operands)

        def assign(index: int) -> bool:
            if index >= len(pattern.members):
                return True
            child = pattern.members[index]
            for operand_index, operand in enumerate(operands):
                if used[operand_index] or not self._matches(operand, child):
                    continue
                used[operand_index] = True
                if assign(index + 1):
                    return True
                used[operand_index] = False
            return False

        return assign(0)

    def candidates(self, pattern: FormulaPattern) -> tuple[Ref, ...]:
        if pattern.operator is None:
            assert pattern.ref is not None
            return self._equivalent_leaf_refs(pattern.ref)
        if not pattern.members:
            return ()

        # Anchor lookup at one already-known child. function_parents contains every
        # operand position, so this remains complete for commutative operators too.
        anchor_candidates = self.candidates(pattern.members[0])
        roots: dict[str, Ref] = {}
        for anchor in anchor_candidates:
            for parent in self.core.store.function_parents(anchor.uid):
                parent_ref = self.core.ref(parent.uid)
                if self._matches(parent_ref, pattern):
                    roots[parent_ref.uid] = parent_ref
        return tuple(roots[uid] for uid in sorted(roots))


class ModalInferenceEngine(_BaseInferenceEngine):
    """InferenceEngine extension for read-only FormulaPatternGoal resolution."""

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
        if isinstance(goal, FormulaPatternGoal):
            return self._formula_pattern(
                goal,
                query,
                workspace_refs,
                attention,
                proof_context=proof_context,
                runtime=runtime,
            )
        if isinstance(goal, MatrixFormulaPatternGoal):
            return self._matrix_formula_pattern(
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

    def _formula_pattern(
        self,
        goal: FormulaPatternGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        candidates = _FormulaPatternResolver(self).candidates(goal.pattern)
        runtime.memory_query(
            "FORMULA_PATTERN",
            self._pattern_label(goal.pattern),
            logical_depth=0,
            candidate_count=len(candidates),
            detail="T-index + reverse function-parent structural lookup; read-only",
        )
        first_disproved: InferenceOutcome | None = None
        first_unknown: InferenceOutcome | None = None
        for candidate in candidates:
            runtime.subgoal(
                logical_depth=0,
                ref=candidate,
                detail="evaluate canonical formula matching runtime pattern",
            )
            child_query = InferenceQuery(
                GoalSpec(FormulaGoal(candidate)),
                premise_refs=query.premise_refs,
                max_depth=query.max_depth,
                max_expanded_states=query.max_expanded_states,
                proof_context=proof_context,
            )
            outcome = super()._solve_goal(
                FormulaGoal(candidate),
                child_query,
                workspace_refs,
                attention,
                proof_context=proof_context,
                runtime=runtime,
            )
            decorated = replace(
                outcome,
                diagnostics=(
                    "resolved runtime formula pattern to canonical formula",
                    *outcome.diagnostics,
                ),
            )
            if outcome.status is LogicalStatus.PROVED:
                return decorated
            if outcome.status is LogicalStatus.DISPROVED and first_disproved is None:
                first_disproved = decorated
            elif (
                outcome.status is LogicalStatus.UNKNOWN
                and first_unknown is None
                and (
                    outcome.premise_refs
                    or outcome.stop_reason
                    in {
                        StopReason.CONFLICTED,
                        StopReason.BUDGET_EXHAUSTED,
                        StopReason.DEPTH_EXHAUSTED,
                        StopReason.RESOURCE_LIMIT,
                    }
                )
            ):
                # A zero-occurrence scoped N is often the query's structural
                # anchor, not competing evidence. Its empty SEARCH_EXHAUSTED must
                # not override explicit negative support on an equivalent fact.
                first_unknown = decorated

        # An OR/XOR question does not require a pre-existing canonical wrapper.
        # Evaluate its runtime-only children using the same open-world rules as a
        # canonical ground formula, without calling ensure_function.
        if goal.pattern.operator in {"OR", "XOR"}:
            derived = self._logical_pattern(
                goal.pattern,
                query,
                workspace_refs,
                attention,
                proof_context=proof_context,
                runtime=runtime,
            )
            if derived.status is not LogicalStatus.UNKNOWN:
                return derived

        # Open-world uncertainty dominates a negative candidate: when equivalent
        # canonical shapes disagree between DISPROVED and UNKNOWN, there is no
        # complete basis for declaring the queried proposition false.
        if first_unknown is not None:
            return first_unknown
        if first_disproved is not None:
            return first_disproved
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            None,
            0,
            (
                "No canonical formula matches the runtime pattern"
                if not candidates
                else "Formula pattern candidates produced no admissible proof",
            ),
            logical_depth=0,
            proof_context=proof_context,
        )

    @staticmethod
    def _merged_refs(
        outcomes: tuple[InferenceOutcome, ...], attribute: str
    ) -> tuple[Ref, ...]:
        refs: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        for outcome in outcomes:
            for ref in getattr(outcome, attribute):
                key = (ref.kind.value, ref.uid)
                if key in seen:
                    continue
                seen.add(key)
                refs.append(ref)
        return tuple(refs)

    def _logical_pattern(
        self,
        pattern: FormulaPattern,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        assert pattern.operator in {"OR", "XOR"}
        outcomes = tuple(
            self._formula_pattern(
                FormulaPatternGoal(member),
                query,
                workspace_refs,
                attention,
                proof_context=proof_context,
                runtime=runtime,
            )
            for member in pattern.members
        )
        proved = tuple(
            item for item in outcomes if item.status is LogicalStatus.PROVED
        )
        disproved = tuple(
            item for item in outcomes if item.status is LogicalStatus.DISPROVED
        )

        rule_id: str | None = None
        status = LogicalStatus.UNKNOWN
        stop_reason = StopReason.SEARCH_EXHAUSTED
        selected: tuple[InferenceOutcome, ...] = ()
        if pattern.operator == "OR":
            if proved:
                status = LogicalStatus.PROVED
                stop_reason = StopReason.GOAL_SATISFIED
                rule_id = "OR_INTRO"
                selected = (proved[0],)
            elif outcomes and len(disproved) == len(outcomes):
                status = LogicalStatus.DISPROVED
                stop_reason = StopReason.GOAL_REFUTED
                rule_id = "OR_REFUTED"
                selected = outcomes
        elif len(proved) >= 2:
            status = LogicalStatus.DISPROVED
            stop_reason = StopReason.GOAL_REFUTED
            rule_id = "XOR_MULTI_TRUE"
            selected = proved[:2]
        elif len(proved) == 1 and len(disproved) == len(outcomes) - 1:
            status = LogicalStatus.PROVED
            stop_reason = StopReason.GOAL_SATISFIED
            rule_id = "XOR_INTRO"
            selected = outcomes
        elif outcomes and len(disproved) == len(outcomes):
            status = LogicalStatus.DISPROVED
            stop_reason = StopReason.GOAL_REFUTED
            rule_id = "XOR_ALL_FALSE"
            selected = outcomes

        if rule_id is None:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                None,
                sum(item.expanded_states for item in outcomes),
                (
                    f"Runtime {pattern.operator} has an UNKNOWN branch; "
                    "open-world inference cannot close it",
                ),
                logical_depth=max(
                    (item.logical_depth for item in outcomes), default=0
                ),
                proof_context=proof_context,
            )

        premises = self._merged_refs(selected, "premise_refs")
        trace = self._merged_refs(selected, "uid_trace")
        logical_depth = max(
            (item.logical_depth for item in selected), default=0
        )
        runtime.rule(
            rule_id,
            logical_depth=logical_depth,
            detail=f"runtime-only {pattern.operator} expression goal",
        )
        return InferenceOutcome(
            status,
            stop_reason,
            None,
            premises,
            trace,
            domain_from_premises(self.core, premises) if premises else None,
            sum(item.expanded_states for item in outcomes),
            (f"Resolved runtime-only {pattern.operator} expression goal",),
            logical_depth=logical_depth,
            proof_support=(ProofSupport(premises, rule_id=rule_id),),
            proof_context=proof_context,
        )

    def _matrix_formula_pattern(
        self,
        goal: MatrixFormulaPatternGoal,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        runtime.focus(
            goal.template_ref,
            logical_depth=0,
            reason="matrix formula-pattern template seed",
        )
        candidates = tuple(
            self.core.store.find_hypernodes_by_template(goal.template_ref.uid)
        )
        runtime.memory_query(
            "MATRIX_FORMULA_PATTERN",
            f"T={goal.template_ref.uid}|formula_roles="
            + ",".join(sorted(role.value for role in goal.proposition_roles)),
            logical_depth=0,
            candidate_count=len(candidates),
            detail="template index + structural formula matching; read-only",
        )
        resolver = _FormulaPatternResolver(self)
        matched = []
        for node in candidates:
            if node.meta.get("semantic_scope"):
                continue
            if not all(
                node.actants.get(role) == ref
                for role, ref in goal.known_roles.items()
            ):
                continue
            if not all(
                isinstance(node.actants.get(role), Ref)
                and resolver._matches(node.actants[role], pattern)
                for role, pattern in goal.proposition_roles.items()
            ):
                continue
            matched.append(node)

        conflicted: list[Ref] = []
        refuted: list[tuple[Ref, Ref]] = []
        for node in sorted(matched, key=lambda item: item.uid):
            fact_ref = self.core.ref(node.uid)
            if self.conflicts.is_conflicted(fact_ref):
                conflicted.append(fact_ref)
                continue
            false_ref = self._false_wrapper(node.uid)
            if false_ref is not None:
                refuted.append((fact_ref, false_ref))
                continue

            runtime.focus(fact_ref, logical_depth=0, reason="matched matrix fact")
            if len(goal.requested_roles) == 1:
                role = goal.requested_roles[0]
                value = node.actants.get(role)
                if not isinstance(value, Ref):
                    continue
                conclusion = RoleBindingConclusion(role, value, fact_ref)
                trace = (fact_ref, value)
            elif goal.requested_roles:
                bindings = tuple(
                    (role, node.actants.get(role))
                    for role in goal.requested_roles
                )
                if any(not isinstance(value, Ref) for _role, value in bindings):
                    continue
                conclusion = MultiRoleBindingConclusion(bindings, fact_ref)
                trace = (fact_ref, *(value for _role, value in bindings))
            else:
                conclusion = ExistingRefConclusion(fact_ref)
                trace = (fact_ref,)
            runtime.rule(
                "FACT_MATCH", logical_depth=0, detail="matrix formula pattern"
            )
            premises = (fact_ref,)
            return InferenceOutcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                conclusion,
                premises,
                trace,
                domain_from_premises(self.core, premises),
                len(candidates),
                proof_support=(ProofSupport(premises, rule_id="FACT_MATCH"),),
                proof_context=proof_context,
            )

        conflict = self._conflict_outcome(
            tuple(conflicted), expanded=len(candidates)
        )
        if conflict is not None:
            return replace(conflict, proof_context=proof_context)
        template = self.core.store.get_template(goal.template_ref.uid)
        if (
            not goal.requested_roles
            and refuted
            and set(template.roles)
            == set(goal.known_roles) | set(goal.proposition_roles)
        ):
            fact_ref, false_ref = refuted[0]
            premises = (false_ref, fact_ref)
            runtime.rule(
                "EXPLICIT_REFUTATION",
                logical_depth=0,
                detail="exact matrix formula pattern",
            )
            return InferenceOutcome(
                LogicalStatus.DISPROVED,
                StopReason.GOAL_REFUTED,
                ExistingRefConclusion(false_ref),
                premises,
                premises,
                domain_from_premises(self.core, premises),
                len(candidates),
                proof_support=(
                    ProofSupport(premises, rule_id="EXPLICIT_REFUTATION"),
                ),
                proof_context=proof_context,
            )
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            None,
            len(candidates),
            ("No asserted matrix fact matches the formula-valued role",),
            proof_context=proof_context,
        )

    @staticmethod
    def _pattern_label(pattern: FormulaPattern) -> str:
        if pattern.operator is None:
            assert pattern.ref is not None
            return f"{pattern.ref.kind.value}:{pattern.ref.uid}"
        return (
            f"{pattern.operator}("
            + ",".join(ModalInferenceEngine._pattern_label(item) for item in pattern.members)
            + ")"
        )
