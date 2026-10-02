# Slice 12.29 — contrastive SLM decisions and inspectable evidence

## Goal

Keep the model boundary small enough for an SLM while removing the universal
affirmative bias observed in v0.12.28. Deterministic code must enumerate and narrow
candidates first; the model only distinguishes the remaining finite alternatives.

## Semantic protocol

### Hidden T role

One deterministic latent-role hypothesis is shown at a time. The output pair names
the semantic distinction instead of using YES/NO:

- `SUBJECT_ARGUMENT / NO_SUBJECT_ARGUMENT`
- `DIRECT_OBJECT_ARGUMENT / NO_DIRECT_OBJECT_ARGUMENT`
- `RECEIVER_ARGUMENT / NO_RECEIVER_ARGUMENT`
- `SOURCE_ARGUMENT / NO_SOURCE_ARGUMENT`

At most one hidden role can be added to a new TemplateCandidate. Existing T is never
implicitly widened; valency evolution remains deferred.

### Nested frame attachment

Python proposes one structurally plausible relation. The SLM only classifies:

- `PARENT_ARGUMENT`
- `SEPARATE_EVENT`

The concrete canonical role (OBJECT/PURPOSE/CAUSE/HOW_TO) remains owned by the
deterministic candidate that generated the question.

### Controller resolution

Controller candidates are mutually exclusive, so they are compared in one request:

- `FIRST`
- `SECOND`
- ...

A low likelihood margin does not pick a controller; Perception preserves complete
runtime alternatives for deterministic Integration/ambiguity handling.

### Actant role classification

Role families and exact roles are direct small finite choices over candidates already
filtered by deterministic syntax/morphology and used-role constraints. There is no
universal YES token and no NONE/UNKNOWN escape label.

## Fixed-choice evidence

Every LocalLLMProcessBackend request now records, when available:

- `choice_outputs`
- `choice_scores`
- `choice_winner`
- `choice_margin`
- `decision_margin_threshold`
- `decision_accepted`

Acceptance artifacts therefore preserve the actual SLM evidence used by deterministic
margin gating. These values are parser diagnostics only: they are not AH truth,
belief, weight, or activation.

## Preserved invariants

- deterministic algorithms narrow first;
- SLM never emits canonical UID or mutates AH;
- no implicit T widening;
- low-margin semantic evidence stays unresolved;
- canonical ambiguity remains `k_AMBIGUOUS` only after deterministic resolution;
- clause CAUSE/FOLLOW normalization is unchanged;
- live VisPy canvas during acceptance remains enabled.
