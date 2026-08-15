# Slice 12.11

Strict TemplateCandidate boundary between perception frames and canonical `T/N`.

## Template boundary

- Added runtime-only `TemplateCandidate(roles)` to `PredicateCandidate`.
- Perception finishes frame normalization first, then emits a separate role schema for the predicate use.
- `TemplateCandidate` has no UID and is not canonical AH state.
- `TemplateResolver` may reuse an already canonical `T` without a new candidate.
- `TemplateResolver` may **not create** a new `T` unless an explicit `TemplateCandidate` is present.
- New `T.roles` come from the validated template candidate, never from the concrete `N` filling passed to integration.
- `FilledRoles(N) ⊆ Roles(TemplateCandidate) ⊆ Roles(T)` is checked deterministically.
- A template candidate may contain roles that the current `N` does not fill. This preserves the architectural distinction between a predicate schema and one concrete fact.
- Failed template creation does not leave a predicate `S` behind.
- `FILL_ROLE` query resolution now also requires the requested role to exist in the selected canonical `T`.

Adaptive perception constructs the candidate after all existing deterministic frame normalization (including shared-subject inheritance and coreference). Query candidates additionally include the requested role in the proposed schema. No new LLM call was introduced.

## No semantic fallbacks

- Adaptive parser no longer returns a partial successful parse when a later act, predicate symbol, relative role, frame relation, or predicate selection cannot be resolved.
- A semantic parse now has exactly two outcomes: a valid `PerceptionResult` or `PerceptionParseError`.
- Removed `failure_policy=empty`; parser errors are never converted to an empty successful result.
- The orchestrator still records the raw external utterance as an H experience before re-raising `PerceptionParseError`. No C/P semantic assertion is fabricated.

This keeps the weak LLM boundary narrow: Python constructs, normalizes, validates and canonicalizes; LLM probes only resolve bounded semantic uncertainty.
