# -*- coding: utf-8 -*-
"""Side-by-side live comparison of local models on the Phase 1 case set (V7 §2.3).

Runs the SAME sentences through the SAME ``run()`` path for each model in a list and prints a
per-model outcome table plus a coverage summary, so C-metrics can be compared across backends.
Unreachable models are skipped cleanly (offline-safe), mirroring :mod:`verify_gemma`.

Usage:
    PYTHONPATH=src python scripts/compare_models.py [model1,model2,...]
    COMPARE_MODELS=gemma-3n-e4b-it,qwen2.5-32b-instruct GEMMA_ATTEMPTS=2 PYTHONPATH=src python scripts/compare_models.py

Env:
    COMPARE_MODELS  comma-separated model list (default: gemma-3n-e4b-it,qwen2.5-32b-instruct)
    GEMMA_ATTEMPTS  bounded attempts per slot, default 2 (retry-once on protocol/provider failure)
"""

from __future__ import annotations

import os
import sys


def _predicate_dec(state):
    for dec in state.decisions.values():
        if dec.slot_id == "predicate_value":
            return dec
    return None


def main() -> int:
    from ah.formalizer.lmstudio_selector import LMStudioSelector, LMStudioSelectorError
    from ah.formalizer.selection_protocol import load_decision_schema
    from ah.formalizer.pipeline import run
    from ah.formalizer.coverage import summarize

    models = [m.strip() for m in sys.argv[1].split(",") if m.strip()] if len(sys.argv) > 1 \
        else [m.strip() for m in os.environ.get("COMPARE_MODELS", "gemma-3n-e4b-it,qwen2.5-32b-instruct").split(",") if m.strip()]
    attempts = int(os.environ.get("GEMMA_ATTEMPTS", "2"))
    base_url = os.environ.get("GEMMA_BASE_URL", "http://127.0.0.1:1234")
    timeout_seconds = float(os.environ.get("GEMMA_TIMEOUT", "60"))  # short enough to fail fast offline

    S1, S2, S3, S4, S5, S6 = (
        "У вороны есть лапки.", "У стола есть ножки.", "У меня есть книга.",
        "Ворона обладает перьями.", "У вороны лапки.", "Вороны любят червей.",
    )
    F1 = ("Лапки — часть тела этой вороны.",)
    F2 = ("Ножки — часть этого стола.",)
    F3 = ("Перья — часть тела этой вороны.",)

    # (label, text, context_facts). Baseline passes NO contextual statements; augmented passes the declared one.
    cases = [
        ("S1 base", S1, ()),
        ("S1 aug ", S1, F1),
        ("S2 base", S2, ()),
        ("S2 aug ", S2, F2),
        ("S3 base", S3, ()),
        ("S4 base", S4, ()),
        ("S4 aug ", S4, F3),
        ("S5 base", S5, ()),
        ("S6 base", S6, ()),
    ]

    schema = load_decision_schema()
    results: dict[str, object] = {}  # model -> CoverageReport
    per_model_rows: dict[str, list[tuple]] = {}

    for model in models:
        sel = LMStudioSelector(model=model, base_url=base_url, temperature=0.0,
                              max_tokens=96, timeout_seconds=timeout_seconds)
        try:
            loaded = sel.list_models()
        except LMStudioSelectorError as exc:
            print(f"[skip] {model}: LM Studio unreachable ({exc})")
            continue
        if model not in loaded:
            print(f"[skip] {model}: not loaded. Available: {loaded}")
            continue

        states = []
        rows = []
        for label, text, facts in cases:
            st = run(text, schema, sel, context_facts=facts, attempts_per_slot=attempts)
            states.append(st)
            dec = _predicate_dec(st)
            if dec is None:
                rows.append((label, "no-decision", "-"))
                continue
            sel_txt = ",".join(dec.selected) or "-"
            rows.append((label, str(dec.outcome), sel_txt))

        rep = summarize(states)
        results[model] = rep
        per_model_rows[model] = rows
        print(f"\n=== {model}  (attempts_per_slot={attempts}) ===")
        for label, outcome, sel_txt in rows:
            print(f"  {label:<9} | {outcome:<14} selected=[{sel_txt}]")
        print(f"  coverage: answered={rep.answered_sentences}/{rep.sentences} "
              f"ratio={rep.coverage_ratio:.2f} honest_gaps={dict(rep.honest_gaps)} provider={dict(rep.provider_failures)}")

    if len(results) >= 2:
        print("\n=== side-by-side coverage ===")
        header = f"{'model':<28} {'answered':>9} {'ratio':>6} {'honest':>7} {'provider':>9}"
        print(header)
        for model, rep in results.items():
            print(f"{model:<28} {rep.answered_sentences}/{rep.sentences:>3} "
                  f"{rep.coverage_ratio:>6.2f} {rep.honest_gap_total:>7} {rep.provider_failure_total:>9}")

    if not results:
        print("\n[skip] no model reachable; nothing to compare live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
