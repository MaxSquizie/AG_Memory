# v0.12.59 — M2 inference attention on arbitrary AH

## Corrected contract

A cold Workspace is an acceptance purity control only. It demonstrates that an M2
answer was not already available as active context before the query. Runtime
inference has no cold-Workspace precondition and must remain correct when memory is
already warm or noisy.

For `CAUSE`, `FOLLOW`, and `IS-A`, proof traversal stays rule-driven while runtime
attention is coordinated through Ignition. Before expanding a proposition the
inference coordinator applies a `QUERY_RECALL` seed and executes one synchronous
Ignition tick. Search stops on the logical Goal, not on an excitation threshold.

## Scale and locality

The operator acceptance suite snapshots the current AH when available, never mutates
live memory, pads its sandbox to at least 150,000 canonical UIDs, and then runs cold,
warm, cross-chain, and heavily branched proofs on the same dirty AH.

Ignition now advances the affected active/incoming frontier rather than deep-copying
the complete runtime-state every tick. Inference likewise uses canonical indexes and
local adjacency rather than whole-AH scans for its supported rule families.

## Acceptance

The M2 suite contains 32 cases and checks:

- `PROVED` + `GOAL_SATISFIED`;
- exact requested logical depth;
- exact canonical UID proof trace;
- exact inference-attention proposition sequence;
- real excitation changes on the used path;
- no proof/attention traversal beyond Goal;
- no leakage into independent or distractor branches;
- correctness with both cold and already warm Workspace state.

Launchers:

```text
GUI: M2: inference attention
CLI: ah-agent --config config/default.toml m2-acceptance
```
