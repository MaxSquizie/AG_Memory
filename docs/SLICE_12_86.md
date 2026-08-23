# v0.12.86 — public-domain literary monolith

This slice adds a real, unadapted literary passage to document acceptance rather than another hand-authored causal scenario.

## Source

- Alexander R. Belyaev, `Человек-амфибия` (1928).
- Chapter: `Покинутая «Медуза»`.
- Public-domain source: Russian Wikisource.
- Local test file: `data/document_acceptance/texts/05_belyaev_amphibian_monolith.md`.

The selected passage covers the mutiny aboard the `Медуза`, Zurita's attempt to escape the sailors, the arrival of the submarine, the interruption of the attack, and the crew's subsequent flight. The text is not rewritten, simplified or supplemented with causal connectives for the test.

## Why this passage

It stresses mechanisms that synthetic `A потому что B` data does not:

- `Педро` and `Зурита` refer to the same actor;
- plural crew references continue across multiple sentences;
- actions are causally linked by physical and pragmatic context rather than a fixed connective;
- direct speech and internal thought coexist with narrator assertions;
- one event can be merely adjacent in narration rather than causal;
- the same actor alternates between overt names and pronouns.

The final oracle therefore grades the canonical graph, not exact sentence-by-sentence wording. It requires a two-edge implicit physical chain (`grab → hit → fall`), causal response from seeing the submarine to calling for help, and the crew stopping when an armed submarine arrives. It also forbids several plausible-but-unsupported causal shortcuts.

## Ingestion boundary

The production perception parser remains bounded. The source is kept as one monolith and diagnostics splits only at explicit sentence/dialogue boundaries while preserving one AH/InteractionContext/Ignition scenario. v0.12.86 extends the deterministic splitter for a common literary dialogue boundary: terminal punctuation followed by an em dash and a new capitalized utterance. Lowercase author attribution after an em dash is not split away. No LLM or oracle data participates in segmentation.

## M2 precommit

Three M2 paths are written before M2 execution:

1. sailor grabs Zurita → Zurita hits sailor → sailor falls;
2. Zurita sees the submarine → Zurita calls for help;
3. submarine approaches → sailors stop the attack.

These are not executed by document acceptance yet; they are frozen targets for the next M2 work.
