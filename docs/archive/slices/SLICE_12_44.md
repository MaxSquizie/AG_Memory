# Slice v0.12.44 — canonical conditionals and structural clarification

## Baseline

Real v0.12.43 acceptance: `36 PASS / 0 FAIL / 4 GAP`. The remaining gaps are three conditionals and one genuine prepositional attachment ambiguity.

## Canonical CONDITION

Conditional branch assertions are integrated as canonical scoped propositions (`N.meta.semantic_scope = CONDITIONAL`). Scope is part of the N signature and ordinary `EXISTS` / `ROLE_FILL` ignores these N.

The dependency itself is represented functionally:

```text
A -> B              => IF(A, B)
A AND B -> C        => IF(AND(A, B), C)
A -> B AND C        => IF(A, AND(B, C))
```

No `L.CONDITION` is introduced because pairwise links would lose conjunctive sufficiency semantics.

## Structural clarification

`Иван увидел Петра с биноклем.` is not guessed. The parser emits two finite structural options. Integration persists an H-only clarification object and the original H experience, while C/P receives no reading. After explicit user choice the original source is reparsed with a program-owned resolution key and the delayed semantic result is attached to the original H event.

Diagnostic no-response turns surface the clarification but do not arm pending dialogue state.

## Oracle

Cases 30–32 now require canonical IF/AND + scoped members. Case 39 now requires successful structural clarification with exact options. There are no deliberate GAP entries left in the current 40-case oracle.

## Safety

- conditional branch existence does not imply branch truth;
- structural ambiguity cannot write a guessed C/P interpretation;
- clarification replay uses normal TemplateCandidate validation and canonical Integration;
- no new opaque natural-language `L.ID` is introduced.
