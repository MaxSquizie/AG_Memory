# AG Memory v0.25.8

Acceptance-driven hardening of coordinated ellipsis.

Implemented:

- suppress every predicate candidate owned by a structurally licensed ellipsis tail, not only proposition-level `нет`;
- unwrap canonical `NOT(N)` correctly in semantic-oracle predicate/role checks;
- distinguish object-level `NOT` from meta-refutation `FALSE(N)` when grading `negated=true`;
- align overt target fillers to antecedent roles only through unique source-grounded grammatical realization signatures;
- regression coverage for dash ellipsis, canonical NOT and live observed SUBJECT/RECIPIENT swap.

Live v0.25.7 diagnostic that motivated the slice: `11/22` ellipsis PASS, with 4 proposition-negation cases already semantically correct but misgraded by the oracle.

Regression: 749 passed, 38 subtests passed.
