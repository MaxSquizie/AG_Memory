# Slice 12.93 — Narrative identity and asserted non-finite events

## Trigger

The v0.12.92 live document run reached `98/98` paragraph semantic checks with zero runtime errors, but the three literary documents still lost events, identities, and temporal/causal edges. The remaining failures were therefore treated as semantic-structure defects rather than transport/parser stability defects.

## Structural fixes

1. **Sentence-local clause parenting.** Fronted subordinate/compound connectives may only attach to a preceding clause from the same sentence. A previous sentence is no longer accepted as a structural parent merely because it is adjacent in the token stream.
2. **Primary predicate relation anchors.** Marker-derived `CAUSE`/`FOLLOW` links target assertions headed by the actual source predicate heads. Clause-local helper assertions remain valid facts but no longer steal the connective edge.
3. **Fixed-point actor inheritance.** Omitted-clause subject sharing is rerun after non-finite control, and coordinated predicate sharing is rerun after controller resolution. These passes are idempotent because already-filled roles are never overwritten.
4. **Source grammatical number in identity.** `ActantCandidate` carries `grammatical_number = sing|plur|None`; Integration stores it on newly created `M`, and EntityResolver filters lexical-name matches by the known source number. This prevents `матрос` and `матросы` from collapsing solely through lemma normalization. The field does not claim exact real-world cardinality.
5. **Quantified nominal heads.** Case forcing from the semantic role is suppressed for quantified NPs when it would choose a proper-name/nominative homograph over the governed common noun.
6. **PP homograph suppression.** A weak ADJS/predicative reading is not promoted to a predicate when the same source token has an oblique nominal reading inside a locally governed prepositional phrase.

## Ambiguous NP attachment

Russian case syncretism makes dictionary morphology insufficient for forms such as `штукатурки` or `лампы`: the same source form can be GEN.SG or NOM.PL. Python first proves the exact adjacent N+N structural ambiguity and then issues one source-only fixed-choice probe:

`GENITIVE_DEP | SEPARATE | UNCLEAR`

The result is cached per source token pair. No AH state or canonical identity is shown to the model.

Postnominal possessive/anaphoric forms are treated similarly only when both NP-modifier and following-predicate-participant readings remain structurally possible:

`POSSESSOR | SEPARATE_PARTICIPANT | UNCLEAR`

If no following finite transitive predicate can host the anaphor, explicit possessive morphology remains deterministic.

## Non-finite assertion status

A `FrameDependencyKind.NONFINITE` edge says only that an infinitive is structurally dependent on a matrix predicate. It does **not** decide whether the infinitive event is asserted to happen.

Examples:

- `лодка продолжала идти` → `идти` is an asserted event;
- `вода начала просачиваться` → `просачиваться` is asserted;
- `он успел подняться` → `подняться` is asserted;
- `он хотел уйти` → `уйти` is non-asserted content;
- `он попросил друга уйти` → `уйти` is non-asserted content.

After structural orientation, role attachment, and controller resolution have already produced one exact matrix/infinitive pair, a tiny semantic probe returns exactly one of:

`ASSERTED_EVENT | NONASSERTED_CONTENT | UNCLEAR`

`ASSERTED_EVENT` adds the child local ref to a parse-local exemption set so the ordinary proposition-content pass does not mark that child `EMBEDDED`. `NONASSERTED_CONTENT` and `UNCLEAR` retain the conservative existing treatment. Invalid protocol on this optional post-parse enrichment is recorded and omitted; backend/infrastructure failures still propagate. The probe runs with thinking explicitly disabled and never receives AH UIDs, Workspace, proof state, or canonical candidates.

## Acceptance/oracle changes

Document participant expectations can now constrain `grammatical_number` in addition to canonical name and structured NP relations. Literary oracle entries for plural letters, sailors, boats, and journals were normalized to canonical singular lemma + plural grammatical number rather than opaque inflected strings.

## Regression

- `560 passed`
- `22 subtests passed`
- `python -m compileall -q src tests` → OK

The next live `Document acceptance` should therefore measure remaining literary event/causal semantics rather than the runtime failures already eliminated in v0.12.92.
