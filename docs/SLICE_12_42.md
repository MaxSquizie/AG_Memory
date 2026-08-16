# Slice v0.12.42 — semantic-relation monotonicity

## Observed real baseline

The v0.12.41 40-case semantic run produced:

```text
34 PASS
2 FAIL
4 ARCHITECTURE_GAP
```

Both FAIL cases are `попросить + infinitive`. In both traces the model already returns `CONTENT_LINK` for the nested infinitive and the controller decision is correct. The failure occurs later: participant reconciliation returns `NOT_RECIPIENT`, after which the parser probes PURPOSE and replaces the previously accepted content relation with `GOAL_LINK`.

## Root invariant

A positive semantic relation is not a disposable intermediate guess. After deterministic narrowing and exact protocol validation accept:

```text
parent -> OBJECT(content child)
```

a later participant-role reconciliation may refine an explicit entity role, but it may not reinterpret the same child as PURPOSE/CAUSE/HOW_TO merely to make the frame fit.

If the role conflict cannot be represented safely, Perception fails closed.

## Narrow participant decision

Only after CONTENT is established and an entity-valued OBJECT occupies the single semantic OBJECT slot, the remaining bounded question is:

```text
Is PARTICIPANT the receiver/addressee/target of the PARENT action?

RECIPIENT
NOT_RECIPIENT
```

The wording explicitly includes request/address cases (the person being asked or told) and removes the misleading `beneficiary` wording.

## Architectural boundary

LLM output still does not write AH. The model proposes only the bounded semantic cue; Python validates the exact label and constructs the runtime candidate. Integration/AH Core remain the sole canonical writers.
