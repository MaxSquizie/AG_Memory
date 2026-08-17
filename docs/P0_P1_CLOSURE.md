# P0/P1 architecture closure

Status: closed for the audited P0/P1 list derived from the v0.12.59/v0.18 review.
Architecture reference: `docs/reference/Архитектура_v3.md` v0.23.

## Closed P0

1. Homograph-safe S boundary: one surface form may index multiple S nodes; Text Sensory does not choose lexical identity by morphology score.
2. Embedded propositions are nonasserted by default and materialize with scoped canonical N/g content.
3. Runtime `PropositionExprCandidate` preserves REF/AND/OR/FALSE and conditional Boolean composition.
4. Surface subordinators create structural edges only; semantic parent-child relation is decided after frames exist.
5. Compound embedded content attaches as one proposition expression rather than `children[0]`.
6. Parser resource caps fail closed when meaningful predicate or actant candidates remain.

## Closed P1

- semantic-role boundary (`SUBJECT` is actor/holder/experiencer, not grammatical NOM; surface/case/preposition shortcuts removed);
- dependency-oriented `ClauseFrameGraph`, clause-local speech act, fronted nonfinite orientation and nominal zero copula;
- generic predicate coordination groups and shared-actant transfer;
- generic modifier attachment ambiguity, relative antecedent candidates and stronger NP/PP chunking;
- multi-WH query goals, negative commands, quotation scope/nonasserted reported content;
- lexical-sense T selection with UID-free local choices and no likelihood scorer as semantic voter;
- relative-adverb surface ambiguity is resolved by a bounded `RELATIVE/SUBORDINATE` decision before antecedent binding;
- public `PerceptionResult` act order is source-stable even when parsing uses dependency/topological scheduling internally.

## Verification

- Production Python modules compiled: 79.
- Full test suite: `318 passed, 4 subtests passed`.
- Real-model broad200 was not run in the build environment because the configured local Windows model directory is not present. No acceptance score is claimed for this slice.
