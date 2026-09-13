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
