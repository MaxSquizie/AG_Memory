> Historical note: `failure_policy=empty` described below was removed in slice 12.11. Current perception fails explicitly and does not return an empty successful parse.

# Slice 9.3 — robust perception wire protocol and H-boundary guards

This slice addresses real failures observed with the local Qwen parser role.

## Perception protocol

The default LLM wire protocol is now `line_v1`, not JSON:

```text
A|ID|surface|lemma|0/1|ROLE=value...
Q|EXISTS/FILL_ROLE|surface|lemma|ROLE_OR_-|ROLE=value...
C|surface|lemma|ROLE=value...
NONE
```

The canonical runtime contract is still `PerceptionResult`; `line_v1` is only the
LLM boundary format. Nested assertions use `@A2` references. The parser remains
stateless and cannot emit canonical UIDs.

The protocol intentionally contains no semantic example with fake entities. This
prevents weak models from copying prompt placeholders into AH memory.

## Grounding

For `line_v1`, predicate surface forms and actant values are source-grounded before
integration. Actant values must be copied from the current source text, except the
small pro-drop/deictic allowance `я/ты/мы`. An implicit predicate is represented by
`surface=_` and its lemma.

Malformed or ungrounded output is repaired once. With the default
`failure_policy="empty"`, a still-invalid parse becomes an empty `PerceptionResult`
with a `PARSER_FAILURE` diagnostic. No C/P semantic writes occur, but the external
turn is still recorded as experienced communication in H and the agent may respond.

## Parser generation

The parser role uses no repetition penalty (`1.0`) and no n-gram blocking. This is
important for structured output, where repeated separators and role tokens are
normal. JSON decoding remains supported for backwards compatibility and tests.

## Agent H boundary

Agent output is sanitized before response experience integration. If the model
appends internal sections such as `CURRENT INPUT`, `ACTIVE MEMORY` or
`INFERENCE RESULTS`, only the actual utterance before the echoed context is kept.
If output consists only of internal context, one repair call is attempted; a still
invalid result is rejected and is not committed to H.

Raw model responses remain available in the LLM diagnostics tabs.
