# Slice v0.12.88 — Literary reliability: grammar, discourse and acceptance boundary

## Live-run diagnosis

The v0.12.87 document run (`20260823_041519_+0300`) was useful because the failures separated cleanly into diagnostics, runtime budget, and real discourse grammar:

- `cooling_station`: final graph `18/18`;
- `greenhouse_control`: final graph `18/18`;
- `archive_leak`: final graph `19/19`;
- every apparent paragraph failure in the first 20 units was only `perception.relation_hints` being compared against an oracle that predates this optional runtime channel;
- 14 runtime failures occurred in literary prose, 13 of them because the parser intentionally stopped after `max_acts=4`; this is too small for normal multi-event sentences but is not an AH semantic invariant;
- the remaining runtime failure exposed a real NP-boundary bug in `торжество его было недолгим`;
- Belyaev additionally exposed cross-window anaphora, finite-agreement anchoring and rightward coordinated-subject ellipsis.

## 1. Runtime-only relation hints are opt-in for exact semantic grading

`CAUSAL_CANDIDATE`, `TEMPORAL_CANDIDATE` and related hints are weaker runtime diagnostics emitted by EventNormalizer. They are not canonical `L` and Integration deliberately ignores them. An old exact oracle that never declared a `relation_hints` expectation must therefore not fail merely because the diagnostic layer gained a new hint.

`semantic_oracle.py` now calls `_match_relation_hints` only when the expectation explicitly contains the `relation_hints` key. Oracles that care about the hints retain exact grading; all others preserve backward-compatible semantics.

## 2. `max_acts` is a resource guard, not a four-event language model

The shipped/default perception budget is raised from `4` to `12` in default, LM Studio and Ollama configs and in runtime defaults. The hard configuration validator remains `[1,16]`.

This does not relax fail-closed semantics: callers/tests that explicitly use `max_acts=4` still fail if a fifth meaningful frame remains. It only stops the production parser from treating normal literary sentences with five to ten predicates as malformed input.

## 3. Finite predicate agreement strengthens cross-turn discourse anchors

A surface nominal can be morphologically misleading:

- a proper surname may expose no stable gender;
- a quantified subject can end in a genitive singular noun while the whole NP is plural.

For an already resolved semantic `SUBJECT`, Integration now first derives the runtime discourse signature from its finite predicate occurrence. A plural finite verb yields plural; a past singular verb with unique gender yields that gender. Only if predicate agreement is unavailable does the older nominal-signature logic run.

No semantic identity is inferred from agreement. The mechanism only determines which nominative third-person pronoun slot (`он/она/оно/они`) can safely carry an already integrated canonical M into the next turn.

## 4. Oblique third-person forms use existing nominative anchors conservatively

InteractionContext continues to store only nominative anchors. `DeixisResolver` now knows the closed Russian oblique/possessive paradigm and can map a source form such as `его`, `ему`, `ей`, `их` back to compatible nominatives.

A result is returned only if all currently available compatible nominatives collapse to one canonical Ref. Syncretic `его` with two different `он`/`оно` refs stays unresolved. This preserves the architecture boundary: grammar narrows, canonical identity is never guessed.

## 5. Local anti-reflexive binding constraint

The local perception coreference pass now excludes the grammatical SUBJECT of the same assertion as an antecedent for a non-reflexive third-person oblique personal pronoun.

Thus `Матрос схватил его` cannot resolve `его` to that same matros; Russian requires `себя` for the reflexive reading. An earlier compatible discourse participant remains eligible. This fixes a general binding error without any lexical rule for `матрос`, `Зурита` or the Belyaev corpus.

## 6. Postnominal possessive NP boundary

Russian `его/её/их` can have both personal-pronoun and indeclinable possessive-adjective analyses. The conservative NP chunker still refuses to swallow a pre-head NPRO as a modifier, but after an established nominal head an `ADJF+Anph+Subx` reading is now sufficient to keep the token in the same NP.

This handles `решение его`, `торжество его` and equivalent literary inversion, preventing the possessive from becoming a spurious third actant of a copular frame.

## 7. Rightward subject sharing inside explicit predicate coordination

The existing coordination engine already shared a common subject when it was group-peripheral. Literary Russian also regularly places the shared subject after the first finite predicate: `выпустили матросы свою жертву и упали`.

For an explicit predicate-coordination group, a single known SUBJECT can now propagate to rightward members when a coordinator lies between its source occurrence and the target predicate and no new nominative subject shell begins there. No semantic probe is used for this strong grammatical configuration.

## 8. Belyaev oracle grounding

The public-domain excerpt first says `Зурита`, then `Педро`, and only much later contains the full form `Педро Зурита`. The previous final oracle required the attack OBJECT `Педро` to already be the same canonical M as the earlier `Зурита`, which silently imported external novel knowledge / future text into an earlier identity check.

The oracle now checks `Педро` literally at that point. Crew-event checks also use source-grounded `матросы` constraints where exact canonical group identity is not the property under test, reducing diagnostic cascades while preserving explicit event and causal expectations.

## Regression

New lexical-independent regressions cover:

- finite-predicate masculine anchoring when the proper nominal has no stable morphology;
- plural verb agreement overriding a misleading singular surface head of a quantified subject;
- unique and ambiguous oblique-pronoun dereference;
- the Russian anti-reflexive local binding constraint;
- postnominal possessive NP chunking;
- default production `max_acts=12`.

Result: `526 passed, 22 subtests passed`; `python -m compileall` passes.
