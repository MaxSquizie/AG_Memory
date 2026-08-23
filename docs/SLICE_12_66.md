# v0.12.66 — semantic GoalCompiler

## Goal

Natural-language evidence retrieval no longer selects inference rules from command words.
The inference rule is compiled from the already parsed semantic turn structure.

## Runtime semantic contract

`ActRelationCandidate` is a UID-free Perception cue:

```text
relation_id + act_ref + source_role + target_role
```

The first registered intra-act relation is `IS-A`. Python narrows endpoint candidates
from already parsed semantic roles; the perception model makes one exact fixed-choice
decision (`NONE` or one local role-pair label). Canonical UIDs are never exposed.

`GoalSemanticService` is shared by live turns and raw corpus/dialogue import.

## Deterministic compilation

`SemanticGoalCompiler` compiles:

- direct role/existence query -> `RoleFillGoal` / `MultiRoleFillGoal` / `ExistsGoal`;
- typed intra-act `IS-A` -> `RelationGoal("IS-A", source, target)`;
- embedded `FOLLOW` -> `RelationGoal("FOLLOW", source, target)`;
- structural embedded `CAUSE` -> direct `RelationGoal("CAUSE", source, target)`;
- asserted cause premise + embedded effect -> `CauseEntailmentGoal(effect)` with explicit `premise_refs`;
- explicit proposition-level `AND` -> `AllOfGoal`;
- proposition-level `OR` -> explicit unsupported diagnostic (never rewritten as AND).

No command/predicate surface word chooses a rule.

## No self-proof

Relations whose endpoint propositions are `EMBEDDED`, `CONDITIONAL` or `QUOTED` are
not materialized into canonical `L` truth by Integration. Scoped N mentions are mapped
back to an already existing ordinary N by canonical `T + actants` signature for proof
lookup only. If no ordinary proposition exists, the scoped ref remains and proof fails.

An inferred structural link may still be materialized *after* a successful proof by the
normal `InferenceMaterializer`; this is post-proof knowledge materialization, not evidence.

## IS-A ingestion

For an ordinary asserted act with a validated `ActRelationCandidate(IS-A, ...)`, Integration
creates/reuses the canonical `IS-A` link using `integration.is_a_link_weight`. The same
semantic completion path is used for live text and raw corpus imports.

## Validation

```text
pytest: 432 passed + 22 subtests
M2 operator: 40/40
AH sandbox: 153502 UIDs
```
