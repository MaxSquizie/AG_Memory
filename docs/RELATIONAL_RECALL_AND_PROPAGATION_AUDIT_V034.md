# v0.34 — relational reference recall + propagation audit

## Relational reference

Canonical identity is unchanged for the observed memory structure:

```text
N_ЕСТЬ
├── SUBJECT    -> USER
├── OBJECT     -> ДРУГ
└── AUXILLIARY -> МИША
```

`ДРУГ` and `МИША` remain different `m` nodes. A runtime reference such as `моего друга` is resolved read-only:

```text
мой -> USER
head -> ДРУГ
hypernodes_for_actant(USER) ∩ hypernodes_for_actant(ДРУГ)
    -> N_ЕСТЬ
remaining semantic participant
    -> МИША
```

If exactly one referent remains, it is returned as the runtime entity resolution. If several remain, ambiguity is preserved. No new canonical N/L is invented.

For a query, the resolved referent and the supporting N are exposed as `QUERY_RECALL` attention anchors before the post-input tick. `QUERY_RECALL` does not perform h_N confirmation and is not proof of the requested predicate. It only lets Workspace/AgentContext contain the already canonical chain even if exact `звать(...)` inference is UNKNOWN.

On `ah_memory(20260817-172356).json`, the concrete result is:

```text
моего друга -> M_Миша
support -> N_ЕСТЬ(USER, ДРУГ, МИША)
```

After one query-recall tick both the referent and support N are above Workspace threshold; ACTIVE projection contains `Миша` and the complete `есть(... друг ... Миша)` fact.

## Propagation topology of ah_memory(20260817-172356).json

The audit mirrors current Ignition propagation only:

```text
canonical L source -> target
S -> T
T -> asserted N       (scaled by N.w)
N -> actants           (scaled by N.w)
```

Pacemaker/external seeds are packet sources and are not graph edges.

Measured topology:

```text
excitable nodes:          37
propagation edges:        56
cyclic SCCs:               0
longest directed path:    14 hops
```

Therefore this snapshot has **no structural positive-feedback cycle**. With pacemaker disabled and no new incoming packet, 60 ticks produced:

```text
activation events: 0 on every tick
new outgoing packets: 0 on every tick
```

Retained `x` remains because of the floating floor, but retained `x` has `output=0` and does not feed the graph again.

### Why activity can nevertheless look cyclic

The default pacemaker is `1 Hz` and round-robins over the eligible graph. It injects a new packet every second. With pacemaker enabled, 60/60 observed ticks had activation events; near ticks 56–60 a single tick contained roughly 8–11 downstream activation events because several older feed-forward waves overlapped.

The largest fan-out hub in this memory is:

```text
S_ВЫСКАЗАТЬ -> T_UTTERANCE -> 12 H event_instance nodes -> FOLLOW/history/actants
```

For a unit packet at `S_ВЫСКАЗАТЬ`, the sum of all downstream path gains is approximately `7.4024`. This value may exceed 1 because the architecture copies one output packet over multiple outgoing branches; it is not a cycle gain. With the current pacemaker pulse `0.08`, the complete distributed wave corresponds to roughly `0.592` cumulative downstream packet mass over its lifetime, spread across many nodes/ticks.

Other top fan-out sources in this snapshot:

```text
S_ВЫСКАЗАТЬ     7.4024
T_UTTERANCE     6.4024
S_ЕСТЬ          1.8800
S_БЫТЬ          1.7200
S_ПРИВЕТ        1.5600
S_ПОМОЧЬ        1.4000
```

The longest path is dominated by the H `FOLLOW` chain; its product gain is extremely small (about `1.65e-9` from the first lexical source to the final endpoint), so it does not self-sustain without continued external/pacemaker input.

## Conclusion

1. Do not merge `ДРУГ` and `МИША`; relational reference lookup is sufficient.
2. Do not enable continuous reverse `actant -> N` propagation for this purpose. The reverse actant index is used only for bounded deterministic lookup.
3. Current snapshot has no propagation cycle.
4. The main source of persistent background motion is `nu`, especially when it hits broad H-envelope hubs such as `S_ВЫСКАЗАТЬ`.
5. If background activity is too noisy, the next tuning target should be pacemaker eligibility/target policy, not another decay hack or reverse hyperedge.
