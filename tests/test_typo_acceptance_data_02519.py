from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import pytest

from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import load_semantic_oracle, validate_oracle_alignment
from ah.perception.lexical_recovery import LexicalRecovery
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import Pymorphy3Morphology


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_typo" / "cases.txt"
ORACLE = ROOT / "data" / "acceptance_typo" / "oracle.json"


def test_typo_acceptance_corpus_is_aligned_and_covers_the_required_frontier() -> None:
    cases = load_acceptance_cases(CASES)
    oracle = load_semantic_oracle(ORACLE)
    validate_oracle_alignment(cases, oracle)
    assert len(cases) == len(oracle) == 81
    assert all(item.grade == "EXACT" for item in oracle)
    assert Counter(item.family for item in oracle) == {
        "typo_baseline": 10,
        "typo_edits": 15,
        "typo_roles": 12,
        "typo_inversion": 12,
        "typo_ellipsis": 10,
        "typo_multiple": 8,
        "typo_negative_oov": 8,
        "typo_ambiguous": 6,
    }

    tags = {tag for item in oracle for tag in item.tags}
    assert {
        "omission", "extra_letter", "substitution", "transposition",
        "keyboard_neighbor", "yo_e", "ending", "short", "long",
        "subject", "object", "location", "recipient", "time", "duration",
        "tool", "material", "source", "inversion", "ellipsis",
        "multiple_errors", "name", "term", "acronym", "code", "neologism",
        "rare_word", "ambiguous", "fail_closed",
    } <= tags


def test_ambiguous_cases_are_explicit_fail_closed_oracles() -> None:
    oracle = load_semantic_oracle(ORACLE)
    ambiguous = [item for item in oracle if item.family == "typo_ambiguous"]
    assert len(ambiguous) == 6
    for item in ambiguous:
        lexical = item.expectation["lexical_recovery"]
        assert len(lexical) == 1
        assert lexical[0]["status"] == "AMBIGUOUS"
        assert lexical[0]["normalized"] is None
        assert len(lexical[0]["alternatives_contain"]) >= 2
        assert item.expectation["perception"]["must_parse"] is False
        assert item.expectation["integration"]["must_succeed"] is False
        assert (
            item.expectation["integration"]["safe_error_contains"]
            == "ambiguous lexical recovery"
        )


class _ControlledShortlistReranker:
    """Acceptance-only scorer proving that expected candidates survive narrowing."""

    def __init__(self, preferred: tuple[str, ...]) -> None:
        self.preferred = {item.casefold() for item in preferred}

    def rank(self, context: str, candidates: tuple[str, ...]) -> dict[str, float]:
        del context
        return {
            candidate: float(candidate.casefold() in self.preferred)
            for candidate in candidates
        }


@pytest.fixture(scope="module")
def morphology() -> Pymorphy3Morphology:
    return Pymorphy3Morphology()


def test_all_typo_oracles_survive_deterministic_generation_and_constraints(
    morphology: Pymorphy3Morphology,
) -> None:
    """Offline preflight for all 81 cases; full semantics remains an acceptance run."""
    for case in load_semantic_oracle(ORACLE):
        expected = tuple(case.expectation["lexical_recovery"])
        preferred = tuple(
            str(item["normalized"])
            for item in expected
            if item["status"] == "CORRECTED_HIGH_CONFIDENCE"
            and item.get("normalized") is not None
        )
        reranker = (
            None
            if case.family == "typo_ambiguous"
            else _ControlledShortlistReranker(preferred)
        )
        graph = LinguisticCandidateBuilder(
            morphology,
            lexical_recovery=LexicalRecovery(
                morphology,
                semantic_reranker=reranker,
            ),
        ).build(case.text)

        for wanted in expected:
            matches = [
                token.recovery
                for token in graph.tokens
                if token.provenance_text.casefold() == str(wanted["raw"]).casefold()
            ]
            assert len(matches) == 1, (case.text, wanted, matches)
            actual = matches[0]
            assert actual is not None
            assert actual.status.value == wanted["status"], (case.text, wanted, actual)
            expected_normalized = wanted.get("normalized")
            assert (
                None if actual.normalized_text is None else actual.normalized_text.casefold()
            ) == (
                None if expected_normalized is None else str(expected_normalized).casefold()
            ), (case.text, wanted, actual)
            alternatives = {item.casefold() for item in actual.alternatives}
            assert {
                str(item).casefold()
                for item in wanted.get("alternatives_contain", ())
            } <= alternatives, (case.text, wanted, actual)


def test_acceptance_examples_are_not_imported_by_production_code() -> None:
    for path in (ROOT / "src" / "ah" / "perception").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "build_typo_acceptance" not in source
        assert "acceptance_typo" not in source


def test_typo_oracle_raw_forms_are_absent_from_production_code() -> None:
    oracle = load_semantic_oracle(ORACLE)
    controlled_raw_forms = {
        str(item["raw"]).casefold()
        for case in oracle
        for item in case.expectation["lexical_recovery"]
        if item["status"] in {"CORRECTED_HIGH_CONFIDENCE", "AMBIGUOUS"}
    }
    assert len(controlled_raw_forms) == 44

    production_tokens: set[str] = set()
    for path in (ROOT / "src" / "ah" / "perception").rglob("*.py"):
        production_tokens.update(
            token.casefold()
            for token in re.findall(
                r"(?<![А-Яа-яЁё])[А-Яа-яЁё]+(?![А-Яа-яЁё])",
                path.read_text(encoding="utf-8"),
            )
        )

    assert controlled_raw_forms.isdisjoint(production_tokens)
