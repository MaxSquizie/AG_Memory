# Slice 12.37 — hidden-valency order-bias preflight

## Goal

Before changing the production hidden-valency protocol again, directly test whether the local Qwen model makes an order-invariant semantic binary decision or merely copies the first offered label.

## Diagnostic boundary

The preflight is diagnostics-only:

```text
fixed semantic cases
→ same hidden-valency prompt shape
→ local Qwen
→ raw answer + diagnostic semantic normalization
→ order comparison
→ report only
```

It does not invoke Orchestrator, Integration, TemplateCandidate registration, or any AH mutation operation.

The Ignition clock is temporarily paused for the diagnostic and restored afterward so the before/after AH safety snapshot cannot be changed by unrelated background ticks.

## Cases

Six fixed capability cases are used:

```text
RECIPIENT
  подарить → HAS_RECIPIENT_SLOT
  любить   → NO_RECIPIENT_SLOT
  победить → NO_RECIPIENT_SLOT

SOURCE
  получить → HAS_SOURCE_SLOT
  любить   → NO_SOURCE_SLOT
  подарить → NO_SOURCE_SLOT
```

Each case is called twice:

```text
canonical order: HAS / NO
reversed order:  NO / HAS
```

Therefore the preflight makes 12 LLM calls.

## Classification

Per case:

- `SEMANTIC_OK` — both orders return the expected semantic label;
- `ORDER_BIAS` — the model chooses position 1 in both orders;
- `SEMANTIC_WRONG` — both orders agree on the same wrong semantic label;
- `INCONSISTENT` — both outputs are valid labels but disagree in another pattern;
- `MALFORMED` — at least one output cannot be reduced to one binary label.

The report also counts how often the selected label is position 1.

## `</think>` separation

Production parsing remains strict fail-closed and is unchanged.

The diagnostic separately records:

```text
EXACT
RECOVERED_ORPHAN_THINK_CLOSE
MALFORMED
```

Only the already-observed trailing orphan `</think>` wrapper may be removed for the diagnostic semantic comparison. This does not make such an answer valid in production. Explanations, punctuation, multiple labels, or other extra text remain malformed.

This separation lets the run answer two independent questions:

1. Does the worker/chat-template path emit a protocol-clean answer?
2. Ignoring only the known wrapper artifact, does the model make an order-invariant semantic choice?

## GUI and bundle

The GUI exposes a dedicated `Hidden-valency preflight` button next to the acceptance runner.

A run writes:

```text
data/hidden_valency_diagnostics/<timestamp>/
  case_*.json
  manifest.json
  summary.txt
  ah_diff.json
```

and automatically creates a sibling ZIP bundle for analysis/upload.

## Decision rule

This slice deliberately does not change production hidden-valency discovery.

- order-invariant semantic success supports one final local protocol/transport fix;
- systematic first-position selection demonstrates positional copying bias and is evidence to move this narrow semantic cue to a stronger LLM while preserving the deterministic Integration boundary.
