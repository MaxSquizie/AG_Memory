# Counterfactual GoalCompiler acceptance v1

This suite covers backlog point 5 independently from quantified-goal and XOR work.

## Input boundary

The GoalCompiler does **not** recognize Russian/English surface markers such as
`если бы`, `if`, `what if`, or `что было бы`. Counterfactual semantics must already
be present in Perception as:

- one QUERY root;
- one or more non-quoted descendant assertions with
  `AssertionStatus.HYPOTHETICAL`;
- optionally an explicit non-hypothetical EMBEDDED target proposition.

For a direct polar query where the query itself is Q and only hypothetical
assumptions are separate descendants, `apply_speech_act_scoping` creates one
runtime shadow assertion:

```text
Q1:__CF_TARGET__
status = EMBEDDED
predicate/actants = QueryCandidate predicate/actants
```

Integration canonicalizes that shadow as scoped proposition content with
`occurrence_count=0`. It is addressable as a FormulaGoal target but is not an
ordinary factual premise.

The suffix form is intentional: document namespacing preserves idempotence:

```text
Q1:__CF_TARGET__
-> B0:Q1:__CF_TARGET__
```

and a later scoping pass derives the same ID.

## Goal compilation

The public `SemanticGoalCompiler` / `TurnGoalBuilder` builds:

```text
CounterfactualGoal(
    assumptions=(hypothesis_1, hypothesis_2, ...),
    target=FormulaGoal(target_ref),
)
```

Sibling hypothetical propositions are simultaneous assumptions in one overlay.
If a hypothetical proposition contains embedded content of its own, that nested
content remains inside the assumption subtree and is not selected as the query
target.

## Existing reasoner ownership

No new counterfactual inference engine is introduced here. Existing
`CounterfactualGoal`, `CounterfactualContext`, and `GroundFormulaReasoner` retain
ownership of:

- local positive/negative overrides;
- dependency-aware support filtering;
- conflict detection for incompatible assumptions;
- ordinary rule reasoning inside the overlay;
- prohibition on materializing counterfactual conclusions into factual AH.

## Fail-closed boundary

The current `CounterfactualGoal` has a `FormulaGoal` target. Therefore this point
intentionally rejects rather than guesses:

- open-ended `FILL_ROLE` counterfactuals such as an unconstrained “what would
  happen?”;
- typed structural relation targets that require `RelationGoal` semantics;
- quantified+counterfactual target composition, which belongs to explicit future
  composition of the two independent goal contracts.

Quoted dependency edges are never treated as counterfactual scope.

`oracle.json` contains 12 exact downstream cases. The regression tests also verify
that solving a counterfactual leaves canonical AH unchanged and that the ordinary
world regains its original truth status immediately after the overlay ends.
