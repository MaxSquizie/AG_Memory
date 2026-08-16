from __future__ import annotations

import unittest

from ah.diagnostics.semantic_oracle import (
    SemanticOracleCase,
    evaluate_semantic_case,
    load_semantic_oracle,
    validate_oracle_alignment,
)
from ah.diagnostics.acceptance_runner import load_acceptance_cases


class SemanticOracle1238Tests(unittest.TestCase):
    def test_repository_cases_and_oracle_are_strictly_aligned(self) -> None:
        cases = load_acceptance_cases("data/acceptance_cases.txt")
        oracle = load_semantic_oracle("data/acceptance_oracle.json")
        validate_oracle_alignment(cases, oracle)
        self.assertEqual(len(cases), 40)
        self.assertEqual(len(oracle), 40)

    def test_explicit_role_coverage_rejects_an_underwide_canonical_template(self) -> None:
        oracle = SemanticOracleCase(
            1,
            "Иван подарил Марии книгу.",
            "EXACT",
            {
                "perception": {
                    "assertions": [
                        {
                            "key": "a1",
                            "predicate": "подарить",
                            "status": "ASSERTED",
                            "negated": False,
                            "roles": {
                                "SUBJECT": "Иван",
                                "RECIPIENT": "Мария",
                                "OBJECT": "книга",
                            },
                        }
                    ],
                    "queries": [],
                    "relations": [],
                    "conditionals": [],
                },
                "integration": {"must_succeed": True, "domains": {"a1": "C"}},
            },
        )
        record = {
            "status": "OK",
            "perception_result": {
                "assertions": [
                    {
                        "local_id": "A1",
                        "predicate": {"surface": "подарил", "normalized_hint": "подарить"},
                        "actants": [
                            {"role": "SUBJECT", "mention": "Иван", "normalized_hint": "Иван"},
                            {"role": "RECIPIENT", "mention": "Марии", "normalized_hint": "Мария"},
                            {"role": "OBJECT", "mention": "книгу", "normalized_hint": "книга"},
                        ],
                        "alternatives": [],
                        "negated": False,
                        "status": "ASSERTED",
                    }
                ],
                "queries": [],
                "commands": [],
                "relations": [],
                "conditionals": [],
            },
            "integration_commit": {
                "assertions": [
                    {
                        "local_id": "A1",
                        "ref": {"uid": "N_GIVE", "kind": "N"},
                        "domain": "C",
                        "created": True,
                    }
                ],
                "clarification_required": False,
                "clarifications": [],
            },
            "queries": [],
        }
        snapshot = {
            "S_GIVE": {"uid": "S_GIVE", "kind": "S", "domain": None, "forms": ["подарить", "подарил"]},
            "T_GIVE": {
                "uid": "T_GIVE",
                "kind": "T",
                "domain": "C",
                "predicate": {"uid": "S_GIVE", "kind": "S"},
                "roles": ["SUBJECT", "OBJECT"],
            },
            "M_IVAN": {
                "uid": "M_IVAN", "kind": "M", "domain": "C",
                "properties": {"name": {"value": "Иван"}}, "meta": {},
            },
            "M_MARIA": {
                "uid": "M_MARIA", "kind": "M", "domain": "C",
                "properties": {"name": {"value": "Мария"}}, "meta": {},
            },
            "M_BOOK": {
                "uid": "M_BOOK", "kind": "M", "domain": "C",
                "properties": {"name": {"value": "книга"}}, "meta": {},
            },
            "N_GIVE": {
                "uid": "N_GIVE",
                "kind": "N",
                "domain": "C",
                "template": {"uid": "T_GIVE", "kind": "T"},
                "actants": {
                    "SUBJECT": {"uid": "M_IVAN", "kind": "M"},
                    "RECIPIENT": {"uid": "M_MARIA", "kind": "M"},
                    "OBJECT": {"uid": "M_BOOK", "kind": "M"},
                },
                "properties": {}, "meta": {}, "weight": 0.4,
            },
        }
        requirements: dict[str, set[str]] = {}
        verdict = evaluate_semantic_case(record, oracle, snapshot, requirements)
        self.assertEqual(verdict.status, "FAIL")
        failures = {item["name"] for item in verdict.failures}
        self.assertIn("templates.подарить.explicit_role_coverage", failures)

    def test_canonical_if_with_scoped_members_is_semantic_pass(self) -> None:
        oracle = SemanticOracleCase(
            1,
            "Если Иван придёт, Мария уйдёт.",
            "EXACT",
            {
                "perception": {
                    "must_parse": True,
                    "assertions": [
                        {
                            "key": "a1", "predicate": "прийти", "status": "CONDITIONAL",
                            "negated": False, "roles": {"SUBJECT": "Иван"},
                        },
                        {
                            "key": "a2", "predicate": "уйти", "status": "CONDITIONAL",
                            "negated": False, "roles": {"SUBJECT": "Мария"},
                        },
                    ],
                    "queries": [], "relations": [],
                    "conditionals": [{"if": ["a1"], "then": ["a2"]}],
                },
                "integration": {
                    "must_succeed": True,
                    "world_assertion_count": 0,
                    "conditionals": [{"if": ["прийти"], "then": ["уйти"]}],
                },
            },
        )
        record = {
            "status": "OK",
            "perception_result": {
                "assertions": [
                    {
                        "local_id": "A1",
                        "predicate": {"surface": "придёт", "normalized_hint": "прийти"},
                        "actants": [{"role": "SUBJECT", "mention": "Иван", "normalized_hint": "Иван"}],
                        "alternatives": [], "negated": False, "status": "CONDITIONAL",
                    },
                    {
                        "local_id": "A2",
                        "predicate": {"surface": "уйдёт", "normalized_hint": "уйти"},
                        "actants": [{"role": "SUBJECT", "mention": "Мария", "normalized_hint": "Мария"}],
                        "alternatives": [], "negated": False, "status": "CONDITIONAL",
                    },
                ],
                "queries": [], "commands": [], "relations": [],
                "conditionals": [{"antecedent_refs": ["A1"], "consequent_refs": ["A2"]}],
            },
            "integration_commit": {
                "assertions": [],
                "conditionals": [{
                    "ref": {"uid": "G_IF", "kind": "G"},
                    "antecedent": {"uid": "N_COME", "kind": "N"},
                    "consequent": {"uid": "N_LEAVE", "kind": "N"},
                    "member_refs": [
                        {"uid": "N_COME", "kind": "N"},
                        {"uid": "N_LEAVE", "kind": "N"},
                    ],
                }],
                "clarification_required": False, "clarifications": [],
            },
            "queries": [],
        }
        snapshot = {
            "S_COME": {"uid": "S_COME", "kind": "S", "domain": None, "forms": ["придёт", "прийти"]},
            "S_LEAVE": {"uid": "S_LEAVE", "kind": "S", "domain": None, "forms": ["уйти", "уйдёт"]},
            "T_COME": {
                "uid": "T_COME", "kind": "T", "domain": "C",
                "predicate": {"uid": "S_COME", "kind": "S"}, "roles": ["SUBJECT"],
            },
            "T_LEAVE": {
                "uid": "T_LEAVE", "kind": "T", "domain": "C",
                "predicate": {"uid": "S_LEAVE", "kind": "S"}, "roles": ["SUBJECT"],
            },
            "N_COME": {
                "uid": "N_COME", "kind": "N", "domain": "C",
                "template": {"uid": "T_COME", "kind": "T"},
                "actants": {}, "properties": {},
                "meta": {"semantic_scope": "CONDITIONAL"}, "weight": 0.4,
            },
            "N_LEAVE": {
                "uid": "N_LEAVE", "kind": "N", "domain": "C",
                "template": {"uid": "T_LEAVE", "kind": "T"},
                "actants": {}, "properties": {},
                "meta": {"semantic_scope": "CONDITIONAL"}, "weight": 0.4,
            },
            "G_IF": {
                "uid": "G_IF", "kind": "G", "domain": "C", "function_id": "IF",
                "operands": [
                    {"uid": "N_COME", "kind": "N"},
                    {"uid": "N_LEAVE", "kind": "N"},
                ],
            },
        }
        verdict = evaluate_semantic_case(record, oracle, snapshot, {})
        self.assertEqual(verdict.status, "PASS", verdict.failures)

    def test_structural_clarification_is_exact_success_not_runtime_error(self) -> None:
        labels = [
            "«с биноклем» относится к действию «увидел»",
            "«с биноклем» описывает «Петра»",
        ]
        oracle = SemanticOracleCase(
            1, "Иван увидел Петра с биноклем.", "EXACT",
            {
                "perception": {
                    "must_parse": True, "assertions": [], "queries": [],
                    "relations": [], "conditionals": [],
                },
                "integration": {
                    "must_succeed": True, "world_assertion_count": 0,
                    "cp_semantic_addition_count": 0,
                    "clarification": {
                        "required": True, "kind": "STRUCTURAL", "options": labels,
                        "pending_armed": False,
                    },
                },
            },
        )
        record = {
            "status": "OK",
            "perception_result": {
                "assertions": [], "queries": [], "commands": [],
                "relations": [], "conditionals": [],
            },
            "integration_commit": {
                "assertions": [], "conditionals": [],
                "clarification_required": True,
                "clarifications": [{
                    "kind": "STRUCTURAL",
                    "options": [
                        {"index": 1, "ref": {"uid": "K1", "kind": "K"}, "label": labels[0]},
                        {"index": 2, "ref": {"uid": "K2", "kind": "K"}, "label": labels[1]},
                    ],
                }],
            },
            "queries": [],
            "ah_diff": {"added": {
                "N_H": {"uid": "N_H", "kind": "N", "domain": "H"},
                "K_H": {"uid": "K_H", "kind": "K", "domain": "H"},
            }},
            "interaction_context_after": {"pending_clarification_refs": []},
        }
        verdict = evaluate_semantic_case(record, oracle, {}, {})
        self.assertEqual(verdict.status, "PASS", verdict.failures)

    def test_architecture_gap_is_never_counted_as_pass(self) -> None:
        oracle = SemanticOracleCase(
            1,
            "Если A, B.",
            "ARCHITECTURE_GAP",
            {
                "perception": {
                    "must_parse": False,
                    "assertions": [], "queries": [], "relations": [], "conditionals": [],
                },
                "integration": {"must_succeed": False, "safe_error_contains": "gap"},
            },
            "No canonical conditional representation yet",
        )
        record = {"status": "ERROR", "error": "RuntimeError: gap", "parser_diagnostics": []}
        verdict = evaluate_semantic_case(record, oracle, {}, {})
        self.assertEqual(verdict.status, "GAP")


if __name__ == "__main__":
    unittest.main()
