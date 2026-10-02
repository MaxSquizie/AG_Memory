# M2 inference attention acceptance

M2 is now exercised through the same Ignition mechanics used by runtime memory.
A cold Workspace is **only** the first-case purity control proving that the answer
was not already present in active context. It is not a precondition of inference.

## Runtime contract

For `CAUSE`, `FOLLOW`, and `IS-A` proof search:

1. the Goal exists before traversal;
2. graph adjacency only generates rule candidates;
3. before semantic expansion of the current proposition, inference focus is moved
   through a `QUERY_RECALL` seed and one normal synchronous Ignition tick;
4. `x`/Workspace affect access and search priority but never truth;
5. proof stops immediately on `GOAL_SATISFIED`;
6. the UID trace contains only canonical elements actually used by the proof;
7. nodes/links after Goal are not added to the proof trace.

The reasoner still does not own excitation or write canonical AH. The injected
`IgnitionInferenceAttention` coordinator is the boundary that turns a proof-focus
shift into actual runtime activation.

## Large-AH behaviour

The operator runner works on a snapshot of the current live AH when one is
available. It does not mutate live memory. The sandbox is padded to at least
150,000 canonical UIDs so M2 cannot accidentally pass only because the graph is a
tiny fixture.

The suite contains:

- CAUSE: depth 1..6 in C;
- another CAUSE family: depth 1..6 in P;
- FOLLOW: depth 1..6 in H;
- IS-A: depth 1..6 in C;
- independent cross-chain queries;
- heavily branched chains, including warm distractor branches;
- one globally cold first-case purity control and many later warm-Workspace cases;
- typed mixed `AllOfGoal` proofs combining CAUSE/FOLLOW/IS-A without treating heterogeneous graph reachability as a rule.

Current total: 40 cases, including 8 typed mixed-rule proofs. See `M2_MIXED_GOALS_CANVAS_V061.md`.

Each case checks exact logical depth, `PROVED`, `GOAL_SATISFIED`, exact UID proof
trace, exact attention-focus proposition sequence, real x changes on the used path,
no pre-Goal activation of the tail, and no foreign branch leakage into either proof
trace or inference attention.

## Launch

GUI: `M2: inference attention`

CLI:

```text
ah-agent --config config/default.toml m2-acceptance
```

Each run writes:

```text
data/m2_runs/<timestamp>/result.json
data/m2_runs/<timestamp>/report.txt
```

No LLM call is required.
