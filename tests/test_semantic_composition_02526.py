from __future__ import annotations

from dataclasses import replace

import pytest

from ah.model import ActantRole
from ah.perception.contracts import (
    ActantCandidate,
    AssertionCandidate,
    ConditionalCandidate,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
    QuantifierCandidate,
    QuantifierKind,
)
from ah.perception.semantic_composition import (
    SemanticCompositionError,
    reconcile_quantifier_scope,
    validate_semantic_composition,
)


def _assertion(local_id: str, *, negated: bool = False, actants=()) -> AssertionCandidate:
    return AssertionCandidate(
        local_id=local_id,
        predicate=PredicateCandidate(surface=f"predicate-{local_id}"),
        actants=tuple(actants),
        negated=negated,
    )


def _ref(local_id: str) -> PropositionExprCandidate:
    return PropositionExprCandidate.ref_expr(local_id)


def _not(expr: PropositionExprCandidate) -> PropositionExprCandidate:
    return PropositionExprCandidate(PropositionOperator.NOT, members=(expr,))


def _and(*members: PropositionExprCandidate) -> PropositionExprCandidate:
    return PropositionExprCandidate(PropositionOperator.AND, members=tuple(members))


def test_consumed_quantifier_negation_removes_only_leaf_polarity_not() -> None:
    before = PerceptionResult(
        "not every engineer approved and alarm sounded",
        assertions=(
            _assertion("a1", negated=True),
            _assertion("a2"),
        ),
        proposition_roots=(
            PropositionRootCandidate(
                "F1",
                _and(_not(_ref("a1")), _ref("a2")),
            ),
        ),
    )

    after = reconcile_quantifier_scope(
        before,
        (replace(before.assertions[0], negated=False), before.assertions[1]),
    )

    assert after.proposition_roots[0].expression == _and(_ref("a1"), _ref("a2"))


def test_independent_outer_not_survives_quantifier_negation_consumption() -> None:
    before = PerceptionResult(
        "it is false that not every engineer approved",
        assertions=(_assertion("a1", negated=True),),
        proposition_roots=(
            PropositionRootCandidate(
                "F1",
                _not(_not(_ref("a1"))),
            ),
        ),
    )

    after = reconcile_quantifier_scope(
        before,
        (replace(before.assertions[0], negated=False),),
    )

    assert after.proposition_roots[0].expression == _not(_ref("a1"))


def test_modal_scope_keeps_modal_operator_while_leaf_polarity_is_reconciled() -> None:
    before = PerceptionResult(
        "every engineer must not approve and alarm sounded",
        assertions=(
            _assertion("a1", negated=True),
            _assertion("a2"),
        ),
        proposition_roots=(
            PropositionRootCandidate(
                "F1",
                PropositionExprCandidate(
                    PropositionOperator.REQUIRED,
                    members=(_and(_not(_ref("a1")), _ref("a2")),),
                ),
            ),
        ),
    )

    after = reconcile_quantifier_scope(
        before,
        (replace(before.assertions[0], negated=False), before.assertions[1]),
    )
    expr = after.proposition_roots[0].expression

    assert expr.operator is PropositionOperator.REQUIRED
    assert expr.members == (_and(_ref("a1"), _ref("a2")),)


def test_missing_leaf_polarity_wrapper_fails_closed_after_consumption() -> None:
    before = PerceptionResult(
        "not every engineer approved and alarm sounded",
        assertions=(
            _assertion("a1", negated=True),
            _assertion("a2"),
        ),
        proposition_roots=(
            PropositionRootCandidate("F1", _and(_ref("a1"), _ref("a2"))),
        ),
    )

    with pytest.raises(SemanticCompositionError, match="exactly one leaf-polarity NOT"):
        reconcile_quantifier_scope(
            before,
            (replace(before.assertions[0], negated=False), before.assertions[1]),
        )


def test_dangling_logical_and_conditional_refs_fail_closed() -> None:
    logical = PerceptionResult(
        "source",
        assertions=(_assertion("a1"),),
        proposition_roots=(
            PropositionRootCandidate("F1", _and(_ref("a1"), _ref("missing"))),
        ),
    )
    with pytest.raises(SemanticCompositionError, match="dangling proposition refs"):
        validate_semantic_composition(logical)

    conditional = PerceptionResult(
        "source",
        assertions=(_assertion("a1"),),
        conditionals=(ConditionalCandidate(("a1",), ("missing",)),),
    )
    with pytest.raises(SemanticCompositionError, match="dangling branch refs"):
        validate_semantic_composition(conditional)


def test_nested_proposition_cycle_fails_closed() -> None:
    a1 = _assertion(
        "a1",
        actants=(ActantCandidate(role=ActantRole.OBJECT, proposition=_ref("a2")),),
    )
    a2 = _assertion(
        "a2",
        actants=(ActantCandidate(role=ActantRole.OBJECT, proposition=_ref("a1")),),
    )

    with pytest.raises(SemanticCompositionError, match="cyclic nested proposition scope"):
        validate_semantic_composition(PerceptionResult("source", assertions=(a1, a2)))


def test_quantified_actant_requires_explicit_bound_variable_handle() -> None:
    quantified = ActantCandidate(
        role=ActantRole.SUBJECT,
        mention="every engineer",
        quantifier=QuantifierCandidate(
            QuantifierKind.FORALL,
            "every",
            restriction_lemma="engineer",
        ),
    )
    result = PerceptionResult(
        "every engineer approved",
        assertions=(_assertion("a1", actants=(quantified,)),),
    )

    with pytest.raises(SemanticCompositionError, match="bound-variable handle"):
        validate_semantic_composition(result)


def test_valid_nested_and_conditional_composition_is_accepted() -> None:
    a2 = _assertion("a2")
    a1 = _assertion(
        "a1",
        actants=(ActantCandidate(role=ActantRole.OBJECT, proposition=_ref("a2")),),
    )
    result = PerceptionResult(
        "source",
        assertions=(a1, a2),
        conditionals=(
            ConditionalCandidate(
                ("a1",),
                ("a2",),
                antecedent_expr=_ref("a1"),
                consequent_expr=_ref("a2"),
            ),
        ),
    )

    validate_semantic_composition(result)
