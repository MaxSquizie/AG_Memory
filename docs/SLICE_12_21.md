# Slice 12.21 — end-to-end clarification lifecycle

This slice completes the `k_AMBIGUOUS + clarification path` required by
`Архитектура_v3` §§3.11, 7.5, 8.3 and the full integration pipeline.

## Boundary

```text
Perception runtime alternatives
  ↓
deterministic Entity Resolution
  ↓ unresolved canonical alternatives
k_AMBIGUOUS(m1, m2, ...)
  ↓
ClarificationRequest
  ↓
agent_clarification            # language generation only
  ↓
explicit user answer
  ↓
deterministic match OR tiny clarification-answer perception probe
  ↓
validate selected option ∈ k.members
  ↓
atomic canonical replacement k -> m
```

The response LLM never receives authority to choose the canonical referent. Its
`agent_clarification` role only turns already-determined candidate labels into a
natural question. If the user's answer is not an exact deterministic label/number,
`perception_clarification_answer` may classify which *presented option the NEW answer
explicitly identifies*. It does not re-score the original ambiguous sentence.

## Runtime state

A clarification is placed in `InteractionContext.pending_clarification_refs` only
after the clarification utterance has actually been generated and committed to H.
The pending queue is persisted with the normal interaction context.

Acceptance diagnostics call the orchestrator with `generate_response=False`; those
runs still expose `IntegrationCommit.clarifications`, but do not arm the pending
queue, so the next independent acceptance case is never mistaken for a clarification
reply.

## Resolution mutation

The user's clarification utterance is recorded as an H event but is not fabricated as
a standalone C/P fact. Integration validates that the selected ref is a member of the
canonical ambiguity group and then replaces references transactionally. If resolving
an ambiguous N makes it identical to an existing N in the same domain, the duplicate
is collapsed and canonical references are redirected, preserving domain-local dedup.

The original `k_AMBIGUOUS` object is retained as the addressable record of the former
alternative set; facts no longer point to it after resolution.

Ignition policy and predicate/T valency behavior are unchanged in this slice.
