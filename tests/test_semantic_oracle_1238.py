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
        self.assertEqual(len(cases), 200)
        self.assertEqual(len(oracle), 200)
        self.assertEqual(len({item.family for item in oracle}), 27)
        self.assertTrue(all(item.grade == "EXACT" for item in oracle))
        self.assertTrue(all(item.family != "uncategorized" for item in oracle))
        self.assertEqual(len({item.scenario_id for item in oracle}), 149)
        self.assertEqual({item.scenario_id for item in oracle[:40]}, {"regression40_frozen"})

    def test_frozen_regression40_corpus_remains_available(self) -> None:
        cases = load_acceptance_cases("data/acceptance_cases_regression40.txt")
        oracle = load_semantic_oracle("data/acceptance_oracle_regression40.json")
        validate_oracle_alignment(cases, oracle)
        self.assertEqual(len(cases), 40)
        self.assertEqual(len(oracle), 40)

    def test_broad200_keeps_first_40_texts_and_expectations_frozen(self) -> None:
        import json

        broad = json.loads(open("data/acceptance_oracle.json", encoding="utf-8").read())
        frozen = json.loads(open("data/acceptance_oracle_regression40.json", encoding="utf-8").read())
        self.assertEqual(
            [item["text"] for item in broad["cases"][:40]],
            [item["text"] for item in frozen["cases"]],
        )
        self.assertEqual(
            [item["expect"] for item in broad["cases"][:40]],
            [item["expect"] for item in frozen["cases"]],
        )

    def test_broad200_new_pressure_is_balanced_across_sixteen_families(self) -> None:
        from collections import Counter

        oracle = load_semantic_oracle("data/acceptance_oracle.json")
        counts = Counter(item.family for item in oracle[40:])
        self.assertEqual(len(counts), 16)
        self.assertEqual(set(counts.values()), {10})
        self.assertTrue(all(item.grade == "EXACT" for item in oracle[40:]))
        # Only deliberate T-evolution and assertion/query chains share state.
        self.assertEqual(
            [item.scenario_id for item in oracle[70:74]],
            ["template_open_evolution"] * 4,
        )
        self.assertEqual(
            [item.scenario_id for item in oracle[160:162]],
            ["query_tool"] * 2,
        )


    def test_broad200_case_100_expects_explicit_then_follow_relation(self) -> None:
        oracle = load_semantic_oracle("data/acceptance_oracle.json")
        case = oracle[99]
        self.assertEqual(case.text, "Анна взяла книгу, а затем положила её на стол.")
        self.assertEqual(
            case.expectation["perception"]["relations"],
            [{"id": "FOLLOW", "source": "a1", "target": "a2"}],
        )

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
                "T_H_EVENT": {
                    "uid": "T_H_EVENT", "kind": "T", "domain": "C",
                    "predicate": {"uid": "S_H_EVENT", "kind": "S"},
                    "roles": ["SUBJECT", "OBJECT", "TIME"],
                },
                "N_H": {
                    "uid": "N_H", "kind": "N", "domain": "H",
                    "template": {"uid": "T_H_EVENT", "kind": "T"},
                    "meta": {"event_instance": True},
                },
                "K_H": {"uid": "K_H", "kind": "K", "domain": "H"},
                "L_H_FOLLOW": {
                    "uid": "L_H_FOLLOW", "kind": "L", "domain": None,
                    "relation_id": "FOLLOW",
                    "source": {"uid": "N_PREV_H", "kind": "N"},
                    "target": {"uid": "N_H", "kind": "N"},
                },
            }},
            "interaction_context_after": {"pending_clarification_refs": []},
        }
        snapshot = {
            "N_PREV_H": {"uid": "N_PREV_H", "kind": "N", "domain": "H"},
            "T_H_EVENT": record["ah_diff"]["added"]["T_H_EVENT"],
            "N_H": record["ah_diff"]["added"]["N_H"],
            "K_H": {"uid": "K_H", "kind": "K", "domain": "H"},
            "L_H_FOLLOW": record["ah_diff"]["added"]["L_H_FOLLOW"],
        }
        verdict = evaluate_semantic_case(record, oracle, snapshot, {})
        self.assertEqual(verdict.status, "PASS", verdict.failures)

    def test_cp_semantic_addition_count_still_counts_links_touching_cp(self) -> None:
        oracle = SemanticOracleCase(
            1, "A потому что B.", "EXACT",
            {
                "perception": {
                    "must_parse": True, "assertions": [], "queries": [],
                    "relations": [], "conditionals": [],
                },
                "integration": {
                    "must_succeed": True,
                    "world_assertion_count": 0,
                    "cp_semantic_addition_count": 1,
                },
            },
        )
        link = {
            "uid": "L_CAUSE", "kind": "L", "domain": None,
            "relation_id": "CAUSE",
            "source": {"uid": "N_CAUSE", "kind": "N"},
            "target": {"uid": "N_EFFECT", "kind": "N"},
        }
        record = {
            "status": "OK",
            "perception_result": {
                "assertions": [], "queries": [], "commands": [],
                "relations": [], "conditionals": [],
            },
            "integration_commit": {
                "assertions": [], "conditionals": [],
                "clarification_required": False, "clarifications": [],
            },
            "queries": [],
            "ah_diff": {"added": {"L_CAUSE": link}},
        }
        snapshot = {
            "N_CAUSE": {"uid": "N_CAUSE", "kind": "N", "domain": "C"},
            "N_EFFECT": {"uid": "N_EFFECT", "kind": "N", "domain": "C"},
            "L_CAUSE": link,
        }
        verdict = evaluate_semantic_case(record, oracle, snapshot, {})
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

    def test_query_outcome_none_is_semantic_fail_not_evaluator_crash(self) -> None:
        oracle = SemanticOracleCase(
            1,
            "Когда Виктор встретил Алексея?",
            "EXACT",
            {
                "perception": {
                    "must_parse": False,
                    "assertions": [],
                    "queries": [],
                    "relations": [],
                    "conditionals": [],
                },
                "integration": {
                    "must_succeed": True,
                    "query_outcomes": [
                        {"status": "PROVED", "role": "TIME", "value": "утро"}
                    ],
                },
            },
        )
        record = {
            "status": "OK",
            "perception_result": None,
            "integration_commit": {
                "assertions": [],
                "clarification_required": False,
                "clarifications": [],
            },
            "queries": [{"outcome": None}],
        }
        verdict = evaluate_semantic_case(record, oracle, {}, {})
        self.assertEqual(verdict.status, "FAIL")
        failures = {item["name"] for item in verdict.failures}
        self.assertIn("inference.q1.status", failures)
        self.assertIn("inference.q1.role", failures)
        self.assertIn("inference.q1.value", failures)


if __name__ == "__main__":
    unittest.main()
