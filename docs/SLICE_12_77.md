# v0.12.77 — non-thinking semantic protocol + fail-closed optional projection

## Live failure addressed

The real v0.12.76 run failed before returning a `PerceptionResult`:

```text
PerceptionParseError: nominal_label_semantics expected exactly one of: YES, NO, UNCLEAR
```

The nominal syntax itself was already correct. The failure came from the new
request-local `enable_thinking=True` semantic cue: a thinking-capable checkpoint can
spend its bounded generation on the reasoning channel, or expose reasoning text
instead of the exact machine-protocol label. An exact `YES / NO / UNCLEAR` parser
must not depend on a reasoning channel being stripped correctly.

## Change

`semantic_nominal_label_semantics` remains an isolated semantic role, but it now
**forces `enable_thinking=False` request-locally**, even when thinking is enabled in
the global model configuration. The generation budget is reduced back to the small
protocol budget (`<=8` new tokens).

No likelihood choice scorer, output repair, label extraction, or hidden
canonicalization is introduced. The backend still has to emit exactly one supplied
protocol label.

## Optional post-parse enrichment is no longer turn-fatal

The shorthand assertions produced by nominal naming projection are derived
post-parse enrichment. The explicit source facts, for example:

```text
название(Крипл, моего проекта)
имя(Крипл, моего ИИ)
```

are already valid primary assertions before the semantic projection cue runs.
Therefore a malformed answer from this one optional cue must not erase those facts
or invalidate the whole turn.

For this optional call only:

- an out-of-protocol model string is kept in `ProbeTrace` with the exact error;
- the derived projection is omitted (fail closed);
- the explicit parsed assertions survive;
- backend/infrastructure errors still propagate normally.

This is not a semantic fallback: no alternate meaning is selected and no assertion
is invented. The system simply declines an optional derivation whose semantic cue
was not valid.

## Regression added

A dedicated backend fixture reproduces the live failure: when a request asks for
thinking it emits reasoning text instead of a label. The parser must force thinking
off and recover all four expected assertions. A second fixture always violates the
semantic protocol and verifies that only the two explicit source facts remain while
the invalid traces are preserved.

## Verification

```text
LLM + nominal targeted: 84 passed
full suite: 479 passed + 22 subtests, 0 failed
```
