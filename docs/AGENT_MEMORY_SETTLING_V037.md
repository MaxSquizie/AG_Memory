# v0.37 — Agent memory settling and semantic AgentContext

## Confirmed timing bug

Before v0.37 the normal turn performed only one `ticks_after_input` after Integration.
With synchronous one-edge-per-tick lexical recall, a resolved prompt symbol followed:

```text
seed S
 tick 1: S -> next(T)
 Workspace snapshot / AgentContext immediately here
```

Therefore the proposition `N` related to that lexical item could still be pending when
the Agent LLM started generating a response.

## Fix

Default `orchestrator.ticks_after_input` is now `3`:

```text
tick 1: S receives prompt seed, schedules T
tick 2: T receives packet, schedules N
tick 3: N receives packet and may cross Workspace threshold
THEN: freeze Workspace -> inference -> AgentContext -> Agent LLM
```

These immediate turn-local settling ticks call `IgnitionEngine.tick(include_pacemaker=False)`.
They preserve ordinary synchronous activation/decay/lifecycle semantics but do not inject
a fresh ν pulse on every immediate settling hop. Scheduled background ticks still use the
normal 1 Hz clock and include pacemaker activity.

## Agent-facing memory format

Workspace remains the exact cognitive set `x > t`. It may contain S/T/N/M/G/K.
AgentContext no longer serializes that set as an internal graph dump.

Model-visible ACTIVE MEMORY now:

- drops standalone S/T/L scaffolding;
- never exposes structural UIDs;
- suppresses SELF/USER rows and entity dependencies already represented by a proposition;
- recovers the exact source USER utterance for active canonical content when available;
- presents old active H events explicitly as previous utterances;
- removes the current H USER event and same-turn semantic content because CURRENT INPUT already contains that text;
- deduplicates repeated semantic lines without ranking/top-k selection.

The exact source Workspace remains visible only in `Memory INPUT -> DEBUG EXPLANATION`.
The panel now reports projection tick, turn-local settle tick count, source Workspace root
count and model-visible memory block count separately.
