# Quantifier semantic acceptance

This corpus grades the separate Quantifier Formalization boundary, not a marker-word recognizer.

- 78 independent EXACT cases.
- EXISTS, NOT_EXISTS, FORALL and NOT_FORALL.
- Paraphrases, inflection, partitives, role scope, inversion, predicate-body negation and a fail-closed ambiguous-scope case.
- The perception oracle requires typed `QuantifierCandidate` metadata.
- The integration oracle checks the exact binder spine, `BoundVar`, class restriction and scoped proposition members.

Run it through the ordinary semantic acceptance pipeline with `data/acceptance_quantifiers/cases.txt` and `data/acceptance_quantifiers/oracle.json`.
