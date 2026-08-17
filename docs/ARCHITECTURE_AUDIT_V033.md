# Architecture audit v0.33

Scope: current runtime after lexical recall v0.32, checked against `docs/reference/Архитектура_v3.md`.

## Aligned and retained

- AH Core remains the only canonical write owner; Perception/Agent do not write canonical records directly.
- External user input follows Text Sensory -> Perception -> deterministic Integration.
- Canonical `S` ambiguity remains `wordform -> set[S]`; post-semantic canonical S receives the strong resolved-symbol seed.
- Ignition tick is synchronous snapshot/commit; a causal packet crosses at most one new structural edge per tick.
- `x` is retained activation; `output` is only newly acquired pre-clamp excitation, so a floating floor is not re-emitted forever.
- Decay remains epoch-local with `x_floor = alpha * x_start`; new user prompt rebases active epochs, strong non-background reactivation may rebase one node.
- Pacemaker-only waves retain provenance and do not train `h`/lifecycle or rebase the floating floor.
- Lexical recall remains feed-forward `S -> T -> N -> actants`; scoped propositions are not promoted as standalone facts, and `FALSE(N)` is the current recall representative of a refuted N.
- Workspace is exactly `x > t`; GUI Workspace/all-nodes views are read-only diagnostics and do not rerank cognition.
- Inference remains deterministic/rule-driven and AgentContext remains current input + Workspace projection + semantic inference results.
- Agent model calls remain stateless (`history_messages=0`); no hidden conversation buffer is introduced.
- H self-utterance is always recorded as an exact-text canonical event. Optional second semantic self-parse is H-only and remains OFF by default for MVP latency.

## v0.33 runtime decisions

- Background IgnitionClock default cadence is **1 scheduled tick per second** (`tick_interval_seconds=1.0`, `tick_rate=1 Hz`). Cognitive time is still actual tick count; the clock never performs catch-up storms.
- `nu=1.0` therefore remains one pacemaker pulse per wall-clock second; at 1 Hz this normally means one background pulse on each scheduled clock tick.
- The LLM diagnostics panel exposes the exact rendered checkpoint chat-template for the most recent Agent-role request, plus input token count. This is runtime-only and never enters AH/H or a future prompt.

## Deliberate MVP boundary

The full second semantic Perception pass over the agent's own response remains optional (`parse_agent_response_to_h=false` by default). This is now explicitly documented rather than being an implementation/specification mismatch. The exact utterance still exists in H and FOLLOW history.

No additional blocking mismatch was found in Ignition -> Workspace -> Inference -> Projection -> Agent flow during this audit.
