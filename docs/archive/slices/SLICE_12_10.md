# Slice 12.10

Deterministic shared-actant integrity for coordinated predicates.

- A later finite predicate coordinated by `и/да/или/либо` with a preceding finite predicate in the same clause inherits an already established `SUBJECT` when it has no explicit subject of its own.
- Inheritance uses the existing semantic actant, evidence span and `entity_ref`; it does not rescan the whole clause and does not call the LLM.
- An explicit nominative participant after the coordinator blocks inheritance.
- Composite subjects (`AND/OR` actant composition) are copied as the same structured subject rather than flattened to text.
- Exact source-span identity is strict: conflicting `entity_ref` values for one source occurrence abort parsing instead of being silently tolerated.
- Adaptive probe instructions are now required files. Missing or empty prompt files are configuration errors; there are no hidden hardcoded prompt substitutes.
- Deterministic trace stages no longer depend on LLM prompt instructions.
- Removed unused legacy span-prompt files that were not referenced by the active adaptive parser.

Regression coverage includes the conditional compound consequent where an intermediate noun has both accusative and nominative morphological analyses. The shared subject is still recovered without an extra LLM probe.
