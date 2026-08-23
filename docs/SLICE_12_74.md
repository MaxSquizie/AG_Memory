# v0.12.74 — Nominal projection asks the relation, not the answer

The live v0.12.73 trace parsed the two explicit frames correctly:

```text
название(SUBJECT=Крипл, OBJECT=моего проекта)
имя(SUBJECT=Крипл, OBJECT=моего ИИ)
```

but the old `nominal_subject_projection` probe then asked whether the complement noun was a "shorthand semantic class/identity" of SUBJECT.  Qwen answered `NONE` for `проект` while accepting `ИИ`, so only `ИИ(Крипл)` was materialized.  The syntax was correct; the semantic probe was asking an unnecessarily indirect question.

## Fix

Projection is now split into the minimum semantic work needed after deterministic nominal-frame parsing.

1. `nominal_projection_relation` classifies only the relation expressed by the already-built nominal frame:
   - `LABELS_COMPLEMENT` — SUBJECT is the name/title/label/identifier/designation of the thing described by a complement;
   - `OTHER_RELATION` — any other nominal relation;
   - `UNCLEAR` — fail closed.
2. If the frame is `LABELS_COMPLEMENT` and exactly one noun concept occurs in its complements, that concept is selected deterministically.
3. Only if several noun concepts remain does `nominal_projection_target` choose one supplied candidate or `NONE`.

No predicate word table is used.  `название`/`имя` must be classified from the clause semantics; `Москва — столица России` is the same code path and must classify as `OTHER_RELATION`, preventing `Россия(Москва)`.

For the Kripl regression the intended result is again:

```text
название(Крипл, моего проекта)
имя(Крипл, моего ИИ)
проект(Крипл)
ИИ(Крипл)
```

The obsolete `nominal_subject_projection.txt` service prompt is removed.

## Verification

```text
nominal targeted: 12 passed
full suite:       473 passed + 22 subtests, 0 failed
M2 acceptance:    40/40 PASS
M2 AH size:       153502 UIDs
final Workspace:  248
```
