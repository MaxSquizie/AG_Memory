# -*- coding: utf-8 -*-
"""End-to-end vertical — a THIN orchestrator composing the proven modules.

This is deliberately small and delegates every heavy step to an already-unit-tested module, so no
new monolith appears (the "no new monoliths" discipline):

    pipeline.run   -> T0..T4 FormalizationState          (proven core)
    assemble_ir    -> immutable CandidateIR             (only exit of the formalizer)
    rx_cache.rank  -> reorder admissible semantic candidates by experience (NEVER excludes, §5.10)
    commit_stage   -> the ONLY write path (T5/T6)       (crash-stop durable + idempotent)
    goal_executor  -> compile canonical AssociationGoals (§5.9)

The span->Ref resolver is injected: production wires it to the store's committed uids; tests inject a
dict-backed one. The vertical never fabricates refs itself — an unresolvable mention simply yields no
goal (the reader contract / goal executor enforce that).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .composition import assemble_ir
from .commit_stage import CommitReport, commit
from .goal_executor import CompiledGoal, goals_from_ir
from .pipeline import run as _run_t0_t4
from .rx_cache import FormalizationCache
from .state import Budget, FormalizationState


@dataclass(frozen=True)
class VerticalReport:
    state: FormalizationState
    ir: object                       # CandidateIR
    ranked_semantic_ids: tuple[str, ...]   # R-X reordered; always a permutation of the candidates
    commit: CommitReport
    goals: tuple[CompiledGoal, ...]


def run_vertical(
    text: str, *, schema, selector, store, morph=None, context_facts=(), budget: Budget | None = None,
    memory_mentions=(), rx: FormalizationCache | None = None, ref_map: dict | None = None,
    run_id: str = "run-1", pending: Sequence = (),
) -> VerticalReport:
    state = _run_t0_t4(text, schema, selector, morph=morph, context_facts=context_facts,
                       budget=budget, memory_mentions=memory_mentions)
    ir = assemble_ir(state)

    cand_ids = [g.graph_id or f"G{i + 1}" for i, g in enumerate(ir.semantic_candidates)]
    if rx is not None and cand_ids:
        ranked = tuple(rx.rank("R-X3", cand_ids, {"observation_id": state.source_uid}))
    else:
        ranked = tuple(cand_ids)

    commit_rep = commit(state, store, run_id=run_id, pending=pending)

    resolve: Callable[[str], object] = (ref_map.get if ref_map is not None else lambda _s: None)
    goals = tuple(goals_from_ir(ir, resolve, text=text))
    return VerticalReport(state=state, ir=ir, ranked_semantic_ids=ranked, commit=commit_rep, goals=goals)
