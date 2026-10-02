# Slice 12.30 — deterministic valency narrowing and fail-closed frame attachment

## Architecture alignment

This slice keeps the v3 trust boundary intact:

```text
Text
→ Perception (deterministic linguistic narrowing + tiny SLM cues)
→ PerceptionResult / TemplateCandidate
→ Deterministic Integration
→ canonical T/N/L/k mutation
```

Perception never creates canonical UIDs or writes AH directly. `T` valency evolution
remains deferred, so an unresolved latent role must not be silently converted into a
narrow canonical T.

## Dictionary transitivity

`MorphInfo` now preserves OpenCorpora grammemes and a normalized `transitivity` cue.
`stable_transitivity()` accepts the cue only when all material verbal readings that
expose it agree.

For a new TemplateCandidate:

- stable `intr` blocks a latent OBJECT hypothesis without an SLM call;
- stable `tran` adds OBJECT to the runtime TemplateCandidate without an SLM call;
- absent/conflicting evidence leaves OBJECT unresolved for a tiny SLM classification.

This is perception-side lexical evidence only. Canonical T creation is still done by
Integration after deterministic validation.

## Hidden semantic slots

Remaining latent participant slots use concrete English distinctions instead of
linguistic meta-labels or YES/NO:

- `TAKES_OBJECT / NO_OBJECT_SLOT`
- `TAKES_RECEIVER / NO_RECEIVER_SLOT`
- `TAKES_SOURCE / NO_SOURCE_SLOT`
- `HAS_SUBJECT_SLOT / NO_SUBJECT_SLOT`

The question describes the actual slot (direct object, receiver/addressee/destination,
source/origin) in simple English. A low-margin result raises explicit
`AdaptiveParseError`; it does not register a narrower T and rely on future valency
widening, because widening is outside the MVP.

## Nested frame attachment

Frame probes are relation-specific:

- OBJECT/content: `CONTENT_LINK / NOT_CONTENT`
- PURPOSE/goal/request/want: `GOAL_LINK / NOT_GOAL`
- CAUSE: `CAUSE_LINK / NOT_CAUSE`
- HOW-TO/manner: `MANNER_LINK / NOT_MANNER`

A confident negative may advance to another structurally allowed hypothesis. A
low-margin result stops immediately with explicit ambiguity/error. Perception never
silently degrades an uncertain nested graph into two unrelated situations.

Bare Russian `что` clauses are narrowed deterministically to the CONTENT hypothesis;
causal compound markers continue to compile through their deterministic CAUSE path.

## Preserved mechanisms

- direct mutually-exclusive controller choice from v0.12.29;
- full fixed-choice score/margin diagnostics;
- clause-level FOLLOW/CAUSE normalization;
- deterministic lexical identity and `дома → LOCATION` narrowing;
- clarification lifecycle and `k_AMBIGUOUS` boundary;
- live VisPy canvas during acceptance;
- strict existing-T/no implicit valency evolution policy.
