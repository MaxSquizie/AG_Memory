# Slice 12.9

Conditional-clause semantics and conservative cross-clause coreference.

- `если` is normalized by linguistic preprocessing to a `CONDITION` clause relation.
- Fronted subordinate clauses (`если A, B`, and the same generic mechanism for TIME/CAUSE/PURPOSE) are attached to the following matrix clause instead of requiring the parent to appear first.
- `PerceptionResult.conditionals` stores runtime `ConditionalCandidate` objects with antecedent/consequent local situation refs.
- Situation candidates participating in a conditional are marked `AssertionStatus.CONDITIONAL`.
- Integration deliberately does **not** commit conditional branches as ordinary C/P/H world facts. The source utterance is still recorded as an H experience. Canonical conditional inference/materialization remains a separate future feature.
- Third-person pronouns are coreferenced deterministically only when morphology leaves exactly one compatible prior entity in the strongest syntactic pool. Ambiguous cases are left unresolved rather than guessed.
- Fixed omitted-subject inheritance so it does not allocate a fake entity identity when the child clause already has an explicit subject.
- GUI decoded JSON renders enum values directly (`CONDITIONAL`) instead of Python enum repr strings.
- Added regression coverage for fronted and postposed conditional clauses, pronoun identity, omitted-subject inheritance, and non-commitment of conditional propositions.
