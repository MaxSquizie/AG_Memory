# Slice 12.34 — additional-valency target with bound-role context

## Goal

Keep the calibrated semantic-completion scorer from v0.12.33, but correct the semantic target. The model must decide whether a predicate has an **additional reusable valency slot beyond roles already known for the TemplateCandidate**, not merely whether a receiver/source participant exists somewhere in the event meaning.

## Architecture boundary

The normative path is unchanged:

```text
unknown predicate
→ deterministic TemplateRequest preflight
→ Perception runtime TemplateCandidate proposal
→ deterministic validation
→ canonical T creation in Integration
```

`TemplateRequest` now transports only noncanonical source text plus textual role bindings. It does not expose canonical AH UIDs/refs to the model and does not mutate memory.

`T` valency evolution remains `[DEFER]`: low calibrated margin still fails closed before canonical T registration.

## Runtime role context

The Integration preflight preserves a minimal textual view of the occurrence that already exists in `PerceptionResult`, for example:

```text
SOURCE TEXT:
Иван подарил книгу.

RUSSIAN VERB:
подарить

ALREADY KNOWN ROLE BINDINGS:
SUBJECT: Иван
OBJECT: книга
```

For a role known structurally but unfilled in the concrete occurrence, Perception renders:

```text
OBJECT: [known slot; unfilled in this occurrence]
```

Candidate refs and context-resolved entities are represented by noncanonical descriptive placeholders. Canonical UID strings are never passed to the hidden-valency probe.

## Corrected semantic target

The three scored continuations are now explicitly about **additional slots**:

- additional receiver/addressee/beneficiary/destination slot;
- additional source/origin slot;
- neither additional directional slot.

Thus for:

```text
Лиза получит советы.
```

`SUBJECT=Лиза` is already shown. A model preference for "there is a receiver in a receiving event" must not be mapped to a new `RECIPIENT`; it would have to claim an additional receiver slot beyond the shown subject.

For:

```text
Иван подарил книгу.
```

an accepted receiver continuation means a genuinely missing reusable slot beyond `SUBJECT=Иван` and `OBJECT=книга`.

## Calibration

The neutral baseline keeps the same known-role shape but removes lexical content:

```text
SOURCE TEXT:
[unknown context]

RUSSIAN VERB:
UNKNOWN_VERB

ALREADY KNOWN ROLE BINDINGS:
SUBJECT: [known subject]
OBJECT: [known object]
```

The worker still ranks:

```text
score(real context, continuation)
- score(neutral context, same continuation)
```

No threshold tuning is introduced in this slice.

## Preserved mechanisms

Unchanged:

- morphology/lexeme filtering before transitivity;
- deterministic omitted-agent grammar;
- deterministic PURPOSE object-control;
- relation-specific CONTENT/GOAL/CAUSE/MANNER attachment;
- strict existing-T reuse;
- explicit ambiguity/fail-closed behavior;
- choice score diagnostics;
- live acceptance rendering.

This slice is intentionally a bounded final attempt to stabilize hidden directional valency with the weak local SLM. If real acceptance still cannot separate the additional-slot alternatives reliably, the next architectural move is to replace only this narrow runtime semantic cue with a stronger LLM while keeping deterministic validation and canonical Integration unchanged.
