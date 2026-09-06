# Slice 12.92 — Structured NP / discourse-control reliability

## Live evidence

The v0.12.91 document run finished with 3/6 documents, 97/98 paragraph semantic checks and one runtime error. The three technical documents remained fully green. The only runtime error was the Belyaev sentence `Но торжество его было недолгим.`; the recorded morphology showed that current pymorphy represents the possessive-adjective reading of `его` as `ADJF + Apro + Anph + Fixd`, while the old detector and its static regression used `Subx`.

The same run also showed that many literary graph misses were not missing predicates. Canonical M identity was still the whole descriptive NP (`Сухая ветка`, `ржавую калитку`, `керосиновую лампу`, etc.). A separate failure class came from coreference compatibility being checked against a singular canonical lemma instead of the inflected source mention (`письма` -> `письмо`, then plural `их` was rejected locally). Gerund frames also frequently contained a correct event but no copied matrix SUBJECT.

## Changes

### 1. Morphology-compatible postnominal possessors

`_is_postnominal_possessive_anaphor` accepts either explicit morphology encoding:

- `ADJF + Anph + Subx`; or
- `ADJF + Apro + Anph + Fixd`.

The rule remains position-sensitive. It does not convert an arbitrary NPRO surface to possession and does not change the conservative pre-head participant boundary.

### 2. NOMINAL_MODIFIER

`NominalRelationKind.NOMINAL_MODIFIER` records ordinary attributive adjective/participle/number structure. Once an NP contains source-grounded internal structure, the main actant lookup identity follows the substantive head.

Examples:

```text
Сухая ветка
M(ветка) --NOMINAL_MODIFIER--> M(сухой)

нижний ящик письменного стола
M(ящик) --NOMINAL_MODIFIER--> M(нижний)
M(ящик) --GENITIVE_DEP-----> M(стол)
M(стол)  --NOMINAL_MODIFIER--> M(письменный)
```

`NOMINAL_MODIFIER` is deliberately weaker than a semantic state/material/event relation. It records source structure only. Like the other nominal relations, it is materialized only for asserted world content; negated/quoted/embedded/conditional scope cannot leak the link into the world graph.

### 3. Surface-first grammatical compatibility

Local pronoun and NP-internal possessor coreference use morphology of the source nominal head first, with canonical `normalized_hint` only as fallback. Role-compatible case narrowing is applied to that source form. This prevents entity lookup lemmatization from erasing grammatical number before coreference.

### 4. GRND subject control

A `NONFINITE` dependency whose child token has GRND morphology inherits the unique matrix SUBJECT if the child has no explicit SUBJECT. This is deterministic Russian grammar. INFN children are excluded because infinitival control is not generally identical to matrix-subject control.

### 5. Recency-based discourse salience

Cross-turn `pronoun_refs` are refreshed from the latest source-grounded SUBJECT position for each number/gender signature. Only a unique canonical M at the latest position becomes the runtime anchor. Distinct refs tied at that latest position clear the anchor. No canonical memory fact is written by this mechanism.

### 6. Structured document oracle

A role expectation can now specify a canonical head plus required outgoing structural relations:

```json
{
  "canonical_name": "стекло",
  "relations": [
    {"relation": "GENITIVE_DEP", "target": "лампа"}
  ]
}
```

The hand-written literary oracle was adjusted only where the previous expectation required an opaque NP string that the canonical architecture no longer stores (`кусок штукатурки`, `падение штукатурки`, `стекло лампы`, `подводная лодка`).

## Deliberately not solved here

This slice does not claim general instance individuation or plural/group semantics. Two distinct physical objects described by the same nominal head still require a stronger identity mechanism than lexical M-name lookup. Likewise no `CAUSAL_CANDIDATE -> CAUSE` promotion was added; literary causal induction remains a separate M2-facing task.

## Regression

- 8 focused v0.12.92 tests cover live pymorphy possessive signatures, head normalization, nested modifiers, canonical modifier L materialization, plural-source pronoun compatibility, gerund subject control, recency salience, and structured oracle matching.
- Full suite: 549 passed + 22 subtests.
- `python -m compileall -q src tests`: OK.
