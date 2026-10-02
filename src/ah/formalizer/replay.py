# -*- coding: utf-8 -*-
"""WP3.4 — End-to-end replay determinism + StageTimingLog (V7 §0.8/§9).

Replay contract: identical reproducible input under the same ``canonical_run_id`` yields a structurally identical output through the whole
pipeline; comparison is structural via a canonical hash, never textual. A fresh run id of the same input is an independent recomputation
(never served from another run's cache — enforced upstream by the provider adapter's integrity check).

``StageTimingLog`` records per-stage budget consumption and reports exhaustion deterministically: once the accumulated cost would exceed
the budget, the pipeline stops at that stage with a stable ``BUDGET_EXHAUSTED`` outcome (not an arbitrary partial result), so two runs of
an over-budget input agree on both the outcome and the recorded stages.

Pure module; reuses the canonical hash from the oracle harness for structural comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ah.formalizer.oracle import canonical_hash


@dataclass(frozen=True)
class StageTiming:
    stage: str
    budget_used: int


class StageTimingLog:
    def __init__(self, budget: int):
        self.budget = budget
        self.entries: list[StageTiming] = []

    @property
    def total(self) -> int:
        return sum(e.budget_used for e in self.entries)

    @property
    def exhausted(self) -> bool:
        return self.total > self.budget

    def record(self, stage: str, budget_used: int) -> None:
        self.entries.append(StageTiming(stage, budget_used))

    def to_dict(self) -> dict:
        """Deterministic serialization (stable ordering = recording order)."""
        return {"budget": self.budget, "stages": [[e.stage, e.budget_used] for e in self.entries],
                "total": self.total, "exhausted": self.exhausted}


class DeterministicPipeline:
    """A stand-in for the full T0-T4 pipeline that consumes a declared per-stage budget; used to prove replay determinism end-to-end."""

    def __init__(self, stages, budget: int):
        self.stages = list(stages)          # [(stage_name, cost), ...] in execution order
        self.budget = budget

    def run(self, text: str, run_id: str) -> dict:
        log = StageTimingLog(self.budget)
        out = {"run_id": run_id, "text": text}
        for name, cost in self.stages:
            if log.total + cost > self.budget:
                out["outcome"] = "BUDGET_EXHAUSTED"     # deterministic stop at the first unaffordable stage
                out["stage_timing"] = log.to_dict()
                return out
            log.record(name, cost)
        out["outcome"] = "COMPLETED"
        out["stage_timing"] = log.to_dict()
        return out


class ReplayHarness:
    def __init__(self, pipeline: DeterministicPipeline):
        self.pipeline = pipeline

    def run_pair(self, text: str, run_id_a: str, run_id_b: str | None = None) -> dict:
        a1 = self.pipeline.run(text, run_id_a)
        a2 = self.pipeline.run(text, run_id_a)          # same canonical_run_id again
        result = {
            "a": a1,
            "a_repeat": a2,
            "identical_within_run": canonical_hash(a1) == canonical_hash(a2),
            "hash_a": canonical_hash(a1),
        }
        if run_id_b is not None:                       # an independent recomputation under a fresh run id
            b = self.pipeline.run(text, run_id_b)
            result["b"] = b
            # compare the semantic outcome (run_id tag excluded by construction — it differs by definition)
            norm_a = dict(a1); norm_a.pop("run_id", None)
            norm_b = dict(b); norm_b.pop("run_id", None)
            result["independent_run_same_outcome"] = canonical_hash(norm_a) == canonical_hash(norm_b)
        return result


if __name__ == "__main__":  # pragma: no cover - quick sanity
    p = DeterministicPipeline([("T0", 2), ("T1", 3)], budget=5)
    print(ReplayHarness(p).run_pair("hello", "run-1"))
