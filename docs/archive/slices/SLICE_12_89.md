# Slice v0.12.89 — Source-bounded perception and literary anaphora

## Why this slice exists

The live document run `20260823_044808_+0300` confirmed that a configured `max_acts` is the wrong abstraction. It was introduced as a runtime safety guard but behaved as a semantic ceiling: a valid source containing more predicate frames than the configured number could be rejected solely because of event count. Event count is a property of the input, not a perception hyperparameter.

The same run also left two real runtime failures in literary prose:

- `Но торжество его было недолгим.` — the deterministic copular holder recovered only `торжество` and left the postnominal possessive `его` as a fake third actant;
- `Сняв мокрый плащ, она повесила его ...` — local anaphora admitted predicative adjective states as referential antecedents and did not exploit the explicit NONFINITE→matrix dependency for same-role participant continuity, producing correlated alternatives before Integration.

## 1. `max_acts` removed as a semantic limit

`AdaptivePerceptionParser.parse()` no longer loops over a configured number of acts. It consumes frames until the finite source candidate graph is exhausted.

The structural invariant is now:

```text
one successful parser iteration
→ consumes one previously unused predicate span
  or one previously unused implicit copular clause
```

Therefore the source itself is the finite bound. There is no arbitrary `12`, `16`, `50`, etc. event ceiling.

If a model emits `NONE` while deterministic meaningful frames remain, parsing still fails closed. Partial semantics are never committed merely because the model stopped.

Removed from the public configuration/runtime surface:

```text
llm.perception.max_acts
LLMConfig.perception_max_acts
LLMPerceptionSettings.max_acts
AdaptiveSettings.max_acts
```

The GUI now reports:

```text
acts=source-bounded
```

instead of a numeric cap.

Existing bounded controls remain where they describe local computational work rather than source semantics: retry count, per-probe generation budget, request timeout and `max_actants_per_act`. The latter is not changed in this slice.

## 2. Postnominal possessive is part of a copular holder NP

The generic NP chunker already recognized Russian postnominal possessive anaphors (`решение его`, `торжество её`). The deterministic copular-holder fast path did not reuse that boundary and returned only the nominal head.

It now extends an otherwise proven copular holder across an immediately following morphology-marked postnominal possessive anaphor. This is position/morphology driven; no lexical phrase list is introduced.

```text
торжество его было недолгим
→ SUBJECT = "торжество его"
→ STATE = "недолгим"
```

and `его` no longer becomes an impossible extra role.

## 3. Referential filtering in personal-pronoun coreference

Ordinary predicative adjective/participle states are no longer accepted as antecedent entities merely because their POS is nominal-like.

Personal-pronoun antecedents now require either:

```text
NOUN / NPRO
```

or an explicitly substantivized adjective/participle morphology (`Subx`).

This prevents a state such as `сердитая` from competing with `Вера` as the antecedent of `она`, while still preserving true substantivized forms.

## 4. Same-role continuity across an explicit NONFINITE dependency

When the linguistic frame graph explicitly contains:

```text
matrix predicate
   └── NONFINITE child predicate
```

and a matrix personal pronoun has exactly one grammatically compatible antecedent in the child with the same semantic role, that source participant is preferred before generic discourse ambiguity handling.

Example class:

```text
Сняв плащ, она повесила его.

снять.OBJECT = плащ
повесить.OBJECT = его
NONFINITE(повесить <- снять)
→ его reuses the source participant "плащ"
```

This does not create a canonical UID choice in the LLM and does not introduce predicate-specific rules. If more than one compatible same-role child antecedent remains, the ordinary ambiguity-preserving path is used.

## Regression

- Numeric act ceilings are absent from config and parser settings.
- A parser boundary regression now verifies 20 source predicate frames are all consumed with no configured act cap.
- Existing semantic/document/M2 regression suites remain enabled.
