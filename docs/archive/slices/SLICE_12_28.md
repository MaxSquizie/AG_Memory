# Slice 12.28 — pairwise SLM semantic boundary

## Goal

Keep model work minimal: deterministic code proposes one semantic hypothesis; the local SLM answers only `YES` or `NO`; deterministic code validates and continues.

## Changes

- `ah.llm.worker` fixed-choice scoring exposes the winning option, per-choice normalized log-likelihood scores, and the winner/runner-up margin.
- Margin is parser evidence only. It is never truth confidence and never writes to AH `w`.
- `AdaptivePerceptionParser._binary_probe` offers exactly `YES` and `NO`. Low-margin results are treated as unresolved without adding `UNKNOWN`/`NONE` to the model choices.
- Dynamic TemplateCandidate discovery uses a tiny deterministic hidden-core-role shortlist and tests one candidate at a time.
- Nested frame attachment (`CONTENT/PURPOSE/CAUSE/MANNER`) is pairwise and ordered from structural syntax.
- Multiple controller candidates are checked one at a time; zero or multiple positive controllers remain runtime alternatives.
- Role-family and exact-role semantic classification use ordered pairwise tests and stop on the first confident match.
- Discourse sequencing markers (`потом`, `затем`, `после этого`) deterministically create `FOLLOW(previous,current)` and are removed as TIME actants.

## Invariants

- No model-created UID or canonical AH mutation.
- No T valency evolution.
- No free-form schema generation.
- No semantic `NONE/UNKNOWN` escape for the pairwise probes above.
- Low model separation means unresolved parser ambiguity, not guessed semantics.
