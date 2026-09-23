# -*- coding: utf-8 -*-
"""FakeSelector — a deterministic stand-in for the LLM (Phase 1 dry run).

It implements exactly the interface the real backend will use:
    select(prompt) -> raw JSON string   (or raises ProviderUnavailableError)

The selector sees ONLY the prompt. rev8 anti-forgery contract: an augmented script
may rely on a contextual statement only if that statement is DECLARED in the prompt
("Declared contextual statements" block). If it is not present, the selector falls
back to its baseline behavior — it cannot cite what it was never shown. This makes
the dry run honest: the augmented result exists because of the declared input, and a
forged context (statement absent from the prompt) degrades to the baseline outcome.

The scripts are per-slot fixtures for the demo sentences; they are NOT rules about
the language (D3 check: no per-example structural knowledge is added between runs).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


class ProviderUnavailableError(RuntimeError):
    """The provider could not be reached — a failed call, counted in the budget."""


@dataclass(frozen=True)
class _Script:
    response: str  # raw JSON to return when all ``requires`` are declared in the prompt
    requires: tuple[str, ...] = ()  # contextual statements that must appear verbatim


def _json(outcome: str, selected: list[str], note: str) -> str:
    return json.dumps({"outcome": outcome, "selected": selected, "note": note}, ensure_ascii=False)


class FakeSelector:
    """scripts maps (slot_id, context_span) to a plain response (str/tuple) or a
    _Script. ``fallback`` is consulted when a script's required statements are absent."""

    def __init__(self, scripts: dict | None = None, fallback: dict | None = None):
        self.scripts: dict = scripts or {}
        self._fallback: dict = fallback or {}

    def select(self, prompt: str) -> str:
        for (slot_id, span), script in self.scripts.items():
            if f"Context span: {span}" not in prompt:
                continue
            if isinstance(script, _Script):
                missing = [s for s in script.requires if f"- {s}" not in prompt]
                if missing:  # the statement was never declared to it -> no reliance
                    alt = self._fallback.get((slot_id, span))
                    if alt is None:
                        return _json("NONE_FIT", [], "no admissible candidate without the undeclared context")
                    script = alt
                else:  # every required statement IS declared in the prompt -> augmented behavior
                    return script.response
            if isinstance(script, str):
                if script == "PROVIDER_UNAVAILABLE":
                    raise ProviderUnavailableError("fake provider down (fixture)")
                return script  # plain response: no context requirement
            outcome, text = script  # e.g. ("INVALID", "...") -> raw text verbatim
            return text
        # Unscripted sentence: honest refusal over the declared closed set.
        return _json("NONE_FIT", [], "no admissible candidate among the declared relations")

    @staticmethod
    def demo(mode: str) -> "FakeSelector":
        """Baseline / augmented scripts for the six demo sentences (etalon v1).

        Augmented entries REQUIRE their contextual statement to be declared in the
        prompt; otherwise they fall back to the baseline behavior (anti-forgery)."""
        S1 = "У вороны есть лапки."
        S2 = "У стола есть ножки."
        S3 = "У меня есть книга."
        S4 = "Ворона обладает перьями."
        S5 = "У вороны лапки."
        S6 = "Вороны любят червей."
        baseline: dict = {
            ("predicate_value", S1): _json(
                "MULTIPLE_ADMISSIBLE", ["V1", "V2"],
                "no contextual statement declares the link; both readings admissible",
            ),
            ("predicate_value", S2): _json(
                "MULTIPLE_ADMISSIBLE", ["V1", "V2"],
                "no contextual statement declares the link; both readings admissible",
            ),
            ("predicate_value", S3): _json(
                "ONE_SELECTED", ["V1"],
                "textual ground: a book is not a body part; possession reading only",
            ),
            ("predicate_value", S4): _json(
                "MULTIPLE_ADMISSIBLE", ["V1", "V2"],
                "no contextual statement declares the link; both readings admissible",
            ),
            ("predicate_value", S5): _json(
                "MULTIPLE_ADMISSIBLE", ["V1", "V2"],
                "no contextual statement declares the link; both readings admissible",
            ),
            ("predicate_value", S6): _json(
                "ONE_SELECTED", ["V4"],
                "textual ground: 'любить' is an attitude verb -> LIKE",
            ),
        }
        if mode == "baseline":
            return FakeSelector(baseline)

        augmented: dict = {
            ("predicate_value", S1): _Script(
                _json("ONE_SELECTED", ["V2"], "relying on declared statement 'Лапки — часть тела этой вороны.' -> HAS_PART"),
                requires=("Лапки — часть тела этой вороны.",),
            ),
            ("predicate_value", S2): _Script(
                _json("ONE_SELECTED", ["V2"], "relying on declared statement 'Ножки — часть этого стола.' -> HAS_PART"),
                requires=("Ножки — часть этого стола.",),
            ),
            ("predicate_value", S3): baseline[("predicate_value", S3)],
            ("predicate_value", S4): _Script(
                _json("ONE_SELECTED", ["V2"], "relying on declared statement 'Перья — часть тела этой вороны.' -> HAS_PART"),
                requires=("Перья — часть тела этой вороны.",),
            ),
            ("predicate_value", S5): baseline[("predicate_value", S5)],
            ("predicate_value", S6): baseline[("predicate_value", S6)],
        }
        return FakeSelector(augmented, fallback=baseline)


if __name__ == "__main__":  # manual smoke check
    sel = FakeSelector.demo("augmented")
    from ah.formalizer.selection_protocol import build_selection_prompt, load_decision_schema

    schema = load_decision_schema()
    prompt = build_selection_prompt(
        slot_id="predicate_value", frame_id="C2", context_span=S1,
        mentions={"M0": "вороны (GEN after 'у')", "M1": "лапки (NOM pl)"},
        schema=schema, contextual_statements=("Лапки — часть тела этой вороны.",),
    )
    print(sel.select(prompt))
