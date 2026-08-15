# Slice 12.14 — Acceptance observability

- LLM panel diagnostics now use a dedicated lightweight 300 ms GUI timer.
- Acceptance runs may suspend heavy GraphInspector/canvas/status polling without hiding LLM stage/request/log diagnostics.
- LLM panel reports resident process RAM separately for the GUI process and the local LLM worker.
- RAM sampling is diagnostic-only and never affects AH, inference, ignition, perception, or generation.
