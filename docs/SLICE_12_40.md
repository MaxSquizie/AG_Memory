# Slice 12.40 — semantic complement boundary, binary generation, turn-local identity

## Goal

Remove three mechanisms exposed by the v0.12.39 semantic acceptance run as systemic error sources rather than patching individual sentences.

## 1. Binary semantic decisions no longer use scorer margins

When Python has already narrowed a semantic question to exactly two protocol labels, Perception now uses ordinary temperature-zero generation and accepts only an exact label. No `choice_outputs`, score request, calibration, or margin threshold is sent for the binary call.

The legacy continuation scorer remains temporarily available only when a finite decision still has more than two alternatives. Its remaining uses are subject to later oracle-driven audit.

This prevents a categorical answer such as `CONTENT_LINK` from being vetoed by an unrelated continuation-score margin.

## 2. Nested content is OBJECT; PURPOSE means actual purpose

Same-clause nested situations are tested as `OBJECT` content/complement before `PURPOSE`.

`OBJECT -> candidate_ref(child)` covers selected proposition/action content such as:

- say/think/perceive content;
- wanted situations;
- requested situations;
- attempted/started situations where the child is what the parent predicate selects.

`PURPOSE` is reserved for a child situation that is the goal/reason for performing the parent action itself.

An animate accusative participant is no longer deterministically collapsed to OBJECT. Morphology narrows it to `{OBJECT, RECIPIENT}` and one tiny semantic probe selects the role. Controller selection for an omitted child subject is a separate decision; the retired `PURPOSE + OBJECT => object controller` shortcut is removed.

## 3. Relative-coreference identity survives containing evidence spans

Relative antecedent binding no longer requires exact evidence-span equality. Exact matches remain preferred; otherwise a containing parent actant may be reused only when its normalized semantic head matches the antecedent.

This handles structures such as:

```text
рядом с журналом ... который ...
^^^^^^^^^^^^^^^^^    ^^^^^^^
LOCATION evidence    same journal identity
```

The shared runtime `entity_ref` is established before Integration, so P provenance of a concrete object is preserved across linked assertions instead of creating a second C identity.

## Acceptance consequence

The v0.12.39 real run was:

```text
32 PASS / 4 FAIL / 4 GAP
```

The four FAIL roots addressed here are:

- request complement / recipient / controller semantics;
- wanted complement classified as PURPOSE;
- the same request error inside a causal sentence;
- loss of turn-local identity causing P -> C provenance drift.

No claim is made that the real run is now 36/40 until it is rerun with the selected local model. The four existing `ARCHITECTURE_GAP` cases are deliberately unchanged.
