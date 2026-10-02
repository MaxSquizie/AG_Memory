# v0.12.75 — nominal predicate family probe

## Live failure addressed

The real v0.12.74 Qwen trace parsed both explicit nominal frames correctly but the
`nominal_projection_relation` probe disagreed across two semantically parallel
clauses:

```text
Крипл — название моего проекта -> LABELS_COMPLEMENT
Крипл — имя моего ИИ           -> OTHER_RELATION
```

That probe still asked the model to reason about the whole SUBJECT↔complement
relation and was therefore larger than necessary.

## Change

The projection decision is narrowed one step earlier.  After deterministic syntax
has already selected the nominal predicate and its SUBJECT/complements, the model
now classifies only the **sense family of the selected nominal predicate**:

```text
LABEL_IDENTIFIER
OTHER_NOMINAL
UNCLEAR
```

`LABEL_IDENTIFIER` means that the predicate itself is used in the local clause in
a name/title/label/identifier/designation/alias sense.  Python then deterministically
projects the single noun concept from the complement; if several nouns remain, the
existing bounded target-selection probe is used.

There is no lexical marker table and no NAME/DENOTES ontology.  The LLM does not
choose the final projected assertion and does not see proof state.  `столица` remains
`OTHER_NOMINAL`, so `Москва — столица России` cannot create `Россия(Москва)`.

The obsolete `nominal_projection_relation.txt` prompt is removed and replaced by
`nominal_predicate_family.txt`.

## Verification

```text
nominal targeted: 13 passed
full suite:       474 passed + 22 subtests, 0 failed
M2 acceptance:    40/40 PASS
M2 AH size:       153502 UIDs
final Workspace:  248
```
