# Slice 12.35 — bounded generative hidden-valency proposal

## Goal

Replace the unreliable likelihood/calibration interface used only for residual hidden directional valency with one ordinary bounded generation from the same stateless Qwen parser model.

## Architecture boundary

The normative dynamic-T path remains:

```text
unknown predicate
→ Perception semantic proposal
→ deterministic validation
→ resolve/create predicate S
→ create/register canonical T
→ resume Integration
```

The model never receives or assigns canonical UIDs and never writes `T/N/L/K` or AH links.

## Runtime input

The hidden-valency call receives only:

- source text for the predicate occurrence;
- predicate surface and resolved lexical form;
- textual bindings for roles already known to the runtime TemplateCandidate.

No canonical AH references are serialized into the prompt.

## Protocol

Exactly one line is accepted:

```text
NONE
RECIPIENT
SOURCE
RECIPIENT,SOURCE
AMBIGUOUS
```

`RECIPIENT` and `SOURCE` are only runtime semantic cues. Python maps them to canonical `ActantRole` values before Integration. `AMBIGUOUS`, multi-line explanation, or any unknown label fails closed before canonical T creation.

## Removed from the active hidden-valency path

- exact-continuation likelihood ranking;
- `FIRST/SECOND` protocol scoring;
- content-free calibration;
- choice margins / threshold gating;
- neutral `UNKNOWN_VERB` baseline.

Generic fixed-choice scoring remains available to other narrow parser probes; it is not a fallback for hidden valency.

## Preserved mechanisms

Deterministic morphology/transitivity, omitted-agent grammar, direct-object fallback, relation-specific frame attachment, deterministic PURPOSE object-control, strict existing-T reuse, explicit ambiguity and atomic Integration are unchanged. T valency evolution remains `[DEFER]`.
