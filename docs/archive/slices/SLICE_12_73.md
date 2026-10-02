# v0.12.73 — Explicit copular direction is structural, not an LLM vote

The live Qwen trace for `Крипл - это название моего проекта и одновременно с этим это имя моего ИИ` exposed a flaw in v0.12.72: after Python had already recognized the explicit nominal copular shell, a `REFERENTIAL / PREDICATIVE / UNCLEAR` probe was still allowed to veto that structure. The model returned `PREDICATIVE`, so `Крипл` survived as the malformed predicate `криплый`, the primary nominal frame never existed, and the coordinated clause fell back to `SUBJECT=этим`, `STATE=одновременно`. The later semantic projection then projected `ИИ` onto that wrong subject.

## Fix

For an already recognized explicit shell

```text
X — [это] Y
X - [это] Y
X это Y
X — Y
X - Y
```

when `Y` is a nominal head, local subject/predicate direction is owned by deterministic syntax:

```text
SUBJECT = X
PREDICATE = Y
```

An adjective-like or otherwise competing lexical reading of `X` may no longer override this shell. If `X` is a finite overt verb, the nominal-shell rewrite does not silently nominalize it; ordinary predicate parsing keeps ownership. Infinitival nominal subjects remain eligible.

The obsolete `referential_predicative` service prompt is removed. This reduces semantic work and restores the intended deterministic-first boundary.

## Effect on coordinated copulas

Once the primary frame is guaranteed to exist, the existing coordinated nominal logic owns the second half:

```text
Крипл - это название моего проекта
и одновременно с этим это имя моего ИИ
```

becomes the explicit frames

```text
название(SUBJECT=Крипл, OBJECT=моего проекта)
имя(SUBJECT=Крипл, OBJECT=моего ИИ)
```

`одновременно с этим это` remains structural linker material, not semantic actants. The shared subject has the original source evidence span `0:5`, so later semantic projections also use `Крипл` rather than the pronoun `этим`:

```text
проект(SUBJECT=Крипл)
ИИ(SUBJECT=Крипл)
```

The bounded `nominal_subject_projection` probe remains: it decides only whether one already-present complement noun is licensed as a shorthand semantic projection. It does not decide the copular subject/predicate direction.

## Live-failure regression

A hostile test backend reproduces the exact Qwen vote `PREDICATIVE`. The regression requires that the `referential_predicative` probe is never called and that all four resulting assertions (`название`, `имя`, `проект`, `ИИ`) share `SUBJECT=Крипл` with evidence span `0:5`. It also rejects `этим` and `одновременно` as explicit-frame actants.

## Verification

```text
nominal targeted: 11 passed
full suite:       472 passed + 22 subtests, 0 failed
M2 acceptance:    40/40 PASS
M2 AH size:       153502 UIDs
final Workspace:  248
```
