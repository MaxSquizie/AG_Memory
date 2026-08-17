# Broad200 2026-08-17 — second real-run fix pass

## Input run

- Runtime completed: **191 / 200**
- Runtime ERROR: **9 / 200**
- Semantic PASS: **71 / 200**
- Semantic FAIL: **129 / 200**
- The supplied post-run AH snapshot contains only SELF/USER and no test C/P/H knowledge, so cross-case AH contamination is not the cause.

The 71/200 score was not treated as 129 independent parser defects. The run was clustered by failing semantic checks and raw probe traces.

## Systemic failures found and fixed

### 1. Actant enumeration was still an LLM stop decision

The dominant failure was `perception_actant_start = 0`: one model STOP could erase every remaining participant of an otherwise structurally valid frame. This produced empty frames such as `читать()` and then cascaded into role-set, template, domain, coreference and inference failures.

Production perception now enumerates the finite structurally exposed phrase candidates deterministically. The LLM is asked only one bounded semantic question for each concrete phrase: its relation to the current predicate. `actant_start` is diagnostic/legacy only and is no longer a semantic voter.

### 2. Generic modifier attachment over-triggered clarification

The P1 generic attachment layer treated every local `event vs adjacent nominal` possibility as user-visible ambiguity. Ordinary examples such as `положил папку на полку`, `получил письмо от Анны`, `взяла книгу со стола`, `сделал стол из дерева` therefore produced no parse.

Adjacency now only enumerates structural owners. One bounded `EVENT / NOMINAL_n / UNCLEAR` decision resolves the reading. Only `UNCLEAR` requests structural clarification, preserving genuine cases such as `увидел Петра с биноклем`.

### 3. WH role was selected before overt query participants

A wrong early guess for `Что` could reserve RECIPIENT and then force overt `Марии` into OBJECT. Query parsing now resolves known overt actants first while excluding WH spans, then assigns requested WH roles only among still-unfilled roles. Multi-WH keeps one-frame binding semantics.

### 4. Explicit temporal/causal connectors were reclassified by generic frame-role probing

`после/перед тем как` and explicit `потому что/так как/поскольку` could be mislabeled PURPOSE. Directional temporal compounds now materialize structural FOLLOW directly; explicit causal compounds materialize CAUSE directly. They are not proposition-valued actants.

Sentence-initial discourse sequencing (`потом`, `затем`, `после этого`) also emits FOLLOW structurally rather than depending on a TIME role first.

### 5. Runtime alternatives did not always inherit proposition scope

EMBEDDED/CONDITIONAL status is now propagated recursively to assertion alternatives, eliminating the runtime `Alternative assertion status/scope mismatch` path.

### 6. Lexical candidate fallback was under-constrained

The position-free fallback now explicitly lists the only allowed morphology lemmas and accepts output only if it maps exactly to one candidate. The mirrored A/B lexical probe also explicitly tells the model to use whole-sentence meaning and surrounding complements/modifiers when identifying a lexeme, while still asking only lexical identity.

### 7. Selected proposition content was confused with adjunct PURPOSE

Frame-relation prompting now contrasts selected CONTENT with adjunct PURPOSE explicitly: a desired/decided/requested/begun proposition can be intended and still be CONTENT. PURPOSE is the separate `PARENT in order to CHILD` reading.

### 8. Template valency extension was confused with a new sense

Adding optional TIME/TOOL/LOCATION/etc. no longer counts as evidence for `NEW` sense. Template-sense prompts explicitly state that role-set difference may be valency expansion of the same predicate meaning.

### 9. OBJECT vs RECIPIENT boundary was too broad

RECIPIENT is now described as an actual receiver/addressee/beneficiary/destination of object/information/communication/benefit. A person directly perceived, selected, summoned/called, or otherwise targeted may be OBJECT; personhood or direct targeting alone does not imply RECIPIENT.

## Architecture

Reference architecture advanced to **v0.25**. New invariants 128–136 cover deterministic actant enumeration, query ordering, attachment resolution, structural temporal/causal relations, alternative scope propagation, candidate-closed lexical fallback, CONTENT/PURPOSE separation, OBJECT/RECIPIENT semantics, and T-sense vs valency distinction.

## Regression coverage

Focused tests were added for:

- deterministic actant enumeration without an LLM `actant_start` stop vote;
- `Что Иван подарил Марии?` known-actants-first behavior;
- unambiguous PP event attachment before clarification;
- the earlier nonfinite-chain / coordinated-nonfinite / copular-holder regressions;
- EMBEDDED oracle expectations and probe protocol constraints.

## Local verification

- `python -m compileall -q src tests` — clean.
- Full unit suite: **327 passed + 4 subtests passed, 0 failed**.

The real broad200 model is not available in this environment, so no replacement score is fabricated. The next meaningful measurement is the same broad200 run on the user's local Qwen configuration.
