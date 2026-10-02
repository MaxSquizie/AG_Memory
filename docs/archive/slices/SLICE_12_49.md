# Slice v0.12.49 — acceptance evaluator resilience

## Observed real broad200 failure

The 2026-08-16 broad200 run reached case 167 and then the diagnostics evaluator crashed while evaluating the following query case. A query record may legally contain `outcome: null` when no inference conclusion exists. The oracle used `item.get("outcome", {})`; because the key existed, this returned `None`, and the next `.get("status")` raised `AttributeError`.

## Fix

1. Normalize a non-mapping/`null` query outcome to an empty mapping before checking expected status/role/value. The case becomes a normal semantic FAIL.
2. Treat semantic-oracle execution as a diagnostics boundary: unexpected evaluator exceptions are serialized to the turn record as `semantic_evaluator_error` / `semantic_evaluator_traceback`, with an `oracle.evaluation_error` failed check, and the suite continues.
3. Manifest extraction ignores malformed/non-mapping check entries rather than becoming a second failure source.

## Architectural effect

None. Perception, Integration, AH Core, prompts, the broad200 corpus, and Architecture v0.11 are unchanged.
