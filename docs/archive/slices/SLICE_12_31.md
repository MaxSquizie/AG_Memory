# Slice 12.31 — gated hidden valency for SLM-first Perception

## Architecture alignment

Normative boundary remains:

```text
Text
→ Perception (deterministic narrowing + one tiny semantic cue when needed)
→ PerceptionResult / TemplateCandidate
→ Deterministic Integration
→ canonical T/N/L/k
```

Perception does not create canonical UIDs or mutate AH. `T` valency evolution remains
`[DEFER]`, so a genuinely unresolved justified hidden slot is fail-closed before T
registration.

## No hidden-role ontology walk

Template discovery no longer asks RECIPIENT and then SOURCE (or walks any other role
sequence). The pipeline is bounded:

```text
observed roles
→ deterministic SUBJECT grammar
→ deterministic/dictionary OBJECT grammar
→ at most one event-type SLM classification
→ at most one hidden RECIPIENT or SOURCE
→ deterministic TemplateCandidate validation
```

If RECIPIENT or SOURCE is already observed, directional hidden-role discovery ends.
This prevents a valid `подарить Марии книгу` frame from triggering a speculative
SOURCE probe.

## SUBJECT grammar

A narrow Russian indefinite-personal pattern is recognized deterministically: finite
indicative plural verb, no overt material nominative noun/pronoun. For `Мне дали
книгу`, Perception can therefore propose `T( SUBJECT, OBJECT, RECIPIENT )` while the
concrete N still omits SUBJECT. This follows the architecture rule that not every role
of T must be filled in each N.

## OBJECT grammar

Stable OpenCorpora `tran/intr` remains the first source. If unavailable, the SLM gets
only one English grammar question:

```text
Can this Russian verb normally take a direct accusative noun phrase
without a preposition?

TAKES_DIRECT_ACCUSATIVE
NO_DIRECT_ACCUSATIVE
```

No semantic recipient/source inference is mixed into this probe.

## Directional semantic cue

Only a simple participant frame with SUBJECT+OBJECT and no existing directional or
non-participant relation may reach one event classification:

```text
TRANSFER_TO_RECEIVER
COMMUNICATE_TO_ADDRESSEE
ACQUIRE_FROM_SOURCE
OTHER_EVENT
```

Deterministic mapping is:

```text
TRANSFER_TO_RECEIVER      -> RECIPIENT
COMMUNICATE_TO_ADDRESSEE  -> RECIPIENT
ACQUIRE_FROM_SOURCE       -> SOURCE
OTHER_EVENT               -> no hidden directional role
```

Exactly one event classification is allowed; it can add at most one role. A low
margin is explicit ambiguity/error before canonical T creation.

## Preserved mechanisms

- relation-specific CONTENT/GOAL/CAUSE/MANNER frame probes from v0.12.30;
- direct mutually-exclusive controller choice;
- full score/margin diagnostics;
- FOLLOW/CAUSE structural normalization;
- clarification lifecycle and k_AMBIGUOUS;
- live VisPy acceptance canvas;
- strict existing-T reuse and no implicit valency widening.
