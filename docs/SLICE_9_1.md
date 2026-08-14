# Slice 9.1 — LLM diagnostics and GenerationConfig cleanup

This cumulative patch adds runtime-only observability for the shared local LLM and removes the Transformers 5.x mixed-generation-arguments deprecation.

## GUI LLM diagnostics

The LLM dock now contains:

- `Perception prompt`
- `Agent prompt`
- `Parser RAW` — exact text returned by the perception role, including repair attempts and parse errors
- `Parser decoded` — deterministic `PerceptionResult` after compact-protocol decoding
- `Agent RAW` — exact latest text returned by the agent role
- `Requests` — recent role calls and responses
- `Worker log` — model load/status log

Diagnostics are runtime-only and are never written to AH/H or projected into AgentContext.

## Transformers generation

`ah.llm.worker.generate()` now builds a request-local copy of `model.generation_config`, applies all role-specific generation settings to that object, and calls `model.generate(..., generation_config=gc)` without also passing generation-related keyword arguments. This avoids the Transformers 5.x deprecation warning and prevents parser/agent settings from mutating the model-global generation config.

Greedy perception calls explicitly clear inherited sampling controls from the checkpoint generation config.
