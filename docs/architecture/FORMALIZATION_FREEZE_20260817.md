# Formalization freeze — 2026-08-17

## Decision

Formalization/perception is frozen for the MVP unless a defect blocks the live demo or corrupts canonical memory. No further broad200 tuning is planned before the hackathon deadline.

## Last real Qwen broad200

- cases: 200
- runtime OK: 198
- runtime ERROR: 2
- semantic PASS: 154
- semantic FAIL: 46
- GAP: 0
- the run used roughly 700 LLM requests and is too expensive for normal iteration.

The remaining failures are concentrated in role/ambiguity edge cases. They are accepted as post-MVP unless a live scenario exposes a canonical-memory blocker. Unit/regression tests remain the fast gate.

## Verification policy after freeze

1. Run the full deterministic/unit suite after code changes.
2. Use a small targeted smoke/regression subset for any parser bug found in a live demo.
3. Do not rerun broad200 during normal MVP development.
4. Spend remaining time on AH memory mechanics, demo reliability and required evaluation artifacts.
