# Live validation — gemma-3n-e4b-it via LM Studio

Date: 2026-10-09 · HEAD `ce80c89` (branch `temp`, synced from origin) · model `gemma-3n-e4b-it` @ `http://127.0.0.1:1234`

Purpose: exercise the implemented mechanics against a REAL local model and record results,
including gaps that surface only under live data ("considered implemented" vs actually working).

## 0. Harness fixes required to run (real integration gap)

The committed live drivers were **out of sync with the current `RealBackendSelector` contract**
introduced by the recent native-path commits. Both failed with a swallowed `TypeError` →
reported as `PROVIDER_UNAVAILABLE` for every call:

- `RealBackendSelector._transport` calls `backend.generate(prompt, system=..., role=..., override=self.generation_settings)`.
- The drivers' ad-hoc `_LMChatBackend.generate(self, prompt, *, system="", role="generic")` did **not** accept `override`, and omitted the mandatory `top_k` kwarg of `LMStudioClient.chat_completions`.

Fixed in both `scripts/run_formalizer_real_backend.py` and `scripts/run_open_set_live.py`:
accept `override: dict | None`, honor its temperature/top_p/max_new_tokens/enable_thinking, and always pass `top_k` (0 → greedy 1). **These two script edits are uncommitted.**

### 0b. REAL production-transport bugs found & fixed (`src/ah/llm/lmstudio_client.py::native_chat`)
The canonical Phase 1 driver `scripts/p1_real_run.py` uses the **real production backend**
(`build_llm_backend` → `reasoning_safe_lmstudio.LMStudioBackend`, which calls the native
`/api/v1/chat` endpoint). It failed **100% of live calls with PROVIDER_UNAVAILABLE** on this model,
due to two stacked transport bugs (both surfaced only under live data):

1. **`top_k=0` rejected.** `native_chat` always sent `"top_k": int(top_k)`; the bounded selector's
default `generation_settings` has `top_k: 0`, and LM Studio native requires `top_k >= 1`
→ HTTP 400 (`too_small`). Fix: omit the field when `top_k <= 0` (server default applies).
2. **`reasoning="off"` rejected on non-reasoning models.** The backend always sends
`reasoning="off"`, but gemma-3n-e4b-it does not expose a reasoning switch → HTTP 400
(`invalid_value: param=reasoning`). Fix: on a 400 that names `reasoning`, retry once without the field.

**Impact:** before this fix, `p1_real_run.py` (the canonical Phase 1 validation driver) had never
actually measured anything live for non-reasoning models — every call was an instant transport failure.
After the fix it runs end-to-end. **This edit is uncommitted.**

**Regression check:** full formalizer+LLM sweep (629 tests) gives identical results with and without my
changes (verified via `git stash` A/B): 47 failures + 69 errors in both — all pre-existing in this synced
state (environment-dependent: GUI/PySide6, data files, network). The 13 targeted LM Studio client/backend
tests pass. **My changes introduce zero regressions.**

## 1. S1–S6 formalizer vertical (`run_formalizer_real_backend.py`, RealBackendSelector, attempts=1)

Targets: V1=HAVE V2=HAS_PART V3=LOCATIVE V4=LIKE. C1=resolved to target · C2=honest incompleteness (target preserved or miss) · C3=wrong meaning committed · PROTOCOL_ERROR=computational failure.

### baseline (single sample run) — C1=5 C2=1 C3(wrong)=0 PROTOCOL_ERROR=0 · protocol-valid JSON 6/6
(One-shot result; see the determinism probe below for the stable picture, which is 2/6 resolved.)
| # | sentence | target | outcome | selected | diag | class |
|---|----------|--------|---------|----------|------|-------|
| S1 | У вороны есть лапки. | V2 | RESOLVED | [V2] | — | C1 ✓ |
| S2 | У стола есть ножки. | V2 | RESOLVED | [V2] | — | C1 ✓ |
| S3 | У меня есть книга. | V1 | RESOLVED | [V1] | — | C1 ✓ |
| S4 | Ворона обладает перьями. | V2 | RESOLVED | [V2] | — | C1 ✓ |
| S5 | У вороны лапки. | V2 | UNRESOLVED | [V2,V1] | NO_GROUNDED_CANDIDATE | C2 (honest) |
| S6 | Вороны любят червей. | V4 | RESOLVED | [V4] | — | C1 ✓ |

### augmented (single sample run, + contextual statements F1/F2/F3) — C1=2 C2=4 C3(wrong)=0 PROTOCOL_ERROR=0 · protocol-valid JSON 6/6
| # | sentence | target | outcome | selected | diag | class |
|---|----------|--------|---------|----------|------|-------|
| S1 | У вороны есть лапки. + "Лапки — часть тела этой вороны." | V2 | UNRESOLVED | [V1,V2] | NO_GROUNDED_CANDIDATE | C2 |
| S2 | У стола есть ножки. + "Ножки — часть этого стола." | V2 | UNRESOLVED | [V2,V1] | NO_GROUNDED_CANDIDATE | C2 |
| S3 | У меня есть книга. | V1 | RESOLVED | [V1] | — | C1 ✓ |
| S4 | Ворона обладает перьями. + "Перья — часть тела этой вороны." | V2 | UNRESOLVED | [V1,V2] | NO_GROUNDED_CANDIDATE | C2 |
| S5 | У вороны лапки. | V2 | UNRESOLVED | [V2,V1] | NO_GROUNDED_CANDIDATE | C2 |
| S6 | Вороны любят червей. | V4 | RESOLVED | [V4] | — | C1 ✓ |

### Determinism probe + corrected stability picture (S1–S6 baseline, 3 repeats each)
A follow-up A/B revealed **gemma-3n-e4b-it is NOT deterministic through LM Studio even at temperature=0**: S1 flipped between `RESOLVED [V2]` (first harness run) and `UNRESOLVED {V1,V2}` (later runs, 4/4). So single-run C1/C2 counts are **noisy**; the first run's "C1=5" was sampling luck. Re-running each baseline sentence ×3 gives the stable picture:

| # | target | rep0 | rep1 | rep2 | stable class |
|---|--------|------|------|------|--------------|
| S1 | V2 | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | honest-ambiguous |
| S2 | V2 | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | honest-ambiguous |
| S3 | V1 | RESOLVED [V1] ✓ | RESOLVED [V1] ✓ | RESOLVED [V1] ✓ | resolved-correct |
| S4 | V2 | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | honest-ambiguous |
| S5 | V2 | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | honest-ambiguous |
| S6 | V4 | RESOLVED [V4] ✓ | RESOLVED [V4] ✓ | RESOLVED [V4] ✓ | resolved-correct |

**Corrected stable baseline: 2/6 resolve correctly (S3, S6); 4/6 are stably honest-ambiguous {V1,V2} (S1,S2,S4,S5); 0 wrong-meaning across all 18 runs.** The model cannot reliably distinguish HAVE from HAS_PART on "у X есть Y" — a real capability gap on this model, reported honestly rather than force-fit.

### Findings (S1–S6)
- **Safety holds robustly: 0 wrong-meaning committed across all 18 runs.** The model never commits a semantically wrong predicate; when unsure it reports honest incompleteness. This is the critical invariant and it held live even under non-determinism.
- **Non-determinism at temperature=0** (see probe above) → single-run metrics are unreliable; characterize behavior with N repeats + consensus, not one shot.
- **Protocol compliance on the core set is perfect (6/6 strict JSON)** — gemma-3n-e4b-it honors the bounded-selection protocol on S1–S6.
- **Contextual augmentation does NOT currently disambiguate.** Adding F1/F2/F3 *reduced* resolved count (5→2). Root cause is architectural, not a bug: contextual statements are recorded as **slot-level C grounds** (`Ground("C", ..., value=None)`), and the model still reports MULTIPLE_ADMISSIBLE {V1,V2}; per Rev7b T4, AMBIGUOUS requires *every* survivor to have its own value-specific positive ground, otherwise UNRESOLVED. Since no context fact maps to a specific value (that mapping is the deferred lexical-semantic step), augmented can only add ungrounded alternatives → honest incompleteness. **The intended "augmented resolves what baseline cannot" benefit is not yet delivered** — it needs value-specific context grounding (deferred capability). Recorded as a known limitation, not a defect in the current contract.
- S5 (copula-less "У вороны лапки.") is UNRESOLVED with target V2 preserved in both modes → correct honest behavior for the genuinely ambiguous form.

## 2. §2.3 coverage + arbitrary examples (`verify_gemma.py`, LMStudioSelector, attempts_per_slot=2)
```
S1 base | outcome=UNRESOLVED selected=[V1,V2] diag=[NO_GROUNDED_CANDIDATE]
S1 aug  | outcome=UNRESOLVED selected=[V1,V2] diag=[NO_GROUNDED_CANDIDATE]
S3 base | outcome=RESOLVED   selected=[V1]
S4 aug  | outcome=UNRESOLVED selected=[V1,V2] diag=[NO_GROUNDED_CANDIDATE]
ARB locative   ('Ворона сидит на ветке.')      | PROTOCOL_ERROR
ARB like       ('Вороны любят червей.')        | RESOLVED [V4]
ARB out-of-set ('Ворона поёт громко и весело.')| PROTOCOL_ERROR

§2.3 coverage: sentences=7 answered=2 proven_outcomes=2 ratio=0.29
honest_gaps={}  provider_failures={'PROTOCOL_ERROR': 4}
```
### Findings (verify_gemma)
- **Protocol compliance degrades on harder / out-of-set inputs.** The core S1–S6 were 6/6, but the ARB locative and out-of-set sentences returned `PROTOCOL_ERROR` (model did not emit valid strict JSON). So protocol reliability is input-dependent: strong on the in-distribution demo set, weaker on novel/out-of-set text.
- **Driver discrepancy on S1 baseline** — a reproducibility concern to root-cause:
  - `run_formalizer_real_backend.py` (RealBackendSelector, attempts=1): S1 base → **RESOLVED [V2]**.
  - `verify_gemma.py` (LMStudioSelector, attempts=2): S1 base → **UNRESOLVED [V1,V2]**.
  Same model + sentence, different outcome. Likely causes: two different selector classes build different prompts; and/or gemma non-determinism despite temperature=0; and/or the retry path. Needs a controlled A/B to pin down (same prompt, same selector, N repeats).

## 3. Open-set probe → verification (`run_open_set_live.py`)
```
gate fired (>=3 distinct synthetic NO_CANDIDATE)
POSITIVE (shared predicate):   no verified proposal (EMPTY_PROPOSAL)
HETEROGENEOUS (melt/boil/burn): no verified proposal (EMPTY_PROPOSAL)
nothing auto-applied; schema extension is a separate explicit acceptance act.
```
### Findings (open-set)
- The gate fires correctly on accumulated misses, and the live probe + verification path runs end-to-end without auto-applying anything (correct: extension stays an explicit acceptance act).
- **Both probe cases returned EMPTY_PROPOSAL** — gemma did not produce a verifiable new value under the current prompt. So open-set *value generation* is not yet yielding usable proposals on this model.
- The script itself flags a real design limitation: grounding checks against **ANY single** miss input, so heterogeneous misses can over-generalize (e.g. 'MELTS' from one shared word). A stricter "grounded in all/most" check is the candidate refinement — not yet applied.

## 3b. Canonical production driver (`p1_real_run.py`, real `LMStudioBackend` native path)
After the §0b transport fix, the canonical Phase 1 driver runs end-to-end on gemma-3n-e4b-it:
```
baseline : S1=C1  S2=C1  S3=C1  S4=C1  S5=C2  S6=C1   (5/6 resolved-correct, 0 C3)
augmented: S1=C2  S2=C2  S3=C1  S4=C2  S5=C2  S6=C1   (2/6 resolved-correct, 0 C3)
mechanism passed (no C3): YES
```
- **Safety holds on the production path too: 0 wrong-meaning (C3) in both modes.**
- Baseline resolves 5/6 here vs 2/6 stable in the ad-hoc determinism probe (§1) — same nominal settings, different outcomes across drivers/runs. This is the **non-determinism** finding made concrete: single-run C1 counts are not reproducible; only the no-C3 safety invariant and the honest-incompleteness behavior (S5 always C2) are stable.
- Augmented again does NOT disambiguate (S1/S2/S4 flip to C2), consistent with §1's slot-level-C-ground limitation.

## 4. Summary of live status
| mechanic | live-exercised | result |
|----------|----------------|--------|
| S1–S6 bounded selection (baseline) | yes | safe (0 wrong / 18 runs); **2/6 stably resolved** (S3,S6), 4/6 honest-ambiguous {V1,V2}; non-deterministic at temp=0; 6/6 protocol on core set |
| S1–S6 contextual augmentation | yes | safe but does NOT disambiguate (slot-level C grounds only) — known limitation |
| §2.3 coverage + ARB examples | yes | protocol degrades on novel/out-of-set (PROTOCOL_ERROR); driver discrepancy on S1 base |
| open-set probe → verification | yes | gate fires; EMPTY_PROPOSAL both cases; over-generalization limitation noted |
| canonical production driver (p1_real_run) | yes (after §0b fix) | 0 C3 both modes; baseline 5/6, augmented 2/6; non-determinism confirmed across drivers |

## 7. Model A/B: qwen3.8-27b vs gemma-3n-e4b-it (same server, same harness)
The agent's own model (`qwen3.8-27b-nvfp4-q5k-no-mtp`, `PI_PROVIDER=kripl-local`) is served on the
**same LM Studio instance** (127.0.0.1:1234) as gemma. So I ran the identical harness
(`run_formalizer_real_backend.py` / inline N=3 driver, OpenAI-compat `chat_completions`, temp=0,
no thinking/context) with **my model substituted for gemma** — one server, one client path, same prompts;
only the model differs. This is a capability comparison (not deployment-equivalent: qwen was called
through the compat endpoint, not the native path).

### Consensus (N=3 per case; every case 3/3 identical for qwen)
| case | target | gemma (stable) | qwen baseline | qwen augmented |
|------|--------|----------------|---------------|----------------|
| S1 у X есть лапки | HAS_PART | UNRESOLVED {V1,V2} | **RESOLVED V2 ✓** | RESOLVED V2 ✓ |
| S2 у стола есть ножки | HAS_PART | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | **RESOLVED V2 ✓ (+ctx)** |
| S3 у меня есть книга | HAVE | RESOLVED V1 ✓ | RESOLVED V1 ✓ | RESOLVED V1 ✓ |
| S4 ворона обладает перьями | HAS_PART | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} | UNRESOLVED {V1,V2} ✗(ctx no help) |
| S5 у вороны лапки (no copula) | HAS_PART | UNRESOLVED {V1,V2} | **RESOLVED V2 ✓** | UNRESOLVED {V1,V2} (ctx hurts!) |
| S6 вороны любят червей | LIKE | RESOLVED V4 ✓ | RESOLVED V4 ✓ | RESOLVED V4 ✓ |

Totals: gemma stable **2/6**; qwen baseline **4/6**; qwen augmented **5/6**. **0 wrong-meaning for both models in every run.**

### Findings (model A/B)
- **Qwen is deterministic at temp=0** — 3/3 identical per case. The non-determinism problem flagged for gemma (§1) does NOT affect qwen; its measurements are reproducible. This alone makes qwen a far better validation substrate.
- **Clear capability gain:** qwen resolves 4/6 baseline vs gemma's stable 2/6, including **S5 (zero-copula "У вороны лапки.")** which gemma never resolved in any run.
- **Contextual augmentation is NOT monotonically helpful.** For qwen it *fixes* S2 (C2→C1) but *breaks* S5 (C1→C2): adding the part-whole statement makes the copula-less form report {V1,V2} instead of committing to V2. And **neither model can fix S4** with context ("обладает перьями" + explicit part-statement stays ambiguous). So the intended "augmented resolves what baseline cannot" benefit is real but partial and case-dependent — a genuine finding, not a clean win.
- **The safety invariant is model-robust:** 0 wrong-meaning across both models in every run. The mechanism's core guarantee (never commit a semantically wrong predicate) holds regardless of which model sits behind the seam — exactly what a sound design should give.

**Conclusion for the "model is the bottleneck" question (§5 of my assessment):** confirmed and quantified. Swapping gemma→qwen on the *unchanged* mechanism raises stable resolution 2/6 → 4/6 (baseline) / 5/6 (augmented), makes results reproducible, and leaves safety intact. The residual gaps (S4 for both; S5-with-context for qwen) are specific lexical-semantic cases — the deferred value-specific grounding work, not a mechanism defect.

## 5. Not yet live-exercised (need a runtime/agent-loop driver)
The recent native-path commits added inference/runtime mechanics that the perception-level drivers above do not reach: counterfactual questions, window aggregates, phrase senses over complete lexical anchors, restricted numeric bodies, scoped queries / grounded references, atomic V7 migration tooling, native query trees + temporal operands, SyntaxRules AST + compound SOM proposition arguments, dialogue clarification + source correction. These need a runtime-level live harness (agent loop with goals/queries) to validate on the model — see follow-up plan.

## 6. Artifacts
- Raw logs: `/tmp/gemma_s1s6.log`, `/tmp/gemma_openset.log`, `/tmp/gemma_verify.log`, `/tmp/gemma_p1.log`
- Uncommitted changes from this validation:
  - `src/ah/llm/lmstudio_client.py` — native_chat top_k + reasoning fixes (§0b, real production bug)
  - `scripts/run_formalizer_real_backend.py`, `scripts/run_open_set_live.py` — harness interface fix (§0)
  - `p1_real_run_report.txt` — regenerated by the live run
- Regression check: full formalizer+LLM sweep identical with/without changes (47F+69E pre-existing).
