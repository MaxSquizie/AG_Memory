# Semantic acceptance oracle

`data/acceptance_cases.txt` is only the sequence of user inputs.

`data/acceptance_oracle.json` is the curated semantic contract for those inputs.

The acceptance suite now reports two independent layers:

```text
RUNTIME OK / ERROR
SEMANTIC PASS / FAIL / GAP
```

`RUNTIME OK` only means the normal pipeline returned. It is never treated as semantic correctness.

`SEMANTIC PASS` requires the oracle checks to match:

- assertion/query count;
- predicate identity;
- assertion status and negation;
- exact filled role set;
- role values/compositions/coreference;
- nested assertion references;
- situation relations;
- conditional branch structure plus canonical `IF/AND` composition and scoped proposition storage;
- Integration completion;
- expected C/P domain;
- clarification behavior, including structural ambiguity that must defer C/P semantic commitment;
- query/inference conclusion;
- canonical N/G representation for integrated assertions;
- canonical T coverage of every **explicitly observed or requested** role accumulated so far.

The oracle deliberately does **not** require speculative hidden roles. That question is separate from concrete semantic correctness and is unsafe as an irreversible canonical requirement.

`ARCHITECTURE_GAP` is not a pass. It means the input exposes semantics that `Архитектура_v3` does not yet define sufficiently to state a complete canonical expected result.

The frozen 40-case regression corpus has no intentional GAP after v0.12.44: cases 30–32 have exact canonical conditional expectations, and genuine attachment ambiguity in case 39 passes only when the system returns the expected structural clarification without guessing. From v0.12.47 the default `broad200-v2` corpus contains 200 `EXACT` cases. `ARCHITECTURE_GAP` remains a valid oracle grade for future corpus items whose semantics are genuinely not defined by the working architecture, but it must not be used merely because current code fails an otherwise well-defined case.

Each case may also carry `family` and `tags`. They do not change correctness; they are diagnostic metadata. Live and offline reports aggregate PASS/FAIL/GAP by family so a large suite can be diagnosed by semantic mechanism rather than only by the global score.

## Offline evaluation

`ah.diagnostics.semantic_oracle.evaluate_acceptance_bundle(run_dir, oracle_file)` can re-grade an existing acceptance bundle without rerunning the LLM. It reconstructs the canonical AH state turn by turn from `initial_ah.json` + each `ah_diff`.

It writes:

```text
semantic_report.json
semantic_summary.txt
```

This is useful when the oracle becomes stricter: old model runs can be re-evaluated under the new correctness contract without spending GPU time again.


## Scenario boundary semantics (v0.12.50)

`acceptance_oracle.json` may attach `scenario` to each case. Consecutive cases with
the same scenario intentionally share canonical/context state. When the id changes,
live acceptance and offline re-grading both restart from `initial_ah.json` / the run
baseline and clear accumulated template-role expectations. Missing `scenario` keeps
legacy sequential behavior for older oracles.
