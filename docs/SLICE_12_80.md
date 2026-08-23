# v0.12.80 — LM Studio Qwen3.8 runtime-key fix

- Pin `llm.lmstudio_model` to the exact key returned by this LM Studio server: `qwen3.8-27b-nvfp4-q5k-no-mtp`.
- Keep `/v1/models` discovery and `/v1/chat/completions` inference.
- Add a deterministic, uniqueness-checked compatibility alias for GGUF display/repository names whose runtime key omits the trailing `-GGUF` / `.gguf` packaging suffix.
- No changes to AH Core, integration, ignition, inference, or projection semantics.
