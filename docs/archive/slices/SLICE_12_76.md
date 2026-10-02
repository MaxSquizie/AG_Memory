# v0.12.76 — deep semantic cue for nominal naming projection

## Live failure addressed

The real v0.12.75 trace showed that syntax and frame construction were already correct:

```text
название(Крипл, моего проекта)
имя(Крипл, моего ИИ)
```

but the weak fixed-choice `nominal_predicate_family` probe returned
`OTHER_NOMINAL` for both `название` and `имя`. Rewording the same weak probe again
would only move the failure around.

## Change

The weak predicate-family classifier is removed from the runtime path. After
fully deterministic nominal syntax has reduced the problem to one local frame, a
separate deep-semantic request answers only one paraphrase:

```text
Does this clause say that the thing described by the complement
is called/named/titled/labeled/designated by SUBJECT?

YES / NO / UNCLEAR
```

The request:

- uses role `semantic_nominal_label_semantics`, not an ordinary perception role;
- receives no AH UID, Workspace, proof trace, memory contents, or candidate truth;
- cannot create or choose canonical elements;
- runs at temperature 0;
- requests thinking mode locally on backends that support it;
- returns only the bounded semantic cue `YES / NO / UNCLEAR`.

When the cue is `YES`, deterministic Python selects the already parsed complement
noun concept. If there is exactly one noun concept, no second semantic call is
made. Multiple candidate nouns still use the existing bounded target selector.

This keeps the architecture boundary intact: the stronger model proposes only a
runtime semantic cue; validation, identity, canonical T/N creation, projection,
and later proof remain deterministic.

The previous `nominal_predicate_family.txt` prompt is removed and replaced by
`nominal_label_semantics.txt`.

## Request-local thinking

`ah.llm.worker._encode_prompt` now accepts a request-local `enable_thinking`
override. The process worker and Ollama backend honor the override without
changing the global model setting. Ordinary `perception_*` calls remain non-thinking.
Only the isolated `semantic_*` path requests thinking.

## Verification

```text
nominal targeted: 15 passed
LLM + nominal targeted: 82 passed
full suite: 477 passed + 22 subtests, 0 failed
M2 acceptance: 40/40 PASS
M2 AH size: 153502 UIDs
final Workspace: 248
```
