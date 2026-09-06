# AG Memory v0.25.7

Capability slice: coordinated ellipsis / discourse frame completion.

Implemented:

- runtime ellipsis clause detection for comma+coordinator zero-predicate tails;
- `EllipsisKind.FRAME`;
- `EllipsisKind.PROPOSITION_NEGATION`;
- `EllipsisKind.PROPOSITION_CONFIRMATION`;
- removal of proposition-level `нет` from the ordinary predicate work queue after structural ellipsis licensing;
- role-whitelisted target actant extraction against the antecedent frame;
- inheritance of only genuinely omitted antecedent roles;
- deterministic `ellipsis_recovery` trace;
- normative Lexical Recovery section in the main v4 architecture: Levenshtein + embeddings + morphology, without direct AH writes.

Regression: 746 passed, 38 subtests passed.
