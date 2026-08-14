# Slice 10.2 — robust micro-probe prompting

This patch keeps the `adaptive_v1` architecture unchanged and fixes two runtime issues observed with the local Qwen checkpoint.

## Probe prompting

Each probe still makes exactly one semantic decision. The model now sees the stage instruction at the **end of the user turn** under `TASK:`. A tiny generic system guard remains, but correctness no longer depends on the checkpoint strongly obeying the system role.

`act_type` receives only `TEXT`; token numbering is not shown because it is not needed for speech-act classification. Span probes receive `TOKENS` only when they need to return token indices.

## Chat-template tokenization

The worker now calls `tokenizer.apply_chat_template(..., tokenize=True, return_dict=True, return_tensors="pt")` directly. It no longer renders a templated string and then tokenizes it with tokenizer defaults. The compatibility fallback explicitly uses `add_special_tokens=False`, preventing duplicated BOS/EOS/chat-control tokens.

No AH contracts changed. LLM output remains a non-canonical perception cue; Python validates every scalar decision and alone constructs `PerceptionResult`.
