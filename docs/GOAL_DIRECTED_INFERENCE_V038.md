# v0.38 — Goal-directed inference / M2

## What changed

- Added explicit runtime `GoalSpec` and `InferenceQuery`.
- Agent query builder now emits `InferenceQuery(GoalSpec(...))` instead of a bare goal.
- Every inference outcome records the exact goal and `logical_depth` for diagnostics.
- Added `DEPTH_EXHAUSTED` so a resource-limited UNKNOWN is not confused with true search exhaustion.
- `IS-A` and `FOLLOW` stop immediately when the requested target is reached, even if the graph continues further.
- Added bounded multi-step CAUSE modus ponens from **explicit query premises**. Intermediate consequents are runtime proof states, not automatically materialized facts or free premises.
- Legacy bare `CauseEntailmentGoal` keeps the previous one-step compatibility behavior; multi-step CAUSE requires explicit `InferenceQuery.premise_refs`.

## M2 acceptance

The regression chain intentionally continues beyond the goal:

```text
A -> B -> C -> D -> E -> F -> G -> H -> I
                              ^ Goal
```

For `max_depth=6`:

```text
status=PROVED
stop=GOAL_SATISFIED
logical_depth=6
trace ends at G
H and I are absent from trace
```

For `max_depth=5`:

```text
status=UNKNOWN
stop=DEPTH_EXHAUSTED
trace ends at F
```

The same six-hop acceptance is covered for multi-step `CAUSE/MP` from explicit premise `A`.

## Architecture boundary

`GoalSpec`, `InferenceQuery`, frontier/visited/bindings and intermediate derived propositions are runtime-only. They are not new AH semantic types and are not written to H. Only a final proved semantic conclusion may pass through the existing inference materialization boundary.
