# -*- coding: utf-8 -*-
"""Phase 1 real-model validation (V4 rev7b / etalon PILOT_DEMO_REFERENCES_V1).

Runs the six demo sentences S1-S6 through the full T0-T4 pipeline with a LIVE local
model (gemma-3n-e4b-it via LM Studio) attached to the formalizer's bounded-selection
seam (:class:`ah.formalizer.real_backend.RealBackendSelector`), and classifies each
sentence against the frozen etalon target reading:

  C1 = correctly formalized (resolved to the target value, or honest complete handling)
  C2 = honestly incomplete/partial (unresolved {HAVE,HAS_PART}, NO_CANDIDATE, INSUFFICIENT_CONTEXT)
  C3 = mechanism failure (a WRONG meaning accepted as the resolved predicate value)

Two runs per sentence:
  baseline  - no contextual statement in the input context
  augmented - the etalon's declared contextual statement (F1/F2/F3) passed verbatim

A fresh RealBackendSelector is built per run so every measurement is a live model call
(no replay-cache masking). Protocol errors and transport outages are reported as honest
diagnostics, never silently turned into an accepted value.

Usage:  PYTHONPATH=src python scripts/p1_real_run.py [config_path]
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "src")

from ah.config import load_config                       # noqa: E402
from ah.llm.factory import build_llm_backend            # noqa: E402
from ah.formalizer.real_backend import RealBackendSelector  # noqa: E402
from ah.formalizer.pipeline import run as pipeline_run   # noqa: E402
from ah.formalizer.selection_protocol import load_decision_schema  # noqa: E402

# sid -> (sentence, target value id, contextual statement tuple for the augmented run)
SENTENCES = {
    "S1": ("У вороны есть лапки.",   "V2", ("Лапки — часть тела этой вороны.",)),
    "S2": ("У стола есть ножки.",    "V2", ("Ножки — часть этого стола.",)),
    "S3": ("У меня есть книга.",     "V1", ()),
    "S4": ("Ворона обладает перьями.","V2", ("Перья — часть тела этой вороны.",)),
    "S5": ("У вороны лапки.",        "V2", ("Лапки — часть тела этой вороны.",)),
    "S6": ("Вороны любят червей.",   "V4", ()),
}

VALUE_NAMES = {"V1": "HAVE", "V2": "HAS_PART", "V3": "LOCATIVE", "V4": "LIKE"}


def _names(ids) -> str:
    return "/".join(VALUE_NAMES.get(v, v) for v in ids) if ids else "(none)"


def classify(outcome, selected, target) -> str:
    """Map a T4 outcome + selection to the etalon C-class against the target reading."""
    if outcome == "RESOLVED" and len(selected) == 1:
        return "C1" if selected[0] == target else "C3"
    # AMBIGUOUS / UNRESOLVED / NO_CANDIDATE / INSUFFICIENT_CONTEXT -> honest incompleteness.
    # A multi-value RESOLVED is not a single accepted meaning, so it is C2 (partial), not C3.
    return "C2"


def run_one(backend, schema, text, facts):
    sel = RealBackendSelector(backend)  # fresh per run -> live call, no replay masking
    t0 = time.time()
    st = pipeline_run(text, schema, sel, context_facts=facts)
    dt = time.time() - t0
    preds = [d for d in st.decisions.values() if d.slot_id == "predicate_value"]
    diags = sorted({x.code for x in st.diagnostics})
    return st, preds, diags, dt


_OUT: list[str] = []


def _emit(line: str = "") -> None:
    print(line)
    _OUT.append(line)


def main(config_path: str) -> int:
    cfg = load_config(config_path)
    backend = build_llm_backend(cfg)
    backend.start()
    schema = load_decision_schema()
    _emit(f"model={backend._active_model!r}  url={cfg.llm.lmstudio_base_url}")
    _emit()

    summary = {}
    for mode in ("baseline", "augmented"):
        print(f"=== {mode.upper()} ===")
        for sid, (text, target, facts) in SENTENCES.items():
            if mode == "baseline":
                use_facts = ()
            else:
                use_facts = facts  # only S1/S2/S4/S5 carry a statement; S3/S6 stay bare
            try:
                st, preds, diags, dt = run_one(backend, schema, text, use_facts)
            except Exception as exc:  # keep the report going even on an unexpected crash
                print(f"{sid} {text!r}\n   !! driver error: {exc}")
                summary[(mode, sid)] = "ERR"
                continue
            if not preds:
                _emit(f"{sid} {text!r}\n   no predicate decision  diags={diags}  ({dt:.1f}s)")
                summary[(mode, sid)] = "C2"
                continue
            d = preds[0]
            c = classify(d.outcome, d.selected, target)
            summary[(mode, sid)] = c
            note = f"  fact={use_facts[0]!r}" if (mode == "augmented" and use_facts) else ""
            _emit(
                f"{sid} {text!r}\n"
                f"   selected={_names(d.selected)}  outcome={d.outcome}  -> {c}"
                f"   (target={VALUE_NAMES[target]}, llm_calls={st.budget.llm_calls}, "
                f"diags={diags or '-'}){note}  ({dt:.1f}s)"
            )
        _emit()

    backend.stop()

    # Set-level rollup: mechanism passes iff there is no C3 anywhere.
    c3 = [k for k, v in summary.items() if v == "C3"]
    _emit("=== ROLLUP ===")
    for mode in ("baseline", "augmented"):
        row = {sid: summary.get((mode, sid), "?") for sid in SENTENCES}
        _emit(f"{mode:9s}: " + "  ".join(f"{k}={v}" for k, v in row.items()))
    _emit()
    _emit(f"mechanism passed (no C3): {'YES' if not c3 else 'NO -> ' + str(c3)}")

    # Dump the full report to a UTF-8 file so Cyrillic survives any console codepage.
    with open("p1_real_run_report.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(_OUT) + "\n")
    return 0


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/p1_gemma_e4b.toml")
