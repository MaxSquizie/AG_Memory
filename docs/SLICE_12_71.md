# v0.12.71 — Unified responsive MONITOR workspace

The Team 3 visual/UX layer remains the GUI standard. The separate INSPECT and RUNTIME workspace presets are replaced by one MONITOR preset because their information is meant to be observed concurrently.

## MONITOR layout

Live monitoring surfaces remain visible together:

- Node/Link Inspector;
- Workspace;
- Runtime / Trace;
- LLM diagnostics/status;
- Dialog.

Auxiliary browsing/configuration surfaces (`All Nodes`, `Config`) remain available in the same workspace. On ordinary displays they are tabified with Workspace/LLM to protect Canvas area; on wide displays they expand into separate panes.

The layout reflows only when the window crosses responsive breakpoints (`compact`, `normal`, `wide`), so manual splitter adjustments are not continuously destroyed during normal resizing.

## Compact runtime controls

Ignition tuning and corpus/memory import are now separate local tabs (`Параметры`, `Импорт`). Import controls no longer consume vertical space while the operator is monitoring runtime state.

No AH, Perception, Integration, Inference, Projection or Persistence semantics are changed.
