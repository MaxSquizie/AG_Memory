# Slice v0.12.90 — Structural nominal relations in canonical AH

## Why this slice exists

v0.12.89 stopped treating postnominal possessives as a fake extra actant, but that only fixed the *perception boundary*. A phrase such as:

```text
торжество его было недолгим
```

could still become one opaque semantic entity named `торжество его`. That hides the owner relation inside a string and makes later recall/inference over the head entity impossible.

The same problem affects broader Russian NPs:

```text
мой проект
дверь здания
машина инженера
книга брата
дверь дома брата
```

The fix must preserve source structure without guessing semantics that the grammar itself does not prove.

## 1. Runtime NP decomposition

Perception now attaches runtime-only `NominalRelationCandidate` objects to an `ActantCandidate`.

Two relation kinds are intentionally distinguished:

```text
POSSESSOR
GENITIVE_DEP
```

`POSSESSOR` requires explicit possessive morphology/anaphoric structure. `GENITIVE_DEP` is weaker: it records a grammatical post-head genitive dependency without claiming that it means ownership, part-of, content, material, source, etc.

The actant keeps the full source mention as evidence but resolves its identity from the nominal head:

```text
mention = "торжество его"
normalized_hint = "торжество"
internal = POSSESSOR(head="торжество", dependent="его")
```

Therefore the main assertion uses `M_торжество`, not `M_"торжество его"`.

## 2. Canonical representation

For ordinary asserted content Integration materializes the internal structure as typed canonical `L` edges:

```text
HEAD --POSSESSOR--> OWNER
HEAD --GENITIVE_DEP--> DEPENDENT
```

Examples:

```text
торжество его
M_торжество --POSSESSOR--> M_Зурита

дверь здания
M_дверь --GENITIVE_DEP--> M_здание
```

The second edge deliberately remains grammatical/underspecified. `дверь здания` is not silently rewritten as ownership, and `стакан воды` would not be forced into the same world relation as `книга брата` merely because both use genitive morphology.

`L` is appropriate here because these are program-defined structural relation IDs, not new natural-language predicates. No LLM chooses canonical UID or writes the relation directly.

## 3. Nested genitive chains

A sequence such as:

```text
дверь дома брата
```

is preserved as a chain rather than flattened:

```text
M_дверь --GENITIVE_DEP--> M_дом
M_дом   --GENITIVE_DEP--> M_брат
```

The same internal entity is reused between adjacent steps.

## 4. Possessive coreference

Third-person possessives inside an NP are not standalone actants, so ordinary actant coreference never sees them. A dedicated deterministic pass now binds an internal possessor only when one structurally compatible prior discourse entity remains.

```text
Зурита стоял ... Торжество его было недолгим.
```

can therefore preserve the same turn-local source identity for `Зурита` and `его` without asking the LLM to choose a canonical entity.

If several compatible antecedents remain, no guess is made. Cross-turn resolution can still use `InteractionContext`.

First/second-person possessive paradigms (`моего`, `моей`, `твоего`, etc.) are also complete in the deixis resolver, so explicit possessive dependents can point to USER/SELF directly.

## 5. Scope safety

NP-internal links are materialized only for ordinary asserted content.

They are not leaked from:

```text
EMBEDDED
QUOTED
CONDITIONAL
NEGATED
```

This prevents a sentence such as `это не его дом` or an embedded/quoted proposition from asserting a world-level possession merely because the nominal phrase was parsed.

## 6. Projection and weight

`SemanticProjector` renders the new link types deterministically:

```text
POSSESSOR(head=..., owner=...)
GENITIVE_DEP(head=..., dependent=...)
```

The initial structural link weight is configurable as:

```toml
integration.nominal_relation_link_weight = 0.20
```

As with all AH weights, this is propagation strength, not truth/confidence.

## Regression

New general tests cover:

- postnominal possession without an opaque phrase entity;
- generic genitive dependency without false ownership;
- nested genitive chains;
- canonical materialization of `POSSESSOR` and `GENITIVE_DEP`;
- no possession leakage from a negated assertion;
- turn-local third-person possessor reuse;
- first-person possessive deixis.

Full suite:

```text
537 passed, 22 subtests passed
compileall OK
```
