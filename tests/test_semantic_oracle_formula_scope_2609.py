from __future__ import annotations

from ah.diagnostics.semantic_oracle import (
    SemanticOracleCase,
    _actual_formula_scope,
    evaluate_semantic_case,
)


def _record(expr: dict) -> dict:
    return {
        "status": "OK",
        "perception_result": {
            "source_text": "Иван не пришёл.",
            "assertions": [
                {
                    "local_id": "A1",
                    "predicate": {
                        "surface": "пришёл",
                        "normalized_hint": "прийти",
                    },
                    "actants": [],
                    "status": "ASSERTED",
                    "negated": True,
                    "quoted": False,
                    "alternatives": [],
                }
            ],
            "queries": [],
            "commands": [],
            "relations": [],
            "relation_hints": [],
            "conditionals": [],
            "proposition_roots": [
                {
                    "local_id": "F1",
                    "expression": expr,
                    "operator_source_refs": [],
                }
            ],
        },
        "integration_commit": {
            "assertions": [
                {
                    "local_id": "A1",
                    "ref": {"uid": "N1", "kind": "N"},
                    "domain": "P",
                    "created": True,
                    "ambiguous": False,
                    "semantic_scope": "LOGICAL",
                }
            ],
            "conditionals": [],
            "formulas": [],
            "existentials": [],
            "universals": [],
            "clarifications": [],
            "clarification_required": False,
        },
        "queries": [],
        "ah_diff": {"added": {}, "removed": {}, "changed": {}},
    }


def _snapshot() -> dict:
    return {
        "S1": {
            "uid": "S1",
            "kind": "S",
            "domain": None,
            "forms": ["прийти"],
        },
        "T1": {
            "uid": "T1",
            "kind": "T",
            "domain": "C",
            "predicate": {"uid": "S1", "kind": "S"},
            "roles": [],
        },
        "N1": {
            "uid": "N1",
            "kind": "N",
            "domain": "P",
            "weight": 1.0,
            "template": {"uid": "T1", "kind": "T"},
            "actants": {},
            "properties": {},
            "meta": {"semantic_scope": "LOGICAL"},
        },
    }


def _oracle() -> SemanticOracleCase:
    return SemanticOracleCase(
        1,
        "Иван не пришёл.",
        "EXACT",
        {
            "perception": {
                "assertions": [
                    {
                        "key": "a1",
                        "predicate": "прийти",
                        "negated": True,
                        "roles": {},
                    }
                ],
                "queries": [],
            },
            "integration": {"must_succeed": True},
        },
    )


def test_actual_formula_scope_distinguishes_direct_leaf_not() -> None:
    leaves, negated = _actual_formula_scope(
        {
            "proposition_roots": [
                {
                    "expression": {
                        "operator": "AND",
                        "members": [
                            {"operator": "REF", "ref": "A1"},
                            {
                                "operator": "NOT",
                                "members": [{"operator": "REF", "ref": "A2"}],
                            },
                        ],
                    }
                }
            ]
        }
    )

    assert leaves == frozenset({"A1", "A2"})
    assert negated == frozenset({"A2"})


def test_formula_leaf_not_keeps_local_canonical_member_positive() -> None:
    record = _record(
        {
            "operator": "NOT",
            "members": [{"operator": "REF", "ref": "A1"}],
        }
    )

    verdict = evaluate_semantic_case(record, _oracle(), _snapshot(), {})

    assert verdict.status == "PASS"
    negated_check = next(
        item for item in verdict.checks
        if item["name"] == "canonical.assertions.a1.negated"
    )
    assert negated_check["ok"] is True
    assert negated_check["expected"] is False


def test_formula_membership_alone_does_not_hide_lost_negation() -> None:
    record = _record({"operator": "REF", "ref": "A1"})

    verdict = evaluate_semantic_case(record, _oracle(), _snapshot(), {})

    assert verdict.status == "FAIL"
    negated_check = next(
        item for item in verdict.checks
        if item["name"] == "canonical.assertions.a1.negated"
    )
    assert negated_check["ok"] is False
