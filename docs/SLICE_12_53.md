# Slice v0.12.53 — generic binary semantic role router

## Why this slice exists

v0.12.52 reacted too directly to individual broad200 failures. It introduced useful-looking but insufficiently general shortcuts: a closed temporal-adverb list, a duration-unit list, bare instrumental → TOOL/HOW_TO, `из` → SOURCE/MATERIAL, a `чем` whitelist, and morphology filters motivated by `Анне`/`вазу`. None was a literal sentence-specific `if`, but together they made correctness depend on hand-maintained Russian constructions.

v0.12.53 removes those additions and keeps the architecture boundary instead.

## Production contract

1. Deterministic processing may **reject** a role only when the evidence is formally incompatible with that role. Current new example: finite number/gender agreement can reject a nominative SUBJECT reading. Missing or ambiguous morphology never rejects it.
2. Surface evidence is preserved. In a WH phrase such as a preposition + interrogative pronoun, the preposition remains inside the target span. It is not converted directly to SOURCE/PURPOSE/etc.
3. Semantic role routing is ontology-generic and binary. The model answers natural cue labels such as `ENTITY_OR_CONTENT_RELATION / MODIFIER_RELATION`, `PLACE_OR_POSITION / TEMPORAL`, or `INSTRUMENT / SUBSTANCE_OR_MATERIAL`. Python maps the final branch to `ActantRole`.
4. Every role-router model call has exactly two labels and therefore uses the clean exact-generation protocol. The legacy >2 choice scorer/margin path is not used for role routing.
5. If earlier deterministic structure supplies `allowed_roles`, every later partition intersects with that set. Excluded roles cannot reappear.
6. Malformed binary output fails closed. A selected semantic span is never silently omitted.

## Explicitly removed from v0.12.52

Production no longer contains:

- `_TEMPORAL_ADVERBS`;
- `_DURATION_UNIT_LEMMAS`;
- `_duration_unit_lemma`;
- `_span_is_numeric_duration`;
- bare instrumental → `{TOOL, HOW_TO}`;
- `из` → `{SOURCE, MATERIAL}`;
- special `чем` → `{TOOL, MATERIAL, HOW_TO}`;
- v0.12.52 fixed-name / lowercase abbreviation morphology suppression.

The broad200 sentences that motivated those changes remain tests/oracle data. They must now succeed or fail through general mechanisms.

## What is intentionally unchanged

- AH Core and Integration.
- Controlled monotonic T evolution.
- nested content/control handling.
- CONDITION and structural clarification.
- broad200-v2 corpus and scenario isolation.
- default model path.

## Acceptance rule

No broad200 score is claimed for v0.12.53 until a real run on the configured Qwen model is supplied. Unit tests establish architecture/protocol invariants, not semantic benchmark performance.
