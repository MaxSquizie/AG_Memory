# v0.12.60 — Proof Explorer and transparent M2

## Runtime boundary

Proof history is diagnostics only. `ProofSnapshot` freezes the exact `InferenceOutcome` UID trace and its deterministic semantic projection. It is never written to C/P/H and never becomes a second proof engine.

## Operator UI

The modeless `Логический вывод — Proof Explorer` receives proofs from three paths:

- normal GUI dialogue (`LIVE`);
- general acceptance suite (`ACCEPTANCE`);
- M2 inference-attention suite (`M2`).

For the selected chain it shows a dedicated graph canvas, human-readable step-by-step logic, exact UID trace, and per-check M2 diagnostics. Live canonical proof UIDs can additionally be highlighted on the main AH canvas. M2 fixture UIDs remain sandbox-only and are never copied into live AH merely for visualization.

## M2 transparency

Every M2 case stores:

- Goal semantics and conclusion semantics;
- exact proposition/link proof graph;
- rule label and explanation for every logical step;
- exact UID trace;
- exact attention sequence;
- individual PASS/FAIL checks for status, stop condition, logical depth, path coldness, Ignition excitation, tail-after-Goal, and foreign branch isolation.

`result.json` carries the complete frozen proof objects and `report.txt` repeats the semantic steps and checks in operator-readable text.
