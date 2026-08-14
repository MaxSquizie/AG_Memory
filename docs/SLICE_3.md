# Slice 3 — Config + Ignition + Local LLM boundary

## Пайплайн, который теперь соединён

```text
PerceptionResult
→ deterministic Integration
→ IntegrationCommit.activation_seeds
→ IgnitionEngine input buffer
→ synchronous tick
   → f(x,z)
   → outgoing impulse
   → activation/reactivation event
   → h
   → g (не на первом excitation tick)
→ Workspace = x > t
```

`RuntimeServices.integrate_external()` дополнительно начинает новый decay epoch перед интеграцией нового внешнего prompt.

## Central config

`config/default.toml` — единственная точка для путей и основных гиперпараметров.

Особенно:

```toml
[paths]
llm_model_dir = "C:/Models/Qwen"
```

Код загрузки модели не содержит hardcoded model path.

## LLM boundary

```text
AH runtime
→ LocalLLMProcessBackend
→ JSONL subprocess
→ ah.llm.worker
→ local transformers model
```

LLM пока не подключён к Perception parser: сначала зафиксирован безопасный runtime boundary и загрузка локальной модели.
