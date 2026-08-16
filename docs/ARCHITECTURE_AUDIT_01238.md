# Architecture audit — v0.12.38

Status: revision baseline. This document does **not** silently replace `docs/reference/Архитектура_v3.md`. It records where the current implementation is aligned, where it accumulated experimental machinery, and which deferred mechanisms now appear necessary for the stated correctness target.

**Follow-up:** v0.12.39 implements the controlled monotonic T evolution proposed by this audit and removes one-shot hidden template-role prediction from the production critical path. The rest of this document remains the v0.12.38 baseline.

Target: semantic correctness, not “no exception”. A run is acceptable only when its canonical meaning matches the curated oracle or when the architecture explicitly marks the case as unresolved. `ARCHITECTURE_GAP` is not PASS.

## Executive result

The v0.12.37 parser is safe at the canonical write boundary, but its current template strategy is structurally incompatible with open-ended natural language:

```text
first occurrence
→ guess a complete T once
→ freeze T forever
```

A later explicit role then fails if that one-shot guess omitted it. Hidden-valency LLM probes were introduced to compensate for this, but they cannot guarantee a complete future role schema and therefore should not own an irreversible canonical decision.

The revision direction is:

```text
explicit observed/requested role evidence
→ deterministic monotonic T role expansion

NOT

first occurrence
→ speculative hidden-role prediction
→ permanent T
```

This requires lifting `[DEFER] T valency evolution` for the MVP. `[DEFER]` is treated as “not required by default”, not as a prohibition when correctness requires the mechanism.

## KEEP

### Canonical write boundary

Architecture §§7–8, 23: LLM perception proposes runtime candidates; deterministic Integration owns canonical UID, validation and AH mutation.

Current implementation preserves this boundary. Keep it.

### Atomic Integration / fail-closed

Malformed/ambiguous semantic decisions do not partially mutate C/P. External user turns still become H experience. This has repeatedly prevented hidden-valency experiments from polluting canonical memory.

Keep it.

### `s != m`, source-language lexical S

Current morphology normalization extends `R_text` on one lexical `S` without introducing a second lemma field. This matches Architecture §§3.2 and 8.

Keep it.

### Runtime alternatives + canonical entity ambiguity

The `Анна увидела Марию. Она улыбнулась.` path preserves alternative referents, creates canonical `k_AMBIGUOUS`, and produces an explicit clarification request. This matches Architecture §§3.11, 7.5, 8.3 and 8.4.

Keep it.

### H-only experience for every user turn

Parse/integration failure does not erase the experienced communication. This matches Architecture §§4–5 and 21.

Keep it.

### Conditional fail-safe

Conditional branches are currently prevented from leaking into C/P as unconditional facts. The representation is incomplete, but this safety property is correct and must remain while canonical conditional semantics are designed.

Keep temporarily; see ARCHITECTURE GAP.

## REMOVE FROM THE PRODUCTION CRITICAL PATH

### One-shot hidden template valency discovery

Current `AdaptivePerceptionParser.propose_template_candidate()` guesses unfilled SUBJECT/OBJECT and then RECIPIENT/SOURCE before canonical T creation.

This mechanism exists because `TemplateResolver` freezes the first T. It is not a scalable correctness mechanism:

- a future sentence may expose a legitimate role never seen in the first occurrence;
- the full role inventory cannot be inferred with certainty from one sentence;
- a false negative permanently blocks later explicit syntax;
- a false positive silently pollutes the reusable predicate schema;
- directional binary probes are only a small subset of the possible role inventory.

Once controlled T evolution exists, hidden role guessing is not required for correctness. Keep the v0.12.37 preflight only as a diagnostic/model capability tool if useful; remove hidden valency from production TemplateCandidate construction.

The same argument applies to hidden SUBJECT and hidden OBJECT prediction. An unfilled reusable role can be learned later from explicit assertion/query syntax. The only reason to guess it in advance was immutable T.

## UNDEFER / IMPLEMENT

### Controlled monotonic T valency evolution

Architecture §33 currently lists `T valency evolution` as `[DEFER]`. For open-ended text this is now necessary.

Required invariant:

```text
Roles(T_old) ⊆ Roles(T_new)
```

Expansion is allowed only from validated **explicit semantic evidence** already present in `PerceptionResult`:

- an assertion fills a role not yet present in T;
- a query explicitly requests a role or supplies it;
- a command explicitly supplies it.

No LLM is allowed to mutate T merely by speculating that an absent role might exist.

Old N remain valid because Architecture §3.6 already states that not every T role must be filled in a concrete N.

This is therefore a natural monotonic operation:

```text
T(SUBJECT, OBJECT)
+ later explicit RECIPIENT
→ T(SUBJECT, OBJECT, RECIPIENT)

existing N(SUBJECT, OBJECT)
remains valid with RECIPIENT unfilled
```

This directly removes the failure cascade observed for `подарить` and `сказать` without requiring an infallible hidden-valency model.

### Query role evidence must participate in T evolution

A query such as `Кому Иван подарил книгу?` explicitly demonstrates that the user is addressing a RECIPIENT position of the predicate. The requested role is schema evidence but not factual evidence of a value.

It may expand T; it must not create a filled N role.

## SIMPLIFY / CORRECT

### Control/complement semantics: OBJECT vs PURPOSE

Architecture §3.7 explicitly permits `N` to be an actant of another `N`, and gives `SAY(OBJECT -> N_MOVE)` as the canonical nested-fact example.

Current parser overloads PURPOSE for control/content complements:

```text
Мария хочет купить билет
попросить ... войти
```

That is not the role definition in Architecture §3.6. `PURPOSE` is “goal / intended result / what for”; proposition/content selected by a predicate belongs naturally in `OBJECT`.

For the current oracle:

```text
хотеть:
  SUBJECT = Мария
  OBJECT  = N_BUY

попросить:
  SUBJECT   = Иван
  RECIPIENT = Мария
  OBJECT    = N_READ
```

The controller of the child predicate remains a separate resolution problem.

The current `GOAL_LINK/NOT_GOAL` control-complement machinery should therefore be redesigned rather than tuned around these examples. Explicit purpose connectors (`чтобы`, `для того чтобы`) can still produce PURPOSE.

### Domain routing must preserve personalized provenance

Architecture §4 defines P as the personalized model of the agent and concrete known objects. The current router looks only at domains of already-resolved actants.

This loses provenance when a new C entity is first introduced inside a P assertion and a sibling/relative fact about the same concrete object is integrated next. Example:

```text
Я положил книгу рядом с журналом, который был новым.
```

Current result:

```text
положил(...) -> P
журнал был новым -> C
```

The second fact describes the same concrete object introduced in the user's personalized event and should remain in P unless a stronger semantic rule says otherwise.

Domain routing needs turn-local provenance/context, not only existing canonical entity domain.

## REVIEW, DO NOT REMOVE BLINDLY

### Fixed-choice log-likelihood margins

The scorer/margin layer is currently used in multiple bounded semantic decisions. It is not required by Architecture_v3 and has already shown backend-specific calibration behavior.

Do not delete it solely for aesthetic simplicity. After the semantic oracle is active, measure which oracle failures it prevents/causes. A mechanism stays only if it provides repeatable semantic value across a larger corpus.

### Deterministic coordination/coreference/relative rules

These rules reduce model semantic work and many are currently correct on the oracle. Keep them while they remain local, explainable transformations. Refactor for size/ownership, not behavior, before removing them.

## ARCHITECTURE GAPS

### Canonical conditional propositions

The current runtime `AssertionStatus.CONDITIONAL` prevents false unconditional commits but Architecture_v3 has no canonical representation for a conditional dependency whose branch propositions are not themselves asserted facts.

Simply adding `L:CONDITION` is insufficient if the referenced N become ordinary asserted world facts merely by existing in C/P.

A design decision is required about proposition-vs-assertion status in canonical memory. Until then conditional cases are `ARCHITECTURE_GAP`, not PASS.

### General syntactic ambiguity clarification

Architecture §7.5 permits runtime parse alternatives, but the implemented clarification contract is entity-reference-specific. A genuine attachment ambiguity such as:

```text
Иван увидел Петра с биноклем.
```

currently fails closed with `PerceptionParseError`. This is safe but not a complete product behavior. We need a general clarification/deferred-integration contract for competing semantic parses.

### Lexical polysemy / several T per one S

Architecture does not state `one S = one T`; current store can technically contain several T for one predicate S, while current resolver behaves primarily as one-schema-per-lexeme.

For broad language coverage this must be resolved explicitly. `sense_hint` is runtime-only and there is no canonical sense identity. Role-schema differences may distinguish some senses; same-schema polysemy remains unresolved.

Do not add a hidden sense mechanism until an oracle corpus demonstrates the required distinction, but do not assume one lexical S always has one semantic frame.

## Acceptance audit

v0.12.37 reported:

```text
runtime OK 33/40
runtime ERROR 7/40
```

That number did not measure semantic correctness.

The new curated semantic oracle, applied offline to the same user-provided run, reports:

```text
PASS 27/40
FAIL 9/40
GAP  4/40
```

Known FAIL roots:

```text
15–18  immutable T blocks explicit RECIPIENT for подарить
22     control-complement parse fails
23     хотеть complement represented as PURPOSE instead of nested OBJECT
28     попросить uses OBJECT(person)+PURPOSE(action) instead of RECIPIENT(person)+OBJECT(action)
38     immutable T blocks explicit RECIPIENT for сказать
40     personalized relative fact routed to C instead of P
```

Known GAP:

```text
30–32  conditional semantics are safe but not canonically represented
39     genuine syntactic attachment ambiguity has no general clarification contract
```

This baseline is intentionally harsher than runtime success. It is the measurement we need for `40/40 -> 500/500 -> ... -> 15000/15000`.

## Next implementation order

1. Controlled monotonic T role expansion from explicit assertion/query/command roles.
2. Remove hidden template role prediction from production T creation; keep observed roles only.
3. Re-run semantic oracle. The `подарить/сказать` cascade should disappear without prompt changes.
4. Correct control/complement representation (`OBJECT` nested N, addressee `RECIPIENT`).
5. Correct P provenance routing for turn-local concrete objects.
6. Resolve architecture gaps (conditional canonical semantics, general parse clarification).
7. Expand oracle corpus by semantic families, not by random sentences.
8. Only then use oracle evidence to simplify/remove scorer or other parser machinery.

## Follow-up v0.12.40

The v0.12.39 real semantic run validated controlled T evolution (cases 14–21 all PASS) and exposed three independent legacy mechanisms: binary scorer-margin veto, conflation of selected complement with PURPOSE, and exact-span-only relative identity binding. v0.12.40 removes/narrows those mechanisms rather than adding sentence-specific patches. The four CONDITION/general-attachment architecture gaps remain outside this slice and require explicit canonical/clarification design.

## Follow-up v0.12.41

The real v0.12.40 run (`31 PASS / 6 FAIL / 3 GAP`) showed that one new mechanism was too broad: classifying every animate/pronominal accusative with an early `OBJECT / RECIPIENT` LLM probe increased semantic work and regressed ordinary direct objects. This validates the audit principle that deterministic narrowing must happen before model semantics, not after it.

v0.12.41 therefore moves participant/addressee classification to the point where a nested `OBJECT`-content relation has already been established and creates a real semantic slot conflict. Ordinary accusatives stay deterministic OBJECT candidates.

The same run exposed an Integration-level identity error: lexical same-name lookup could reuse a canonical entity from another domain before personal provenance was applied. Architecture v0.7 now states explicitly that name/alias is retrieval-only. Strong turn-local provenance establishes a provisional lookup domain before lexical entity resolution; otherwise global lookup remains candidate generation and ambiguity stays explicit.

The controller failure also reinforced the exact-protocol rule: bare machine labels belong in `CHOICES`, while human-readable descriptions are separate context. This is protocol hygiene, not prompt tuning.

## Resolution follow-up v0.12.44

The two architecture gaps identified above are now resolved by explicit mechanisms rather than parser exceptions:

- **Conditional propositions:** branch `N` are canonical but scoped (`semantic_scope=CONDITIONAL`), so their existence is proposition content rather than an asserted world fact. `g_IF` binds antecedent/consequent and `g_AND` preserves multi-member branch conjunction. Ordinary `EXISTS/ROLE_FILL` ignores scoped N.
- **General structural clarification:** genuine parse attachment ambiguity becomes H-level pending dialogue state. C/P semantics are withheld until explicit user selection; the selected reading is replayed through normal Perception/Integration and attached to the original H experience.

The real v0.12.43 run immediately preceding this implementation measured `36 PASS / 0 FAIL / 4 GAP`. v0.12.44 changes those four oracle entries from GAP to exact contracts; a fresh real-model run is required before claiming `40/40`.

