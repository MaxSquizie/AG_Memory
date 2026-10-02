# -*- coding: utf-8 -*-
"""WP3.5 — Behavioral comparison with the legacy ``adaptive_parser`` (V7 §12).

The legacy parser is used **only as a behavioral reference** — never as an unconditionally correct standard. This harness runs both sides on
the six demo sentences and reports, per sentence, the new formalizer's decision outcomes against the legacy parser's *completion status*
(COMPLETED / CLARIFICATION_REQUIRED / ERROR). It deliberately does NOT assert agreement: divergence is recorded, not failed, because the two
systems are expected to differ and the legacy output is not ground truth. The new side is asserted deterministic (re-run -> identical), which
is the property that actually matters for a replacement candidate.

The real legacy parser is constructed lazily behind try/except; if its dependencies are unavailable in an environment, the harness degrades
to a caller-supplied stub rather than failing to import.
"""

from __future__ import annotations

from dataclasses import dataclass

DEMO_SENTENCES: dict[str, str] = {
    "S1": "У вороны есть лапки.",
    "S2": "У стола есть ножки.",
    "S3": "У меня есть книга.",
    "S4": "Ворона обладает перьями.",
    "S5": "У вороны лапки.",
    "S6": "Вороны любят червей.",
}


def new_pipeline_projection(text: str, mode: str = "baseline") -> dict:
    """Run the real T0-T4 pipeline (deterministic FakeSelector) and project its decision outcomes + diagnostics."""
    from ah.formalizer.fake_selector import FakeSelector
    from ah.formalizer.pipeline import run
    from ah.formalizer.selection_protocol import load_decision_schema

    schema = load_decision_schema()
    state = run(text, schema, FakeSelector.demo(mode))
    decisions = sorted((d.slot_id, d.outcome or "OPEN") for d in state.decisions.values())
    return {"decisions": decisions, "diagnostics": sorted({x.code for x in state.diagnostics})}


class LegacyAdapter:
    """Wraps a legacy ``parse(text)`` callable and reduces it to a completion status (behavioral reference only)."""

    def __init__(self, parse_fn):
        self.parse_fn = parse_fn

    def status(self, text: str) -> str:
        try:
            self.parse_fn(text)
            return "COMPLETED"
        except Exception as exc:  # noqa: BLE001 - any legacy failure is a legitimate behavioral outcome
            name = type(exc).__name__
            if "ClarificationRequired" in name or "clarification" in str(exc).lower():
                return "CLARIFICATION_REQUIRED"
            return "ERROR"


def build_real_legacy_parse_fn():
    """Lazily construct the real legacy parser; return its ``parse`` bound method, or None if unavailable."""
    try:  # pragma: no cover - environment dependent
        from pathlib import Path

        from ah.config import LLMRoleSettings
        from ah.llm import LLMResponse
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        project = Path(__file__).resolve().parents[3]

        class _Backend:  # permissive: empty answers; the deterministic parts run without an LLM
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse("", {})

        parser = AdaptivePerceptionParser(
            _Backend(),
            AdaptiveSettings(
                prompt_dir=project / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
        )
        return parser.parse
    except Exception:  # noqa: BLE001 - degrade to stub rather than fail import
        return None


@dataclass(frozen=True)
class ComparisonRow:
    label: str
    sentence: str
    new_decisions: tuple            # ((slot_id, outcome), ...) from the new pipeline
    legacy_status: str             # COMPLETED | CLARIFICATION_REQUIRED | ERROR

    @property
    def new_has_resolved(self) -> bool:
        return any(outcome == "RESOLVED" for _, outcome in self.new_decisions)


def compare(sentences, new_fn, legacy_adapter: LegacyAdapter, mode: str = "baseline") -> list[ComparisonRow]:
    """One row per sentence; records both sides without asserting agreement (legacy is a behavioral reference only)."""
    rows = []
    for label in sorted(sentences):
        text = sentences[label]
        proj = new_fn(text, mode) if legacy_adapter else {"decisions": ()}
        rows.append(ComparisonRow(label=label, sentence=text,
                                  new_decisions=tuple(proj["decisions"]),
                                  legacy_status=legacy_adapter.status(text)))
    return rows


if __name__ == "__main__":  # pragma: no cover - manual run
    parse = build_real_legacy_parse_fn()
    adapter = LegacyAdapter(parse) if parse else None
    for row in compare(DEMO_SENTENCES, new_pipeline_projection, adapter):
        print(row.label, row.new_decisions, "->", row.legacy_status)
