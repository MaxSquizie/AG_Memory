# Slice 12.26 — robust one-shot TemplateCandidate protocol

The real v0.12.25 acceptance run produced 0/40 successful cases because the weak local model consistently emitted a correct-looking first decision and then continued with prose. The strict whole-response parser rejected all such outputs.

This slice keeps the architecture-v3 boundary: one LLM TemplateCandidate request followed by deterministic validation. It changes the request from "which omitted roles?" to the complete reusable valency schema of the shown predicate sense, avoiding the previous dominant `NONE` answer and format-example echo.

The first non-empty response line is now the sole protocol frame and must contain `SCHEMA:` followed only by canonical role names. Later text is non-protocol chatter and is ignored. Filled roles from the concrete frame remain a deterministic lower bound. Legacy `NONE.` is accepted only as conservative abstention; it cannot remove observed roles or widen `T`.

No valency evolution is introduced. Canonical `T` registration remains deterministic Integration work.
