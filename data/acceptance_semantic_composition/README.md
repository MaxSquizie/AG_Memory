# Semantic composition acceptance

This corpus is the executable oracle boundary for stream A.  Cases are added by
roadmap step before production code is changed.  The first slice covers temporal
`NEVER` as a source-semantic operator:

```text
NOT(EXISTS $t: AND(P@$t, RELEVANT_PAST($t, anchor)))
```

`NEVER` is not ordinary predicate negation.  The source timestamp/context anchor
and the `RELEVANT_PAST` restriction remain explicit.  Absence of a past occurrence
is `UNKNOWN`; only an asserted `NEVER` formula is negative evidence for the
corresponding existential.

The sentence corpus is oracle data, not a phrase dictionary.  Production code may
use morphology/structure to narrow a candidate and one bounded semantic choice to
classify it, but may not contain these strings or enumerate their paraphrases.

## A2 — proposition query goals

`a2_cases.txt` and `a2_oracle.json` specify read-only OR/XOR expression goals and
compound proposition-valued matrix queries.  The contract distinguishes explicit
falsehood from open-world `UNKNOWN`, requires exact-one XOR semantics, and forbids
query-side canonical writes.

## A3 — recursive orthogonal scopes

`a3_cases.txt` and `a3_oracle.json` specify typed nesting for quantified, modal,
counterfactual, relation and association goals.  Each semantic layer remains
visible in the runtime goal: a modal or counterfactual wrapper must never be
discarded to obtain an ordinary factual `ExistsGoal`.  Compilation and inference
are read-only after Integration has produced the canonical quantified body.

## A4 — correlated semantic alternatives

`a4_cases.txt` and `a4_oracle.json` specify ambiguity over complete proposition
variants, including multi-role correlations and alternatives nested below logical
or matrix scopes.  Canonical ambiguity groups contain whole `N/G` readings, never
independent per-role groups whose Cartesian product could invent unattested
SUBJECT/OBJECT pairs.  Clarification selects and validates one complete reading in
an atomic mutation while unselected readings remain non-asserted.
