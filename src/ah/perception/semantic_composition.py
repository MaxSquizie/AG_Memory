from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .contracts import (
    AssertionCandidate,
    PerceptionResult,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
)


class SemanticCompositionError(ValueError):
    """Raised when source-level proposition scope cannot be kept internally coherent."""


def _count_ref(expr: PropositionExprCandidate, ref: str) -> int:
    if expr.operator is PropositionOperator.REF:
        return int(expr.ref == ref)
    return sum(_count_ref(member, ref) for member in expr.members)


def _remove_consumed_leaf_not(
    expr: PropositionExprCandidate,
    consumed_refs: frozenset[str],
) -> tuple[PropositionExprCandidate, dict[str, int]]:
    """Remove exactly the predicate-polarity NOT directly wrapping a consumed leaf.

    Logical/whole-scope NOT is preserved. LogicalFormBuilder represents a negated
    assertion leaf as NOT(REF). Therefore an independent outer source-level NOT is
    represented as NOT(NOT(REF)); recursively removing the innermost wrapper leaves
    the genuine outer NOT intact.
    """

    if expr.operator is PropositionOperator.REF:
        return expr, {}

    if expr.operator is PropositionOperator.NOT and len(expr.members) == 1:
        child = expr.members[0]
        if (
            child.operator is PropositionOperator.REF
            and child.ref is not None
            and child.ref in consumed_refs
        ):
            return child, {child.ref: 1}

    members: list[PropositionExprCandidate] = []
    removed: dict[str, int] = {}
    for member in expr.members:
        rewritten, counts = _remove_consumed_leaf_not(member, consumed_refs)
        members.append(rewritten)
        for ref, count in counts.items():
            removed[ref] = removed.get(ref, 0) + count
    if tuple(members) == expr.members:
        return expr, removed
    return replace(expr, members=tuple(members)), removed


def _validate_expression_refs(
    expr: PropositionExprCandidate,
    assertion_refs: frozenset[str],
    *,
    owner: str,
) -> None:
    refs = expr.leaf_refs()
    missing = tuple(ref for ref in refs if ref not in assertion_refs)
    if missing:
        raise SemanticCompositionError(
            f"{owner} contains dangling proposition refs: {', '.join(missing)}"
        )


def _assertion_variants(assertion: AssertionCandidate) -> tuple[AssertionCandidate, ...]:
    return (assertion, *assertion.alternatives)


def _validate_nested_propositions(
    assertions: tuple[AssertionCandidate, ...],
    assertion_refs: frozenset[str],
) -> None:
    adjacency: dict[str, set[str]] = {item.local_id: set() for item in assertions}
    for assertion in assertions:
        for variant in _assertion_variants(assertion):
            for actant in variant.actants:
                proposition = actant.proposition
                if proposition is None:
                    continue
                _validate_expression_refs(
                    proposition,
                    assertion_refs,
                    owner=f"assertion {assertion.local_id} proposition actant",
                )
                adjacency[assertion.local_id].update(proposition.leaf_refs())

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ref: str) -> None:
        if ref in visited:
            return
        if ref in visiting:
            raise SemanticCompositionError(
                f"cyclic nested proposition scope detected at {ref}"
            )
        visiting.add(ref)
        for child in adjacency.get(ref, ()):
            visit(child)
        visiting.remove(ref)
        visited.add(ref)

    for ref in adjacency:
        visit(ref)


def validate_semantic_composition(result: PerceptionResult) -> None:
    """Validate cross-layer source composition before canonical Integration.

    Dataclass contracts validate each candidate locally. This pass validates the
    seams between candidates: proposition leaves must name final assertions,
    operator-source frames must exist, conditional branches must stay grounded,
    nested proposition arguments must not dangle/cycle, and quantified binders
    must carry an explicit runtime variable handle.
    """

    assertion_ids = tuple(item.local_id for item in result.assertions)
    if len(assertion_ids) != len(set(assertion_ids)):
        raise SemanticCompositionError("duplicate assertion local ids in semantic composition")
    assertion_refs = frozenset(assertion_ids)

    root_ids = tuple(item.local_id for item in result.proposition_roots)
    if len(root_ids) != len(set(root_ids)):
        raise SemanticCompositionError("duplicate proposition root local ids")

    for root in result.proposition_roots:
        _validate_expression_refs(
            root.expression,
            assertion_refs,
            owner=f"proposition root {root.local_id}",
        )
        missing_operators = tuple(
            ref for ref in root.operator_source_refs if ref not in assertion_refs
        )
        if missing_operators:
            raise SemanticCompositionError(
                f"proposition root {root.local_id} has dangling operator frames: "
                + ", ".join(missing_operators)
            )

    for index, conditional in enumerate(result.conditionals, start=1):
        branch_refs = (*conditional.antecedent_refs, *conditional.consequent_refs)
        missing = tuple(ref for ref in branch_refs if ref not in assertion_refs)
        if missing:
            raise SemanticCompositionError(
                f"conditional {index} contains dangling branch refs: {', '.join(missing)}"
            )
        if conditional.antecedent_expr is not None:
            _validate_expression_refs(
                conditional.antecedent_expr,
                assertion_refs,
                owner=f"conditional {index} antecedent",
            )
        if conditional.consequent_expr is not None:
            _validate_expression_refs(
                conditional.consequent_expr,
                assertion_refs,
                owner=f"conditional {index} consequent",
            )

    for assertion in result.assertions:
        for variant in _assertion_variants(assertion):
            for actant in variant.actants:
                if actant.quantifier is not None and not actant.entity_ref:
                    raise SemanticCompositionError(
                        f"quantified actant in {assertion.local_id} has no bound-variable handle"
                    )

    _validate_nested_propositions(result.assertions, assertion_refs)


def _rewrite_assertion_proposition_scopes(
    assertion: AssertionCandidate,
    consumed: frozenset[str],
    source_occurrences: dict[str, int],
    removed_total: dict[str, int],
) -> AssertionCandidate:
    def rewrite_variant(variant: AssertionCandidate) -> AssertionCandidate:
        changed = False
        actants = []
        for actant in variant.actants:
            proposition = actant.proposition
            if proposition is None:
                actants.append(actant)
                continue
            for ref in consumed:
                source_occurrences[ref] += _count_ref(proposition, ref)
            rewritten, removed = _remove_consumed_leaf_not(proposition, consumed)
            for ref, count in removed.items():
                removed_total[ref] = removed_total.get(ref, 0) + count
            if rewritten != proposition:
                changed = True
                actants.append(replace(actant, proposition=rewritten))
            else:
                actants.append(actant)
        if not changed:
            return variant
        return replace(variant, actants=tuple(actants))

    rewritten_alternatives = tuple(rewrite_variant(item) for item in assertion.alternatives)
    base_without_alternatives = replace(assertion, alternatives=())
    rewritten_base = rewrite_variant(base_without_alternatives)
    if rewritten_alternatives == assertion.alternatives and rewritten_base == base_without_alternatives:
        return assertion
    return replace(rewritten_base, alternatives=rewritten_alternatives)


def reconcile_quantifier_scope(
    before: PerceptionResult,
    assertions: Iterable[AssertionCandidate],
) -> PerceptionResult:
    """Reconcile proposition polarity after quantifier binder formalization.

    QuantifierFormalizer may move source negation from an assertion body to a
    NOT_FORALL/NOT_EXISTS binder. Logical/modal/conditional/nested composition is
    intentionally built earlier, so every runtime AST copy may still contain the
    old predicate-level NOT. This function removes exactly that stale leaf wrapper
    from all proposition-bearing surfaces and leaves independent outer operators
    untouched. Any mismatch fails closed instead of silently changing formula
    meaning.
    """

    final_assertions = tuple(assertions)
    old_by_id = {item.local_id: item for item in before.assertions}
    new_by_id = {item.local_id: item for item in final_assertions}
    if set(old_by_id) != set(new_by_id):
        raise SemanticCompositionError(
            "quantifier formalization changed assertion identity set"
        )

    consumed = frozenset(
        ref
        for ref, old in old_by_id.items()
        if old.negated and not new_by_id[ref].negated
    )
    removed_total: dict[str, int] = {ref: 0 for ref in consumed}
    source_occurrences: dict[str, int] = {ref: 0 for ref in consumed}

    rewritten_assertions = tuple(
        _rewrite_assertion_proposition_scopes(
            assertion,
            consumed,
            source_occurrences,
            removed_total,
        )
        for assertion in final_assertions
    )

    roots: list[PropositionRootCandidate] = []
    for root in before.proposition_roots:
        for ref in consumed:
            source_occurrences[ref] += _count_ref(root.expression, ref)
        rewritten, removed = _remove_consumed_leaf_not(root.expression, consumed)
        for ref, count in removed.items():
            removed_total[ref] = removed_total.get(ref, 0) + count
        roots.append(
            root if rewritten == root.expression else replace(root, expression=rewritten)
        )

    conditionals = []
    for conditional in before.conditionals:
        antecedent = conditional.antecedent_expr
        consequent = conditional.consequent_expr
        rewritten_antecedent = antecedent
        rewritten_consequent = consequent
        for name, expr in (("antecedent", antecedent), ("consequent", consequent)):
            if expr is None:
                continue
            for ref in consumed:
                source_occurrences[ref] += _count_ref(expr, ref)
            rewritten, removed = _remove_consumed_leaf_not(expr, consumed)
            for ref, count in removed.items():
                removed_total[ref] = removed_total.get(ref, 0) + count
            if name == "antecedent":
                rewritten_antecedent = rewritten
            else:
                rewritten_consequent = rewritten
        if rewritten_antecedent == antecedent and rewritten_consequent == consequent:
            conditionals.append(conditional)
        else:
            conditionals.append(
                replace(
                    conditional,
                    antecedent_expr=rewritten_antecedent,
                    consequent_expr=rewritten_consequent,
                )
            )

    for ref in consumed:
        occurrences = source_occurrences.get(ref, 0)
        removed = removed_total.get(ref, 0)
        if occurrences and removed != occurrences:
            raise SemanticCompositionError(
                "quantifier consumed predicate negation but proposition scope did not "
                f"contain exactly one leaf-polarity NOT per occurrence for {ref}: "
                f"occurrences={occurrences}, removed={removed}"
            )

    result = replace(
        before,
        assertions=rewritten_assertions,
        conditionals=tuple(conditionals),
        proposition_roots=tuple(roots),
    )
    validate_semantic_composition(result)
    return result
