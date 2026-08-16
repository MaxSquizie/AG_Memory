# Slice 12.33 — calibrated semantic continuations

## Goal

Remove protocol-token bias from hidden directional TemplateCandidate discovery without widening the LLM trust boundary.

## Architecture boundary

The normative path remains:

```text
unknown predicate
→ Perception runtime TemplateCandidate
→ deterministic validation
→ canonical T creation in Integration
```

The model never receives or writes AH UIDs and never creates canonical `T/N/L/k`. `T` valency evolution remains `[DEFER]`; an unresolved calibrated decision fails closed before canonical mutation.

## Semantic completion scoring

The previous ordinal `FIRST/SECOND` continuation labels were dominated by a model prior. v0.12.33 scores the semantic continuations themselves. For each continuation `c`:

```text
semantic_score(c) = mean_logP(c | Russian verb context)
                  - mean_logP(c | UNKNOWN_VERB context)
```

The neutral prompt is structurally identical and uses the same system/instruction text. The calibrated margin, not the raw continuation margin, gates the runtime cue.

Hidden directional discovery is one bounded three-way decision:

- receiver / addressee / destination semantics → runtime `RECIPIENT` cue;
- source / origin semantics → runtime `SOURCE` cue;
- neither → no hidden directional role.

Deterministic code maps the accepted cue to at most one TemplateCandidate role and stops.

## Controller narrowing

When Perception has already established:

```text
PARENT.OBJECT = X
PARENT.PURPOSE -> CHILD(infinitive)
```

and there is exactly one parent `OBJECT` candidate before the child predicate, `X` is used as the child controller deterministically inside Perception. This is a structural object-control rule, not an Integration repair and not a predicate-specific sentence rule.

## Diagnostics

Acceptance request logs now include:

- `choice_scores` — raw lexical-context continuation scores;
- `calibration_choice_scores` — neutral-context scores;
- `calibrated_choice_scores` — per-choice deltas;
- `raw_choice_margin`;
- `choice_margin` — calibrated top-two margin;
- `choice_scoring_mode`.

These values are parser evidence only and never map to truth or `w`.
