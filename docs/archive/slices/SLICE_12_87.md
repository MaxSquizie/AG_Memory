# Slice v0.12.87 — Event normalization + third literary monolith

## Why this slice exists

The first literary-monolith run showed that bounded sentence parsing could remain runtime-stable while the final event graph still lost or distorted prose-level structure. The defect class was broader than one Belyaev/house phrase: non-finite events, coordinated event sequences, result-state participles, narrative adjacency, and pronoun ambiguity could all alter the canonical graph before M2 ever starts.

v0.12.87 adds a deterministic runtime boundary between the parsed linguistic frame graph and canonical Integration. It is deliberately conservative: it recovers event/state structure that is already licensed by grammar, but it does not turn narrative proximity into canonical causality.

## EventNormalizer

`src/ah/perception/event_normalizer.py` runs after ordinary adaptive perception has built assertions/relations and before `PerceptionResult` is handed to Integration.

It can:

- promote a detached gerund from proposition-valued embedding back to an independently asserted event;
- for a preposed perfective gerund separated from its finite matrix by punctuation, materialize source-order `FOLLOW`;
- for an imperfective/temporally underdetermined gerund, retain only a runtime `SIMULTANEOUS_CANDIDATE` / `TEMPORAL_CANDIDATE`;
- materialize conservative `FOLLOW` between coordinated perfective predicates;
- expose the state encoded by an explicit passive full participle as `быть(SUBJECT, STATE)` without inventing who/what caused that state;
- expose weak adjacent-event causal hypotheses only as `CAUSAL_CANDIDATE` runtime hints.

`relation_hints` are part of `PerceptionResult`, are validated for local referential integrity, and are intentionally ignored by canonical Integration. They therefore cannot become proof edges merely because two events are adjacent in prose.

## Identity invariant after event normalization

A result-state assertion can reuse the same source NP span as the matrix assertion. After EventNormalizer runs, the parser executes the existing exact-source-span identity binder once more. This preserves one turn-local `entity_ref` for the matrix entity and its newly exposed state instead of creating two semantically identical entities.

## Pronoun alternative stabilization

A literary run exposed a generic failure mode where an ambiguous pronoun could create *correlated* runtime alternatives. The old implementation allocated an antecedent `entity_ref` lazily while iterating alternatives; if the antecedent was another actant in the same assertion, later alternatives started from a mutated base and more than one role appeared to vary.

v0.12.87 pre-binds every compatible antecedent source mention before branching. No antecedent is selected by this step. All alternatives now share one stable assertion skeleton and differ only in the actual anaphoric role, preserving the existing deterministic Integration ambiguity boundary.

## Negative document facts and scoped content

The document graph oracle now supports `final.forbidden_facts`. A fact matcher can additionally request `semantic_scope`:

- `ASSERTED` / `WORLD` means an unscoped world assertion;
- `EMBEDDED`, `QUOTED`, etc. match the corresponding canonical N metadata.

This lets literary acceptance distinguish “the narrator asserts X happened” from “a character imagined/seemed/thought that X happened” without pretending that embedded proposition content does not exist canonically.

## Document report categories

`document_report.json` and `document_summary.txt` now group final graph checks into:

- event extraction;
- temporal graph (`FOLLOW`);
- causal graph (`CAUSE` + minimum depth);
- negative constraints (forbidden facts/links);
- other checks.

This makes a literary failure immediately attributable to event formalization, chronology, causal structure, or over-inference.

## Third literary monolith

Added `data/document_acceptance/texts/06_old_observatory_monolith.md`: 34 connected sentences of hand-written prose, kept as one source monolith and ingested in 17 two-sentence bounded windows while AH/InteractionContext/Ignition remain continuous.

The text intentionally contains:

- preposed gerunds (`Отперев`, `Зажёгши`, `Увидев`, `Сняв`, `Поднявшись`, `Заметив`);
- coordinated event sequences;
- passive/result-state descriptions;
- two named participants and cross-sentence pronouns;
- direct speech;
- a subjective `Ей показалось, будто ...` episode whose embedded events must not become asserted world facts;
- physical and temporal adjacency without blanket `CAUSE` materialization.

Its manually authored final oracle contains 40 positive facts, 16 typed `FOLLOW` edges, 3 forbidden `CAUSE` shortcuts, 2 forbidden asserted-world facts, and 4 predeclared M2 paths. No synthetic scenario generator is used.

The GUI `Document acceptance` run now evaluates all six documents in one run: three technical documents plus `house_by_pier_monolith`, the public-domain Belyaev excerpt, and the new observatory prose monolith.

## Dialogue splitter

The monolith sentence splitter now preserves the leading em dash of a new direct-speech turn instead of consuming it as a delimiter. This keeps quotation evidence available to perception while still splitting only at explicit punctuation boundaries.

## Regression

Local deterministic/unit suite after this slice:

- `519 passed`
- `22 subtests passed`
- `compileall OK`

No live LM Studio score for the expanded six-document suite is claimed until the user runs `Document acceptance` with Qwen3.8.
