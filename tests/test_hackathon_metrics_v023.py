from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ah.config import load_config
from ah.diagnostics import (
    M2QuestionObservation,
    run_m3_gc_acceptance,
    score_m1_acceptance_bundle,
    score_m1_role_f1,
    score_m2_explainability,
    score_m4_comparison,
    score_m5_robustness,
    run_tick_benchmark,
)


PROJECT = Path(__file__).resolve().parents[1]


class HackathonMetricsV023Tests(unittest.TestCase):
    def test_m1_multiset_matching_and_role_weights(self) -> None:
        gold = [
            (1, "читать", "SUBJECT", "Иван"),
            (1, "читать", "OBJECT", "книга"),
            (2, "жить", "SUBJECT", "Мария"),
            (2, "жить", "LOCATION", "Москва"),
        ]
        predicted = [
            (1, "читать", "SUBJECT", "иван"),
            (1, "читать", "OBJECT", "журнал"),
            (2, "жить", "SUBJECT", "Мария"),
            (2, "жить", "LOCATION", "Москва"),
        ]
        report = score_m1_role_f1(gold, predicted)
        rows = {row.role: row for row in report.roles}
        self.assertEqual(rows["SUBJECT"].correct, 2)
        self.assertAlmostEqual(rows["SUBJECT"].f1, 1.0)
        self.assertEqual(rows["OBJECT"].correct, 0)
        self.assertAlmostEqual(rows["LOCATION"].f1, 1.0)
        # weighted mean = (2*1 + 2*0 + 1*1) / 5
        self.assertAlmostEqual(report.weighted_mean, 0.6)
        self.assertTrue(report.mandatory_roles_present)

    def test_m1_acceptance_bundle_reads_oracle_and_turns(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "oracle_used.json").write_text(
                json.dumps({
                    "version": 1,
                    "cases": [{
                        "text": "Иван читает книгу.",
                        "expect": {"perception": {"assertions": [{
                            "predicate": "читать",
                            "roles": {"SUBJECT": "Иван", "OBJECT": "книга"},
                        }]}}
                    }]
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "turn_001.json").write_text(
                json.dumps({
                    "index": 1,
                    "perception_result": {"assertions": [{
                        "predicate": {"surface": "читает", "normalized_hint": "читать"},
                        "actants": [
                            {"role": "SUBJECT", "mention": "Иван", "normalized_hint": "иван"},
                            {"role": "OBJECT", "mention": "книгу", "normalized_hint": "книга"},
                        ],
                    }]},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            report = score_m1_acceptance_bundle(root)
        self.assertAlmostEqual(report.weighted_mean, 1.0)

    def test_m2_formula_exactly_uses_correct_depth_and_trace_gate(self) -> None:
        observations = []
        for index in range(20):
            depth = (index % 6) + 1
            observations.append(M2QuestionObservation(True, depth, True, str(index)))
        report = score_m2_explainability(observations)
        expected = sum(item.depth / 6 for item in observations) / 20
        self.assertAlmostEqual(report.explain_score, expected)
        broken = list(observations)
        broken[0] = M2QuestionObservation(True, 1, False, "broken")
        report_broken = score_m2_explainability(broken)
        self.assertLess(report_broken.explain_score, report.explain_score)

    def test_m2_rejects_wrong_hidden_set_shape(self) -> None:
        with self.assertRaises(ValueError):
            score_m2_explainability([M2QuestionObservation(True, 1, True)])

    def test_m3_committee_shape_removes_200_and_preserves_live_component(self) -> None:
        config = load_config(PROJECT / "config/default.toml")
        report = run_m3_gc_acceptance(config)
        self.assertTrue(report.passed)
        self.assertEqual(report.orphan_nodes_before, 200)
        self.assertEqual(report.orphan_nodes_after, 0)
        self.assertEqual(report.live_nodes_before, report.live_nodes_after)
        self.assertLessEqual(report.ticks_until_orphans_gone or 999, 50)
        self.assertAlmostEqual(report.gc_efficiency, 1.0)
        self.assertAlmostEqual(report.live_preservation, 1.0)

    def test_tick_benchmark_uses_at_least_1000_n_plus_l_units(self) -> None:
        config = load_config(PROJECT / "config/default.toml")
        report = run_tick_benchmark(config, target_graph_units=1000, measured_ticks=5, warmup_ticks=1)
        self.assertGreaterEqual(report.graph_units_n_plus_l, 1000)
        self.assertTrue(report.passes_500ms)

    def test_m4_and_m5_formulas_follow_statement(self) -> None:
        m4 = score_m4_comparison(
            ah_explainability=0.8,
            rag_explainability=0.3,
            ah_hallucination=0.1,
            rag_hallucination=0.4,
        )
        self.assertAlmostEqual(m4.delta_explainability, 0.5)
        self.assertAlmostEqual(m4.delta_hallucination, 0.3)
        m5 = score_m5_robustness(
            ah_slm_f1=0.6,
            rag_slm_f1=0.4,
            ah_llm_f1=0.8,
            rag_llm_f1=0.8,
        )
        self.assertAlmostEqual(m5.robustness_gain, 0.5)


if __name__ == "__main__":
    unittest.main()
