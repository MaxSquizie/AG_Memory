# Slice 0.12.98 — Factivity and active-history discourse relations

## Live baseline

The v0.12.97 document run (`20260824_032516_+0300`) is transport/runtime clean:

- document pass: 4/6;
- paragraph semantic: 98/98;
- runtime errors: 0;
- cooling station: 18/18;
- greenhouse control: 18/18;
- archive leak: 19/19;
- house by pier: 56/56;
- Belyaev: 26/36;
- old observatory: 59/61.

The residual failures are not independent parser misses. They collapse to four mechanisms.

## 1. Factive proposition content

The Belyaev turn with `Зурита увидел, что ... приближалась подводная лодка` already had the correct proposition-valued actant:

```text
N_SEE
├── SUBJECT -> Зурита
└── OBJECT  -> N_APPROACH

N_APPROACH
└── SUBJECT -> лодка
```

The child `N_APPROACH`, however, was conservatively scoped `EMBEDDED`. That is correct for generic proposition content but wrong for a factive matrix use. Because Integration intentionally does not materialize ordinary nominal relations for scoped propositions, the already parsed `лодка --NOMINAL_MODIFIER--> подводный` never reached canonical AH. This caused the oracle's submarine-approach fact to fail and cascaded into the SEE and CONTINUE checks.

v0.12.98 keeps `_mark_embedded_statuses` conservative and adds a separate factivity boundary. Python first narrows the problem to an asserted matrix OBJECT that explicitly references one subordinate proposition candidate. A tiny semantic probe returns only:

```text
FACTIVE
NONFACTIVE
UNCLEAR
```

Only `FACTIVE` promotes the child (and its equivalent local alternatives) back to `ASSERTED`. The model sees source-local event text only; it never sees or selects canonical UIDs. `NONFACTIVE` and `UNCLEAR` fail closed. This keeps `сказал/думал/надеялся, что P` scoped while allowing factive perception/discovery uses to become ordinary world content.

## 2. PP morphology must be decided from the nominal head

The old-observatory turn

```text
За окнами усиливался ветер; рама в дальней комнате то дрожала, то снова замирала.
Поскольку защёлка давно не держалась в пазу, очередной порыв распахнул створку.
```

was entirely semantically rolled back because the attachment resolver treated `в дальней комнате` as potentially instrumental. The reason was morphological: the adjective `дальней` exposes several equal case readings, one of them ablative, while the rightmost nominal head `комнате` is strongly locative. The old test effectively asked whether *any* token after the preposition had an ablative reading.

The resolver now derives PP case from the coherent nominal head: rightmost NOUN/NPRO first, adjective/participle only as fallback. A case is accepted when the material readings agree, or when one reading clearly dominates. Hard instrumental attachment is considered only when that head case is ablative; pre-predicate location normalization accepts locative head case. The genuine `с биноклем` ambiguity remains untouched and still requests clarification.

## 3. Local narrative causality is not strict logical entailment

The deterministic local review gate already correctly opened a semantic review for:

```text
Матрос ухватил его за ногу,
но Зурита ... ударил его по голове,
и оглушенный матрос упал на палубу.
```

The failure was the semantic protocol: it asked whether the second event was strictly *entailed* by the first. The model therefore rejected `ухватил -> ударил` despite the narrative explicitly presenting the latter as Zurita's reaction.

The bounded choice is now:

```text
CAUSAL_RESPONSE
NO_CAUSAL_RESPONSE
UNCLEAR
```

`CAUSAL_RESPONSE` means that B is presented by this narrative as a direct reaction, response, consequence or result triggered by A. Temporal order, topic continuity, participant sharing, and common-sense plausibility are explicitly insufficient. The deterministic eligibility gate itself is unchanged, so this does not open semantic CAUSE probing for arbitrary event sequences.

## 4. Cross-turn discourse relation induction

Five remaining Belyaev expectations require relations whose source and target are in different user turns. Same-sentence candidate refinement cannot create them, and adding an acceptance-specific postprocessor or globally scanning AH would violate the architecture.

v0.12.98 adds `DiscourseRelationRefiner` as a bounded runtime bridge:

```text
current integrated user turn
        ↓
current H experience
        ↓
walk backward through H FOLLOW
only while each prior H event is ACTIVE in Workspace
        ↓
collect only ACTIVE ordinary C/P N content from those H events
        ↓
UID-free deterministic semantic projection
        ↓
small model choices:
  current event -> prior source -> CAUSE/FOLLOW
        ↓
local indexes only
        ↓
IntegrationService.integrate_discourse_relation
        ↓
canonical validated L write
```

Important invariants:

- no global AH scan;
- inactive H history stops traversal;
- prior semantic candidates must themselves be active Workspace events;
- no canonical UID is exposed to the model;
- the model cannot write AH;
- only ordinary asserted C/P hypernodes may be endpoints;
- H dialogue carriers and EMBEDDED/CONDITIONAL/QUOTED content are rejected;
- FOLLOW is cycle-checked before commit;
- one primary incoming discourse relation is considered per current event in one pass;
- the serialization bound is derived from the existing AgentContext token budget and is not a cognitive top-k/reranker.

The semantic selector deliberately prefers an established initiating prior event over a merely more recent incidental intermediate event. This is required for narrative causality such as an earlier attack motivating a later escape or an approaching submarine causing sailors to stop, while the canonical access set remains determined by the active H trajectory.

## Expected effect on the next live run

The deterministic fixes should remove both old-observatory failures and the three cascading submarine fact failures. The revised local causal protocol should recover the sailor-grab -> Zurita-hit relation when the live model follows the new bounded choice. The new discourse path makes the remaining cross-turn Belyaev CAUSE/FOLLOW expectations representable without a global-memory shortcut.

A 6/6 live result is not asserted until the LM Studio model is actually run: the final discourse labels are intentionally semantic model decisions. Any remaining failure will now be attributable to an explicit bounded discourse-probe decision rather than to absence of an architectural cross-turn mechanism.

## Regression

```text
586 passed, 22 subtests passed
compileall OK
```
