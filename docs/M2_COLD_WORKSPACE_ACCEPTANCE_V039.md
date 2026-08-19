# v0.39 — M2 cold-Workspace goal-directed acceptance

## Why this slice exists

M2 measures explainable inference over `FOLLOW / IS-A / CAUSE` chains with depth `d=1..6`. The proof engine must demonstrate that it derives a result from canonical AH structure, not because the relevant chain was already present in Global Workspace.

## Added acceptance coverage

A new regression module `tests/test_m2_goal_directed_acceptance_v039.py` builds independent long chains and queries goals at different intermediate positions.

Coverage:

- `CAUSE`: real canonical `N` propositions, requested depths 1, 2, 3, 4, 5, 6;
- `FOLLOW`: real H-domain canonical `N` events, requested depths 1, 2, 3, 4, 5, 6;
- `IS-A`: canonical concept/entity nodes, requested depths 1, 2, 3, 4, 5, 6;
- two independent CAUSE chains coexist in one AH and are queried separately to verify no cross-chain trace leakage.

Every long chain contains nodes beyond the requested target. Therefore a passing test proves early goal stop rather than end-of-chain traversal.

## Cold-Workspace contract

Before every query:

```text
WorkspaceView.refs() == ()
```

After every query the same assertion must still hold. The complete runtime `uid -> excitation` snapshot is also compared before and after each proof.

Therefore these tests establish that:

```text
proof validity does not depend on x > t;
inference itself does not excite the proof chain;
Workspace membership is not silently used as a premise;
```

Workspace remains available only as an optional search-priority signal, consistent with the architecture.

## Trace contract

For a target at depth `d`, exact trace is:

```text
node_0, link_0, node_1, ... link_(d-1), node_d
```

So its length is exactly `2*d + 1`. All nodes and links after `node_d` are forbidden from that proof trace.

## Relation-specific semantics

`CAUSE` uses an explicit query premise and multi-step MP. Intermediate consequents are runtime search states.

`FOLLOW` uses H-domain event propositions, matching episodic semantics.

`IS-A` uses concept/entity nodes rather than abusing proposition `N` as taxonomy objects.
