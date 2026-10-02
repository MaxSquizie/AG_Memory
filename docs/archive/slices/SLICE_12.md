# Slice 12 — compositional perception

## Main change

Default perception protocol is now `adaptive_v3`.

Pipeline:

```text
text
→ deterministic linguistic candidate graph
→ morphology alternatives / clause windows / predicate heads / coordination
→ tiny stateless LLM choices only where candidates remain ambiguous
→ deterministic semantic composition
→ PerceptionResult
→ deterministic Integration
```

The LLM is not expected to know AH terminology and is not shown output examples.
Probe prompts contain only the current context, a short task definition and the
actual finite option set. Previous invalid output is never included in retries.

## Deterministic candidate graph

`linguistic_candidates.py` builds runtime-only candidates for:

- all materially distinct morphology parses instead of trusting only the top parse;
- predicate heads;
- clause boundaries and subordinate markers;
- simple AND/OR coordination.

High-confidence decisions bypass the LLM. Ambiguous choices stay as finite probes.

## Composition

Coordinated actants can now carry a structured `ActantCompositionCandidate`.
Integration materializes it as canonical `g.AND(...)` / `g.OR(...)` instead of
flattening coordination into one entity name.

Subordinate clauses with stable markers can be connected through local
`candidate_ref` before canonical UID creation.

## Validation

- no prompt examples/few-shot anchors in the active micro-prompts;
- one-option numeric replies only for discrete probes;
- open text remains only for unknown English semantic predicate naming;
- retry is stateless;
- 114 tests pass.


## Conservative ambiguity policy

- every non-deterministic semantic relation probe exposes an explicit abstention choice;
- predicate boundary, query mode, role selection and ambiguous frame attachment never force a guess;
- morphology candidates are parsed in source order rather than asking the LLM to choose one "main" predicate;
- coordinated predicate frames are kept independent and may share deterministic arguments;
- sentence-local candidate construction prevents predicates in later sentences from influencing current clause boundaries.
