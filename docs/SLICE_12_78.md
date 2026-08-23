# v0.12.78 — LM Studio server backend

## Goal

Connect the existing AH Perception + Agent LLM boundary to a model hosted by LM Studio without touching canonical AH semantics, inference, ignition, or deterministic integration.

## Transport boundary

```text
AH Perception / Agent
        ↓ existing LLMBackend.generate contract
LMStudioBackend
        ↓
LM Studio local server
  GET  /api/v1/models
  POST /v1/chat/completions  (stream=false)
        ↓
one externally managed loaded model
```

The backend is deliberately stateless. Every call contains only the role-specific system prompt and the current mechanical request. It does not preserve LM Studio chat history or KV state between AH calls.

## Model selection

`llm.lmstudio_model` accepts the exact LM Studio model key. If it is empty or `auto`:

1. exactly one loaded LLM → use it;
2. no loaded LLM and exactly one available LLM → use that key;
3. multiple loaded/available candidates → fail closed and print the exact keys.

LM Studio owns loading, GPU offload, quantization and unload policy. AH `start/stop` only attaches/detaches from the external server.

## Protocol safety

- `history_messages` remains hard-fixed to `0`;
- `/v1/chat/completions` always uses `stream=false`;
- Perception/semantic roles remain ordinary deterministic-generation probes, not continuation-score voters;
- `choice_outputs` is rejected for this backend rather than silently changing semantic decision mechanics;
- Qwen-style `<think>...</think>` content is stripped from machine-protocol roles (and globally when `strip_thinking=true`).

## Files

- `src/ah/llm/lmstudio_client.py`
- `src/ah/llm/lmstudio_backend.py`
- `config/lmstudio.toml`
- `run_gui_lmstudio.bat`
- `tests/test_lmstudio_backend_v078.py`

Factory/config/GUI hot-reload boundaries were extended with the new backend. LM Studio endpoint/model/token changes are classified as `RESTART_LLM`, not runtime rebuilds.

## Verification

Full repository suite after the change:

```text
484 passed, 22 subtests passed
```
