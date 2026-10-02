# Slice 11 — weak-model discrete perception

## Цель

Свести роль LLM Perception к минимальному числу недетерминированных решений и не требовать от модели знания АГ-архитектуры или специальной грамматики.

## Adaptive v2

```text
source text
  ↓ Python tokenization
ACT TYPE                  numeric choice
  ↓
PREDICATE START           numeric choice over source tokens
  ↓
PREDICATE END             numeric choice over precomputed legal endings
  ↓
PREDICATE SYMBOL          short English semantic name (only open-text probe)
  ↓
NEGATION                  deterministic when unambiguous, else 0/1
  ↓
ACTANT START/END          numeric choices over legal source spans
  ↓
ROLE FAMILY               numeric choice over 3 plain-language groups
  ↓
EXACT ROLE                numeric choice over a short group-specific list
  ↓ Python mapping
PerceptionResult
```

The LLM never receives UIDs, canonical AH nodes, domains, graph state, T/N construction rules, or canonical mutation operations.

### No hidden meta-notation

`N`, `N-M`, `ROLE`, JSON schemas and AST formats are gone from the active protocol. Every number shown to the model has an explicit meaning in the same request. Span-end options include the concrete source phrase they would select.

### Deterministic fast paths

- no negative marker in source → `negated=false` without an LLM call;
- direct `не` immediately before predicate / explicit `нет` → `negated=true` without an LLM call;
- no legal actant starts → extraction stops without an LLM call;
- one legal span end / one remaining role → Python selects it;
- high-confidence Russian question words (`где`, `когда`, `сколько`, `почему`, `зачем`, `откуда`, ...) map to the requested role without an LLM call.

### Role classification

The model never needs to know `ActantRole`. It first chooses a plain-language family:

1. participant/entity;
2. description/context;
3. reason/goal/means.

Then it chooses one short plain-language definition inside that family. Python maps the selected number to `SUBJECT`, `OBJECT`, `STATE`, `LOCATION`, etc.

### Safety boundary

Any invalid scalar answer is rejected. The validator tolerates only harmless terminal punctuation. It never extracts a valid number from explanatory prose. Failed retry uses the identical clean prompt and never includes the previous bad answer.

## Architecture reconciliation

The architecture contract is unchanged:

```text
LLM Perception -> runtime-only PerceptionResult -> Deterministic Integration
```

The implementation merely narrows the LLM side of that boundary. Canonical UID, entity resolution, T creation, domain routing, deduplication and AH mutation remain deterministic.
