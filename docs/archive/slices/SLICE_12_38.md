# Slice 12.38 — semantic oracle + architecture audit

## Goal

Stop treating `no exception` as parser acceptance. Establish a semantic baseline before changing production parsing again.

## Added

- `data/acceptance_oracle.json` — curated expectations for the existing 40-case suite.
- `ah.diagnostics.semantic_oracle` — live and offline semantic evaluator.
- PASS / FAIL / GAP semantic statuses.
- cumulative explicit-role T coverage check.
- offline re-grading of old acceptance bundles.
- `docs/ARCHITECTURE_AUDIT_01238.md`.
- `docs/SEMANTIC_ORACLE.md`.

## Important policy

`[DEFER]` is not treated as an absolute ban. The audit concludes that controlled monotonic `T` valency evolution is now required for open-ended correctness and should be the next implementation step.

## Parser behavior

No production perception/integration behavior is intentionally changed in this slice. v0.12.38 is a measurement/revision baseline.

## Baseline from the supplied v0.12.37 model run

```text
runtime:  33 OK / 7 ERROR
semantic: 27 PASS / 9 FAIL / 4 GAP
```

The lower semantic score is expected: the old acceptance counter did not inspect meaning.
