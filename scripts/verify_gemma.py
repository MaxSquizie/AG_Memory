# -*- coding: utf-8 -*-
"""Live end-to-end verification of the Phase 1 pipeline on a real local model (Gemma via LM Studio).

Runs S1-S6 (baseline + augmented) plus arbitrary examples through the SAME ``run()`` path as the scripted dry run,
but with :class:`~ah.formalizer.lmstudio_selector.LMStudioSelector` (default model ``gemma-3n-e4b-it``) as the bounded
selector. Prints per-sentence outcomes and a §2.3 coverage report.

Usage:  PYTHONPATH=src python scripts/verify_gemma.py [model]
        GEMMA_MODEL=gemma-3n-e4b-it PYTHONPATH=src python scripts/verify_gemma.py

Skips cleanly (exit 0) if the LM Studio server or the model is not reachable, so it never breaks an offline run.
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

    model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GEMMA_MODEL", "gemma-3n-e4b-it")
    base_url = os.environ.get("GEMMA_BASE_URL", "http://127.0.0.1:1234")
    timeout_seconds = float(os.environ.get("GEMMA_TIMEOUT", "240"))  # high default for real inference; override to fail fast offline
    sel = LMStudioSelector(model=model, base_url=base_url, temperature=0.0,
                          max_tokens=96, timeout_seconds=timeout_seconds)

    try:
        models = sel.list_models()
    except LMStudioSelectorError as exc:
        print(f"[skip] LM Studio unreachable ({exc}); nothing to verify live.")
        return 0
    if model not in models:
        print(f"[skip] model {model!r} not loaded. Available: {models}")
        return 0

    schema = load_decision_schema()

    S1, S2, S3, S4, S5, S6 = (
        "У вороны есть лапки.", "У стола есть ножки.", "У меня есть книга.",
        "Ворона обладает перьями.", "У вороны лапки.", "Вороны любят червей.",
    )
    F1 = ("Лапки — часть тела этой вороны.",)
    F3 = ("Перья — часть тела этой вороны.",)

    # (label, text, context_facts). Baseline passes NO contextual statements; augmented passes the declared one.
    cases = [
        ("S1 base", S1, ()),
        ("S1 aug ", S1, F1),
        ("S3 base", S3, ()),
        ("S4 aug ", S4, F3),
        ("ARB locative  ", "Ворона сидит на ветке.", ()),
        ("ARB like      ", "Вороны любят червей.", ()),
        ("ARB out-of-set", "Ворона летает высоко над городом.", ()),
    ]

    attempts = int(os.environ.get("GEMMA_ATTEMPTS", "2"))  # bounded retry-once on protocol/provider failure
    states = []
    print(f"model={model}  base_url={sel.base_url}  attempts_per_slot={attempts}\n")
    for label, text, facts in cases:
        st = run(text, schema, sel, context_facts=facts, attempts_per_slot=attempts)
        states.append(st)
        dec = _predicate_dec(st)
        codes = sorted({d.code for d in st.diagnostics})
        if dec is None:
            print(f"{label} | no predicate decision | diag={codes}")
            continue
        sel_txt = ",".join(dec.selected) or "-"
        print(f"{label} | {text!r}\n"
              f"          outcome={(dec.outcome or '-'):<20} lifecycle={(dec.lifecycle or '-'):<11} selected=[{sel_txt}]")
        if codes:
            print(f"          diag={codes}")

    rep = summarize(states)
    print("\n=== §2.3 coverage report ===")
    print(f"sentences={rep.sentences}  answered={rep.answered_sentences}  "
          f"proven_outcomes={rep.proven_outcomes}  ratio={rep.coverage_ratio:.2f}")
    print(f"honest_gaps={dict(rep.honest_gaps) or '{}'}   provider_failures={dict(rep.provider_failures) or '{}'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
