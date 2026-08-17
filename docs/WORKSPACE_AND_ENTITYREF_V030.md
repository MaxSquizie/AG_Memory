# v0.30 — entity_ref materialization + Workspace viewer

## CandidateValidationError fix

A turn-local `entity_ref` is one identity commitment. During one assertion several
roles can legitimately reference the same previously unseen participant. Staging
used to produce several equivalent `NewEntityPlan` objects and materialize each
into a different `M`, after which Integration raised its own
`resolved inconsistently` error.

v0.30 materializes the first occurrence and reuses its canonical ref for all later
occurrences of the same `entity_ref`. A conflict between already-canonical distinct
refs remains fail-closed.

## Workspace GUI

A separate `Workspace` dock now displays the exact `x > t` set. Each row contains:

- human-readable ACTIVE semantic projection;
- AH kind and C/P/H domain;
- current `x` and `output`;
- decay age and N lifecycle when applicable;
- UID as a secondary debug identifier.

Rows are ordered by current `x` only for operator readability. This is a diagnostic
presentation and does not rank/filter/change Workspace membership. Clicking a row
selects the same node on the canvas/inspector.
