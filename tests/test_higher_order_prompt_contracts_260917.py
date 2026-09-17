from __future__ import annotations

from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts" / "perception"


def test_higher_order_perception_stage_prompts_are_packaged() -> None:
    """Every model-facing stage introduced by higher_order_queries must be explicit.

    Adaptive v3 intentionally fails closed when a stage instruction is absent.  The
    production parser therefore cannot add a semantic probe without shipping its
    corresponding prompt contract.
    """
    required = (
        "binary_relation_frame.txt",
        "query_endpoint_level.txt",
        "query_gap_level.txt",
    )
    missing = [name for name in required if not (PROMPT_DIR / name).is_file()]
    assert not missing, f"missing higher-order perception prompts: {missing}"
    for name in required:
        assert (PROMPT_DIR / name).read_text(encoding="utf-8").strip()
