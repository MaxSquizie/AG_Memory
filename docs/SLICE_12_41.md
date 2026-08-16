# Slice v0.12.41 — delayed role semantics and provenance-safe entity lookup

## Why this slice exists

The real v0.12.40 acceptance run regressed from the previous baseline:

```text
semantic PASS 31/40
semantic FAIL 6/40
architecture GAP 3/40
```

The regression was not six unrelated sentence bugs. Raw Perception traces exposed three root mechanisms:

1. v0.12.40 asked an LLM to classify every animate/pronominal accusative as `OBJECT` vs `RECIPIENT` before structural context was known. Ordinary direct objects such as `его` in `отправил его Марии` and `взял его` were therefore misclassified.
2. The controller prompt mixed protocol labels with descriptions (`SECOND: Иван ...`), while the validator required the bare label `SECOND`.
3. Entity resolution treated a same-name canonical entity in another domain as identity evidence. A previously known `C:журнал` could therefore hijack the concrete journal introduced inside a `P` event, despite `name` being only a retrieval key.

v0.12.41 removes/narrows those mechanisms instead of adding sentence-specific branches.

## Delayed role decision

A surface accusative is again a deterministic direct `OBJECT` candidate. Perception does **not** ask the model whether every animate accusative is an addressee.

A bounded `RECIPIENT / NOT_RECIPIENT` probe is introduced only after independent structure proves that a nested situation is semantic `OBJECT` content and one entity-valued `OBJECT` already occupies that slot. Then, and only then, the existing participant may be reclassified to `RECIPIENT`.

Example:

```text
Иван попросил Марию прочитать книгу.
```

Processing narrows in this order:

```text
прочитать(...) is CONTENT_LINK
        ↓
parent semantic OBJECT must be the nested proposition
        ↓
existing participant "Марию" conflicts with that OBJECT slot
        ↓
RECIPIENT / NOT_RECIPIENT
        ↓
controller FIRST / SECOND
```

The model performs only the semantic decision that remains after deterministic narrowing.

## Exact controller protocol

Human-readable participant descriptions are separated from protocol labels:

```text
PARTICIPANTS:
FIRST = Мария
SECOND = Иван

CHOICES:
FIRST
SECOND
```

The validator still accepts only the exact bare label. This avoids creating malformed answers by teaching the model a longer pseudo-label such as `SECOND: Иван`.

## Provenance-safe entity resolution

`name / aliases` remain retrieval indexes, never cross-domain identity keys.

If Integration already has strong provenance/identity evidence from `SELF/USER` deixis, a resolved `candidate_ref`, or an established turn-local `entity_ref`, it computes a provisional provenance domain before ordinary lexical lookup. Lexical entity search is then restricted to that domain.

Thus a pre-existing generic `C:журнал` cannot capture the concrete journal in:

```text
Я положил книгу рядом с журналом, который был новым.
```

The action introduces/reuses a `P:журнал`; the relative assertion reuses the same turn-local identity and therefore also remains in `P`.

Without strong provenance evidence, global name lookup is still allowed to generate candidates so existing cross-turn name resolution and explicit ambiguity continue to work.

## Architecture changes

`docs/reference/Архитектура_v3.md` is now working specification v0.7 and records:

- semantic probes are delayed until deterministic structure has narrowed the ambiguity;
- protocol `CHOICES` contain bare labels, with descriptions outside the choice set;
- name/alias lookup is retrieval-only and cannot prove cross-domain identity;
- strong provenance may establish a provisional lookup domain inside deterministic Integration before lexical entity resolution.

## Regression coverage

New tests verify:

- ordinary object pronouns do not invoke the participant-role LLM probe;
- discourse `его` remains `OBJECT` and corefers after deterministic role assignment;
- `попросить Марию прочитать` invokes recipient classification only after nested OBJECT-content is established;
- controller prompt separates participant descriptions from exact labels;
- a pre-existing same-name C entity cannot hijack a personal P entity introduced by strong provenance.

The production 40-case semantic result for v0.12.41 must be measured by a new real model run; this slice does not infer acceptance success from unit tests.
