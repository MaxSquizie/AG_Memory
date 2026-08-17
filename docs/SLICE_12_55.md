# Slice v0.12.55 — relation contracts + lexical-decision monotonicity

## Real input to the slice

The v0.12.54 real-model broad200 run completed with:

- runtime: 198 OK / 2 ERROR;
- semantic: 159 PASS / 41 FAIL / 0 GAP;
- frozen regression40: 40/40.

The lexical-identity boundary removed several predicate-homograph runtime failures, but the largest adjunct-role cluster remained.  Raw traces showed a systematic issue rather than missing vocabulary: short role glosses allowed neighboring canonical roles to overlap in ordinary interpretation.  For example, an object "used" in an event could satisfy the old MATERIAL wording even when it was actually a separate TOOL.

## Production change

### 1. Event-relative role contracts

Binary protocol labels remain only `A` / `B`.  Each displayed candidate meaning now states what `TARGET` does in the current event and, where necessary, what nearby meaning it excludes.  No new intermediate ontology or Russian word table is introduced.

### 2. Negative POS evidence only

If every materially possible reading of a selected span is `ADVB`, nominal participant roles and physical TOOL/MATERIAL are formally impossible and may be removed before the semantic probe.  The parser does **not** infer TIME, LOCATION, HOW-TO, CAUSE, etc. from ADVB itself.

### 3. Lexeme probes receive morphology evidence

A/B lexical candidates are accompanied by analyser facts already present for the observed surface form: POS, case, number, gender, and a small set of grammeme markers such as `passive`, `indeclinable`, `personal-name`, `abbreviation`, or `qualitative`.  The probe still decides lexical identity only.

### 4. Accepted lexical identity is monotonic

After `_contextualize_nominal_span()` selects a lemma, `_semantic_actant_text()` reuses that selection for `normalized_hint`.  It no longer calls a second independent normal-form chooser that can overturn the accepted lexical decision.

### 5. Fail-safe structural repairs

Finite SUBJECT agreement is applied to pre-predicate nominative candidates without breaking plural AND-coordination.  Relative antecedent matching treats a missing normalized hint as absence of optional evidence and falls back to source mention instead of throwing `AttributeError`.

## Explicit non-goals

- no sentence-specific rules for broad200 words;
- no temporal word list;
- no duration-unit list;
- no new case/preposition-to-role table;
- no change to the broad200 oracle;
- no claim of a new real acceptance score until the same suite is rerun.
