# Slice v0.12.57 — single-shot runtime role cues

## Evidence from the real v0.12.56 run

- broad200-v2: 200 cases, 149 isolated scenarios.
- Runtime: 199 OK / 1 ERROR.
- Semantic: 163 PASS / 37 FAIL / 0 GAP.
- Frozen regression40: 40/40 PASS.
- Acceptance restored the pre-run AH/InteractionContext/Ignition state.

The property ladder introduced in v0.12.56 did not reduce semantic uncertainty. It compounded it. For instrument/source/time targets the local model repeatedly answered `NO` to several individually reasonable properties, so the correct role subset was removed and the residual participant router later selected AUXILLIARY/SUBJECT/OBJECT. This is an architecture failure of multi-step semantic routing, not a missing Russian word rule.

## Production change

`AdaptivePerceptionParser._classify_role()` now has one semantic boundary after deterministic structural narrowing:

```text
formal morphology/syntax
        ↓
remove only impossible ActantRole candidates
        ↓
one role_cue generation for one TARGET
        ↓
RuntimeRoleCue
        ↓ Python-owned mapping
ActantRole
```

`RuntimeRoleCue` is an internal perception protocol enum. It is not canonical AH and is never persisted. Examples include `ACTOR_OR_EXPERIENCER`, `AFFECTED_OR_CONTENT`, `ORIGIN`, `TIME_POINT`, `INSTRUMENT`, and `CONSTITUENT_MATERIAL`. Only cues corresponding to currently admissible roles are shown.

The role-cue call uses ordinary deterministic generation with exact label validation. It does **not** pass `choice_outputs`, request likelihood scores, use a margin threshold, or run a hidden pairwise tournament. Invalid output fails closed before Integration.

The v0.12.56 semantic-property ladder and family-tree routing are absent from production. The v0.12.56 quantified-phrase normalizer is also not retained; its counted-entity/event-measure ambiguity is deferred to a dedicated structural slice rather than mixed into role routing.

The legacy direct `из/от -> SOURCE` shortcut is removed. Prepositions remain part of the evidence span passed to the cue model.

## Coreference safety

Third-person anaphora now respect explicit grammatical-person mismatch as negative deterministic evidence. If an anaphor is explicitly `3per`, a candidate antecedent explicitly marked `1per` or `2per` is excluded from the local candidate pool. Missing person information does not force or reject a binding. This prevents deictic speaker/addressee mentions from creating false runtime alternatives for a third-person pronoun.

## Non-goals

- no broad200 sentence literals in production;
- no new preposition/case -> role table;
- no LLM canonical UID/T/N writes;
- no claim of a v0.12.57 broad200 score before a real run;
- quantified NUMERAL+nominal semantics remain a separate unresolved family.
