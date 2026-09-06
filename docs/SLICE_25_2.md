# Slice v0.25.2 — LM Studio reasoning isolation for bounded probes

## Trigger

User diagnostic bundles showed:

- M1 adversarial: 0 runtime OK / 36 runtime errors;
- broad acceptance: 14 runtime OK / 186 runtime errors.

The repeated error was an empty assistant `content` with `finish_reason=length` while all 8–10 generated tokens were reported as reasoning tokens. Cases that needed no LLM probe could still run, which localized the fault to the semantic-probe transport.

## Root cause

The project sent `enable_thinking=false` and `chat_template_kwargs.enable_thinking=false` to `/v1/chat/completions`, but these are not part of the documented LM Studio OpenAI-compatible Chat Completions payload. A loaded reasoning-capable model/runtime can therefore ignore them and use its tiny protocol budget for hidden reasoning.

The parser correctly rejected empty visible output; consuming hidden reasoning as an answer would violate the bounded semantic-probe contract.

## Change

For roles beginning with `perception_` or `semantic_`, when thinking is disabled, the LM Studio backend now calls native `POST /api/v1/chat` with:

- `reasoning = "off"`;
- `store = false`;
- `stream = false`;
- the same bounded `max_output_tokens`;
- the same deterministic sampling settings.

Generic/agent generation stays on `/v1/chat/completions`, minimizing the change surface.

## Architectural semantics

This is transport hardening, not a semantic fallback. The LLM still makes exactly the same bounded decision, hidden reasoning is never interpreted as a protocol label, and no additional model call or repair path is introduced.
