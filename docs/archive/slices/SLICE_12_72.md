# v0.12.72 — Nominal predication, compound copular frames, semantic class projection

This slice fixes the live Perception failure where a referential noun/name at the left side of a Russian nominal copula could be selected as the predicate solely because morphology exposed an adjective-like reading. The concrete failure was `Крипл - это название моего проекта и одновременно с этим это имя моего ИИ`, which became one malformed predicate `криплый(...)`.

## Runtime semantic boundary

Nominal copular shells are recognized structurally before normal predicate scheduling:

- `X — это Y`;
- `X - это Y`;
- `X это Y`;
- `X — Y` / `X - Y` when the dash is punctuation rather than an internal hyphen.

If the left term is already an unambiguous nominative nominal, no model call is required. If morphology also makes the left term a plausible predicate, a bounded UID-free probe chooses only `REFERENTIAL`, `PREDICATIVE`, or `UNCLEAR`. It does not choose a role, entity, relation, or canonical UID.

A resolved nominal complement is promoted to a runtime predicate head. Repeated copular coordination in the same sentence (`... и ... это Z`) creates a peer frame and reuses the already resolved subject. Independent punctuation-bounded sentences are handled independently.

For the live regression the explicit Perception frames are:

```text
название(SUBJECT=Крипл, OBJECT=моего проекта)
имя(SUBJECT=Крипл, OBJECT=моего ИИ)
```

The former malformed roles `TIME=одновременно`, `AUXILLIARY=с этим`, `RECIPIENT=имя`, and `MATERIAL=моего ИИ` no longer occur.

## Bounded nominal subject projection

The explicit frames above still contain useful class content inside their noun complements. A second bounded semantic probe is allowed only after a nominal-predicate frame has already been structurally established. Python enumerates noun concepts already present in non-subject complements and gives the model only local labels plus `NONE`.

The probe answers one narrow question: whether the whole clause also licenses one supplied noun concept as a shorthand semantic class/identity of the subject. It never generates a word, UID, relation ID, or proof path. Deterministic code materializes the selected projection as an ordinary assertion candidate and normal Integration owns canonical S/T/N creation.

For the Kripl sentence this yields two additional semantic facts:

```text
проект(SUBJECT=Крипл)
ИИ(SUBJECT=Крипл)
```

This is not a lexical marker table. The same mechanism receives `Россия` for `Москва — столица России` and must return `NONE`; therefore no false `Россия(Москва)` fact is created. No `NAME` / `DENOTES` AH relation or new ontology is introduced.

## Lexical ambiguity

A promoted noun predicate still obeys the lexical trust boundary. If deterministic morphology leaves several noun lexemes, the existing tiny fixed-choice lexical probes select only among supplied local alternatives. Analyzer order is never used as a semantic voter.

## Canonical Integration and inference regression

The exact compound sentence is tested through Template completion + Integration. It creates four canonical N realizations (`название`, `имя`, `проект`, `ИИ`) sharing one canonical semantic entity for `Крипл`.

End-to-end regression then asks:

```text
Крипл - проект?  -> PROVED
Крипл - ИИ?      -> PROVED
Крипл - человек? -> UNKNOWN
```

The unrelated `человек` predicate is established elsewhere so `UNKNOWN` is a real failed ExistsGoal, not `predicate_not_found`.

Logical truth is still owned by deterministic inference. Arbitrary graph connectedness and Workspace activation are not promoted to proof.

## Verification

```text
nominal v0.12.72 targeted: 10 passed
full unit suite:          471 passed + 22 subtests, 0 failed
M2 operator acceptance:   40/40 PASS
M2 AH size:               153502 UIDs
```
