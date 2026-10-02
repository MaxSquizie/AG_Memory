# Slice 12.95 — Narrative Graph Refinement

## Why this slice exists

The live v0.12.94 document run was the first clean literary diagnostic after the morphology-boundary fix:

- document pass: `3/6`;
- paragraph semantic: `98/98`;
- runtime errors: `0`;
- `house_by_pier_monolith`: `51/56`;
- `belyaev_amphibian_mutiny`: `25/36`;
- `old_observatory_monolith`: `45/61`.

The remaining red checks were therefore no longer transport failures. Three general mechanisms stood out: compatible re-descriptions could remain duplicate N, narrative causality needed a safe promotion boundary, and a comma-heavy subordinate construction could expose a structured participant in the child event without placing that participant in the matrix event.

## 1. Canonical N enrichment without event guessing

`AHCore.add_or_enrich_hypernode()` extends exact N deduplication with a monotonic unique-match rule. Two descriptions may share one N only when they use the same canonical T and semantic scope, share at least one identical role filler, and contain no conflicting filler. Exactly one compatible existing N must exist.

Example:

```text
N: усилиться(SUBJECT=ветер)
+
усилиться(SUBJECT=ветер, LOCATION=бухта)

=> same N UID
   SUBJECT=ветер
   LOCATION=бухта
```

If both `войти(Иван, дом)` and `войти(Иван, офис)` already exist, a later generic `войти(Иван)` is **not** merged with either one. This is fail-closed event identity, not fuzzy similarity. Template roles may grow monotonically first; enrichment preserves the existing N UID and therefore all existing L endpoints.

Integration uses this operation for canonical assertion writes. Exact duplicates still only increment occurrence metadata.

## 2. Causal candidates stay weak unless a narrow source pattern earns a probe

`EventNormalizer` deliberately keeps broad narrative adjacency as `CAUSAL_CANDIDATE`; adjacency is not truth. An earlier experimental implementation asked the LLM about every candidate and caused an unwanted second semantic pass over ordinary coordination, relative clauses and nominal helper assertions.

v0.12.95 gates the probe structurally. It is eligible only when:

- both endpoints are ordinary ASSERTED, non-negated, non-quoted events;
- both material predicates are event heads, not implicit/nominal helpers;
- both occur in the same non-relative sentence;
- the source OBJECT/RECIPIENT is the target SUBJECT.

Only then does the UID-free bounded probe return one of:

```text
ENTAILED
NOT_ENTAILED
UNCLEAR
```

Only `ENTAILED` materializes a canonical `CAUSE`. All other `CAUSAL_CANDIDATE` hints remain non-canonical. This catches high-information action→reaction structures such as `ударил матроса, и матрос упал` without turning `A happened; B happened` into causal truth or sending every event pair to the model.

The service prompt is intentionally under the existing tiny-probe size guard and thinking is disabled for the probe.

## 3. Structured subordinate participant projection

The v0.12.94 Belyaev trace showed that `подводная лодка` itself was already represented correctly as a structured nominal head plus `NOMINAL_MODIFIER`. The missing oracle fact `Зурита увидел подводную лодку` came from a different boundary:

```text
Зурита увидел,
что к «Медузе»,
разрезая гладь океана,
... приближалась подводная лодка.
```

The clause candidate graph recognized the empty `что ...` subordinate connector under the matrix clause, while the detached parenthetical left the later finite child structurally orphaned. v0.12.95 adds a post-frame refinement for exactly this shape. Python requires one matrix ASSERTED frame with a free OBJECT, one nearest later ASSERTED finite child in the same sentence, and exactly one concrete child SUBJECT. It then asks only:

```text
OBJECT
NO_DIRECT_OBJECT
UNCLEAR
```

If and only if the answer is `OBJECT`, the *same structured ActantCandidate* is copied into the matrix OBJECT role. Nominal relations and source identity therefore survive into EntityResolver/Integration. The child event remains ASSERTED. This is not a lexical `увидеть` rule and does not project every subordinate subject into every matrix predicate.

## 4. Delayed pronoun identity after structural inheritance

A reused source occurrence of `он/она/оно/они` could previously receive a fresh `entity_ref` during exact-span coalescing before a real antecedent had become available through structural inheritance/coordination. That synthetic identity then blocked later coreference.

The binder now leaves an unresolved third-person personal-pronoun span unallocated when every copy is still unresolved. After structural role sharing, coreference runs once more; exact-span coalescing then propagates the established antecedent id. Already-resolved pronouns are unchanged, and morphology defines the grammatical class rather than a sentence-specific name rule.

## Tests

New focused coverage includes:

- unique compatible N enrichment;
- refusal to choose between multiple compatible specific N;
- template valency growth while preserving an existing linked N UID;
- narrow patient→subject causal promotion;
- UNCLEAR causal result remaining non-canonical;
- generic cross-sentence adjacency causing no semantic probe;
- orphan subordinate SUBJECT→matrix OBJECT projection after a bounded probe;
- unresolved repeated personal-pronoun copies waiting for real antecedent binding.

Final local regression:

```text
571 passed
22 subtests passed
compileall OK
```

No document oracle or literary source text was changed in this slice. A live LM Studio document run is still required to measure the actual Qwen3.8 effect.
