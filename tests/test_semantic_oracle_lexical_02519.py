from __future__ import annotations

from ah.diagnostics.semantic_oracle import SemanticOracleCase, evaluate_semantic_case


def _case() -> SemanticOracleCase:
    return SemanticOracleCase(
        1,
        "ктт",
        "EXACT",
        {
            "lexical_recovery": [{
                "raw": "ктт",
                "status": "AMBIGUOUS",
                "normalized": None,
                "alternatives_contain": ["кот", "кит"],
            }],
            "perception": {
                "must_parse": False,
                "assertions": [],
                "queries": [],
                "relations": [],
                "conditionals": [],
            },
            "integration": {
                "must_succeed": False,
                "safe_error_contains": "ambiguous lexical recovery",
            },
        },
        family="typo_ambiguous",
    )


def _record(*, second: str = "кит") -> dict:
    return {
        "status": "ERROR",
        "error": "ambiguous lexical recovery: ктт",
        "linguistic_candidate_graph": {
            "tokens": [{
                "text": "ктт",
                "raw_text": "ктт",
                "recovery": {
                    "raw_text": "ктт",
                    "normalized_text": None,
                    "status": "AMBIGUOUS",
                    "alternatives": ["кот", second],
                },
            }],
        },
    }


def test_oracle_grades_lexical_recovery_even_when_parser_fails_closed() -> None:
    verdict = evaluate_semantic_case(_record(), _case(), {}, {})
    assert verdict.status == "PASS", verdict.failures
    assert any(item["name"] == "lexical.1.status" for item in verdict.checks)


def test_oracle_rejects_a_missing_required_ambiguity_alternative() -> None:
    verdict = evaluate_semantic_case(_record(second="лес"), _case(), {}, {})
    assert verdict.status == "FAIL"
    assert {
        item["name"] for item in verdict.failures
    } == {"lexical.1.alternative.кит"}

