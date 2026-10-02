# v0.12.62 — ollama_uv integration

This slice ports the useful independent mechanisms from `ollama_uv` onto the current v0.12.61 codebase without replacing the newer inference/M2/CanvasBrowser/Proof Explorer layers.

## Included

- backend-neutral LLM factory with `builtin_process` and `ollama` backends;
- stateless Ollama HTTP client/backend with fixed-choice diagnostics;
- runtime-only session JSONL/text logging;
- structured cold corpus loading from JSON and the MVP `.ahm/.prj` subset;
- strict raw-text and dialogue import into the same Perception → TemplateCompletion → Integration path as live turns;
- explicit `best-effort` mode only when requested;
- cold/hot memory snapshot import;
- runtime memory reset preserving only SELF/USER identity bootstrap;
- CLI import/reset commands;
- GUI perception timeline, corpus/text/memory import controls, pacemaker pulse and Workspace threshold controls;
- `AH_CONFIG`, `run_gui_ollama.bat`, and venv-aware launchers.

## Architectural boundaries

- imports never write diagnostics into H;
- structured cold loading writes canonical AH only and does not seed Ignition;
- LLM backend remains stateless and does not own cognitive memory;
- raw semantic corpus build reuses the exact public TemplateCompletion service used by live turns;
- `x`/Workspace policy is not used as truth;
- architectural pacemaker frequency `nu` remains distinct from pulse amplitude.

## Validation

- full suite: 414 passed + 22 subtests;
- M2 operator run: 40/40, 153502 UID sandbox.
