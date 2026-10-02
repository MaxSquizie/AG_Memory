# Slice v0.12.54 — neutral role partitions + contextual lexical identity

## Real input that motivated the slice

The isolated broad200 run on v0.12.53 completed with:

- runtime: 195 OK / 5 ERROR;
- semantic: 158 PASS / 42 FAIL / 0 GAP;
- frozen regression40: 40/40 PASS.

The run demonstrated two general failure modes.  First, role probes returned semantic family labels whose ordinary linguistic interpretation was broader than the internal partition.  A concrete instrument could therefore be classified as an "entity relation", while a temporal expression could be called a "circumstantial modifier" even though the hidden branch used that label only for CAUSE/PURPOSE/TOOL/MATERIAL/HOW_TO.  Second, dictionary morphology sometimes preserved two material lexemes and downstream code consumed a context-free winner or failed before context could resolve the lexical item.

## Production change

### 1. Neutral A/B role partition protocol

Every role-router model call now answers only `A` or `B`.  Neither protocol label carries semantic meaning.  The prompt exposes the natural-language descriptions of the concrete canonical role candidates in each branch, after intersection with the current admissible set.

```text
deterministic admissible roles
        ↓
OPTION A: meanings of subset A
OPTION B: meanings of subset B
        ↓
LLM: A | B
        ↓
Python intersection only
```

The model never returns an AH role name and cannot reintroduce an excluded role.

### 2. Contextual lexical identity before morphology consumption

When one selected nominal token has exactly two materially plausible dictionary lexemes, Perception asks one independent lexical question:

```text
TEXT + TARGET + candidate lemma A + candidate lemma B
→ A | B
```

The chosen lemma filters the token's morphology readings for the rest of the parse.  It does not create an entity, role, template or UID.  Predicate homographs use the same boundary.  More-than-binary lexical ambiguity is unresolved and fails closed.

## Explicit non-goals

- no word-specific broad200 fixes;
- no corpus/oracle changes;
- no direct LLM canonical write;
- no reintroduction of role multi-choice scorer/margin;
- no claim that all older deterministic role heuristics have been audited in this slice.
