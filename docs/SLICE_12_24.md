# Slice v0.12.24 — one-shot TemplateCandidate

## Motivation

The real v0.12.23 acceptance showed that counterbalancing did not solve the core issue. Weak Qwen answered semantic YES consistently for `template_more_core`, then the forced family/role choices made it invent omitted roles even for predicates such as `спать` and `читать`. The hard limit prevented an infinite walk but converted most inputs into explicit parse errors.

## Architecture alignment

The normative flow is `unknown predicate -> LLM TemplateCandidate -> deterministic validation -> canonical T`. v0.12.24 implements that literally as one finite Perception request rather than a recursive dialogue.

## Protocol

For each unknown predicate:

1. Deterministically collect roles filled by the current frame.
2. Make exactly one `perception_template_schema` request.
3. The model returns `NONE` or a comma-separated subset of canonical omitted role option numbers.
4. Echoes of already-filled roles are ignored conservatively; they cannot widen the schema.
5. Construct runtime-only `TemplateCandidate(observed + omitted)`.
6. Integration validates and, if valid, registers canonical `T`.

No recursive `more_core/family/role` probing exists. If the model fails to infer a latent optional role, the resulting `T` may be narrow and a later occurrence can still fail explicitly because T valency evolution remains `[DEFER]`. That limitation is preferable to runaway calls or garbage templates.
