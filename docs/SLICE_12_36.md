# Slice 12.36 — sequential binary hidden-valency generation

## Goal

Keep hidden directional valency as a tiny semantic cue from the same local Qwen model, but replace the unstable five-way output protocol with the ordinary binary generation shape that the parser already handles more naturally.

## Architecture boundary

The normative dynamic-T path is unchanged:

```text
unknown predicate
→ deterministic grammar narrowing
→ Perception semantic cue
→ Python TemplateCandidate
→ deterministic Integration validation
→ canonical T registration / atomic AH mutation
```

The model receives no canonical UID/ref and never creates or registers `T/N/L/k`.

## Runtime protocol

After deterministic SUBJECT/OBJECT narrowing, residual directional discovery is:

```text
1. RECIPIENT probe
   HAS_RECIPIENT_SLOT
   NO_RECIPIENT_SLOT

2. only after NO_RECIPIENT_SLOT:
   SOURCE probe
   HAS_SOURCE_SLOT
   NO_SOURCE_SLOT
```

A positive RECIPIENT answer stops the procedure. Therefore one hidden-valency procedure can add at most one directional slot.

There is no active `RECIPIENT,SOURCE` outcome and no `AMBIGUOUS` label in this protocol.

## Prompt input

Each call receives only:

- source sentence;
- resolved lexical verb;
- textual bindings for roles already known to the runtime TemplateCandidate;
- one narrow English question;
- exactly two English labels.

The shared instruction explicitly says not to count an already shown SUBJECT or OBJECT again.

## Generation boundary

Both calls use ordinary temperature-zero generation.

The active path sends no:

- `choice_outputs`;
- `return_choice_scores`;
- calibration prompt;
- score margin;
- continuation likelihood request;
- token-probability decision rule.

After outer whitespace trimming, only an exact expected label is accepted. Punctuation, explanation, multiple labels, old v0.12.35 labels, or any other text fail closed before TemplateCandidate acceptance.

## Preserved mechanisms

Unchanged:

- deterministic morphology/transitivity;
- omitted-agent grammar;
- direct-object fallback;
- relation-specific frame attachment;
- deterministic PURPOSE object-control;
- strict existing-T reuse;
- directional hidden discovery disabled when RECIPIENT/SOURCE is already observed;
- T valency evolution remains `[DEFER]`;
- Integration remains the only canonical validation/registration boundary.

## Evaluation intent

This slice is deliberately a protocol-shape experiment. It does not change semantic scope or add a new parser ontology. The acceptance comparison against v0.12.35 should answer only whether sequential binary generation lets Qwen make the hidden-valency decision reliably enough to keep this task on the local model.
