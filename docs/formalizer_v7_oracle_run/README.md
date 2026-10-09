# V7 concrete oracle execution

Baseline: `c26854847a21086086790e87981a6da42d31261a`; exact implementation hashes are in `provenance.json`.

Result: **1319 PASS / 0 FAIL / 1223 BLOCKED**. Full run status: **BLOCKED**.

| Tier | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|
| component | 1310 | 0 | 521 |
| durability | 9 | 0 | 62 |
| pipeline | 0 | 0 | 640 |

`actual.jsonl.gz` contains actual checkpoints and concrete binding manifests; its decompressed hash is pinned. `comparison.json` lists every result and blocker. `runtime_coverage.json` reports case coverage per mechanism/A/DR/action. Signed resource files use a public TEST_ONLY fixture key and are not a reviewed production release.

No raw-text case is claimed executed without its API binding. These are component and file-WAL checks; `crash` discards the adapter and restores a fresh AH core, not a killed operating-system process. Compiler IR export currently means admitted typed T5 plans, not a full parser IR snapshot. Gates G0–G5 are not evaluated. Missing actions block the entire case before writes; runtime exceptions fail the case.
