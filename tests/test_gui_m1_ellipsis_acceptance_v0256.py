from pathlib import Path

from ah.diagnostics.acceptance_runner import load_acceptance_cases
from ah.diagnostics.semantic_oracle import load_semantic_oracle, validate_oracle_alignment


def test_ellipsis_acceptance_corpus_schema_and_alignment():
    root = Path(__file__).resolve().parents[1]
    cases_path = root / "data" / "acceptance_ellipsis" / "cases.txt"
    oracle_path = root / "data" / "acceptance_ellipsis" / "oracle.json"
    cases = load_acceptance_cases(cases_path)
    oracle = load_semantic_oracle(oracle_path)
    assert len(cases) == 166
    assert len(oracle) == 166
    validate_oracle_alignment(cases, oracle)


def test_ellipsis_corpus_has_no_case_id_lines():
    root = Path(__file__).resolve().parents[1]
    lines = [line.strip() for line in (root / "data" / "acceptance_ellipsis" / "cases.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert all(not (line.startswith("[") and line.endswith("]")) for line in lines)


def test_ellipsis_v2_contains_composite_frontier_cases():
    root = Path(__file__).resolve().parents[1]
    cases = load_acceptance_cases(root / "data" / "acceptance_ellipsis" / "cases.txt")
    texts = {item.text for item in cases}
    assert "Иван купил журнал, а Мария и Пётр - нет." in texts
    assert "Иван живёт в Москве, Мария - в Казани, Пётр - в Париже, а Слава - бродяга." in texts
    assert "Иван хочет купить книгу, а Мария — журнал." in texts
    assert "Иван купил книгу и положил её на стол, а Мария — журнал на полку." in texts
    assert "Иван купил кнгу, а Мария — журнал." in texts


def test_ellipsis_v2_oracle_covers_interacting_families():
    root = Path(__file__).resolve().parents[1]
    oracle = load_semantic_oracle(root / "data" / "acceptance_ellipsis" / "oracle.json")
    families = {item.family for item in oracle}
    assert {
        "complex_chain",
        "coordination_ellipsis",
        "polarity_chain",
        "role_rich_chain",
        "temporal_locative_combo",
        "antecedent_reset",
        "punctuation_ellipsis",
        "scope_ellipsis",
        "coreference_ellipsis",
        "mixed_adversarial_ellipsis",
    } <= families
