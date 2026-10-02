# Slice v0.12.58 — structural ambiguity boundaries

## Why this slice exists

The real v0.12.57 broad200 run completed with runtime `200/200` and raw semantic `178/200`, while the frozen regression40 remained `40/40`. The single-shot `RuntimeRoleCue` boundary therefore removed the earlier role-router instability. The remaining failures clustered around deterministic structure, lexical identity, relative evidence, local provenance, and a small oracle overconstraint rather than around missing word-specific role knowledge.

An oracle audit found eight cases where the evaluator required a noun lemma (`утро`, `вечер`, `дом`) even though the product had preserved the semantically correct source-denoting adverbial/directional filler (`утром`, `вечером`, `домой`). Architecture already defines `normalized_hint` as optional retrieval evidence, not canonical truth. The saved v0.12.57 runtime bundle therefore regrades to `186/200` under `broad200-v3`. This is an evaluator correction only; it is not a v0.12.58 runtime score.

## Production changes

### Structural case ambiguity stays ambiguous

Material case syncretism is no longer resolved by ordered case checks. Pure ACC and pure DAT remain deterministic evidence, but ACC+DAT keeps `{OBJECT, RECIPIENT}` for the existing one-shot role cue. Likewise, a postverbal NOM+ACC nominal under a stably transitive predicate is not treated as an unambiguous subject. Preverbal subjects and intransitive postverbal nominatives remain available.

### Coordination and NP span construction

OR coordination receives the same direct-object-region treatment as AND when an already available subject and postverbal coordinated nominals make that structure formal. NP-internal genitive growth is conservative: a following nominal is absorbed only when its materially possible core-case readings are genitive-only. A competing DAT/ACC reading keeps the spans separate.

### Relative clauses reuse the ordinary role boundary

Relative antecedent search now consumes only materially structural nominal readings, so tiny unrelated NOUN homonyms of a PREP cannot become an antecedent. When a relative form is governed by a preposition, the role evidence contains the full PP and bypasses the bare-case shortcut. The remaining relation is resolved through the same admissible one-shot `RuntimeRoleCue` used by ordinary actants.

### Symmetric lexical hypothesis verification

Two materially plausible lexical identities are no longer compared as position-sensitive A/B candidates. Each candidate is independently tested with the same `YES/NO` hypothesis question and its morphology profile. Exactly one `YES` is required. `YES/YES`, `NO/NO`, malformed output, or more than two unresolved lexical identities fail closed. Analyzer probability and candidate order never become the contextual winner.

### Quantity normalization is downstream of semantics

A neighboring numeral is fused into a duration filler only after the nominal head has already been semantically classified as `DURATION`. This yields one source filler such as `два часа` without a unit lexicon. A counted entity remains `OBJECT + AMOUNT`; the normalizer cannot infer DURATION from the surface form.

### Personalized nested propositions

Before dependency-ordered Integration, direct SELF/USER deixis seeds P provenance and that requirement propagates only through the turn-local `candidate_ref` containment graph. This prevents a nested proposition from being integrated into C merely because the child must be built before its personalized parent. Non-deictic local parent/child structures remain C.

### Substantivized anaphors

Morphology-marked substantivized anaphors are nominal-like for structural role recovery. If deterministic compatibility leaves several earlier source mentions, a bounded probe may choose only a temporary source label `C1..Cn` or `UNCLEAR`. No UID/entity ref is exposed to the model; `UNCLEAR` preserves normal runtime ambiguity for Integration.

### Conditional consequent scope

For a fronted conditional, contiguous same-sentence top-level siblings explicitly introduced by additive `и/да` remain inside the consequent. OR/adversative siblings are deliberately not absorbed into an implicit AND.

## Acceptance oracle v3

`data/acceptance_oracle.json` is now `broad200-v3`. Only eight expected filler values changed to accept their actual source-denoting adverbial/directional forms. Case texts, predicates, roles, domains, scenario boundaries, and frozen regression40 expectations are unchanged.

## Deliberately not done

- No lexical list for `утром`, `вазу`, `Анне`, `ключом`, `стоит`, or any other broad200 sentence.
- No `preposition -> ActantRole` table added.
- No hidden lexical scorer/tournament added.
- No change to canonical UID/T/N ownership: the model still cannot write AH directly.
- No claimed real v0.12.58 broad200 score before a fresh local-model run.
