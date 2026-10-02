# Slice 12.7 — semantic CAUSE relations

Causal subordinate clauses were already composed into the parent frame as a
`CAUSE` actant referencing the child situation. Slice 12.7 makes the canonical
situation relation explicit as well.

The relation compiler is semantic rather than tied to one Russian connective:
whenever composition establishes

```text
parent.CAUSE = @child
```

Perception emits

```text
child --CAUSE--> parent
```

as a `SituationRelationCandidate`. Integration accepts `CAUSE` together with
`FOLLOW` and materializes it as canonical `L`, after all local assertion refs
have been resolved. This means a causal relation obtained through a known
connective or through later ambiguity resolution follows the same compiler path.

`integration.cause_link_weight` controls the initial canonical CAUSE link
weight. Existing configs remain compatible: when the setting is absent it falls
back to `follow_link_weight`.
