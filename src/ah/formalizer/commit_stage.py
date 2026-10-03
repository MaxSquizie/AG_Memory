# -*- coding: utf-8 -*-
"""Commit stage (T5/T6) — the ONLY place anything is written to memory.

Wires the pure pieces into one durable, idempotent commit flow (I25: nothing writes before this):

    FormalizationState --assemble_ir--> CandidateIR  (the only exit of the formalizer)
        -> T6 head-only admission (t6_core.head_only_admission)
        -> plan\\E = admitted ∪ closure ∪ common ops   (t6_core.compute_plan_E)
        -> batch_hash (idempotency key) + MaterializationMarker(observation, version)
        -> store.commit_transaction(ops, marker, decision)   [atomic: E+marker+D]
        -> terminal outcome journaled (APPLIED / REJECTED_* / STALE_SUPERSEDED)

A run that is NOT admitted at the head still preserves its common observation op but writes no
version-specific assertions — so a losing concurrent run leaves no half-materialized facts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Sequence

from .composition import assemble_ir
from .state import FormalizationState
from .store_interface import (
    CommitDecision,
    MaterializationMarker,
    Store,
    StoreOp,
    TerminalOutcome,
)
from .t6_core import PlanOp, PendingBatch, compute_plan_E, head_only_admission, select_terminal_outcome


@dataclass(frozen=True)
class CommitReport:
    admitted_at_head: bool
    applied: bool                 # did the store accept this transaction?
    batch_hash: str
    n_ops: int
    terminal: TerminalOutcome


def _ops_from_ir(ir) -> list[PlanOp]:
    """Derive plan\\E descriptors from the IR.

    The observation record is a COMMON op (always preserved). Each predicate frame and each
    semantic graph is a version-specific E op depending on the observation it materializes."""
    ops: list[PlanOp] = [PlanOp(uid=f"obs:{ir.observation_id}", in_E=False)]
    for fid in ir.predicate_frames:
        ops.append(PlanOp(uid=f"frame:{fid}", deps=(f"obs:{ir.observation_id}",), in_E=True))
    for i, g in enumerate(ir.semantic_candidates):
        gid = g.graph_id or f"G{i + 1}"
        frame_deps = tuple(f"frame:{fid}" for fid in ir.predicate_frames)
        ops.append(PlanOp(uid=f"graph:{gid}", deps=frame_deps or (f"obs:{ir.observation_id}",), in_E=True))
    return ops


def _batch_hash(ir, run_id: str) -> str:
    """Idempotency key: canonical serialization of the IR + run identity."""
    payload = {
        "observation_id": ir.observation_id,
        "interpretation_version": ir.interpretation_version,
        "run_id": run_id,
        "lexical_units": list(ir.lexical_units),
        "predicate_frames": list(ir.predicate_frames),
        "ambiguity_sets": [list(a) for a in ir.ambiguity_sets],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def commit(
    state: FormalizationState,
    store: Store,
    *,
    run_id: str,
    pending: Sequence[PendingBatch] = (),
    superseded: bool = False,
) -> CommitReport:
    """Run the full commit stage for one interpretation of one observation."""
    ir = assemble_ir(state)

    # T6 admission: is THIS run at the head of the pending order?
    this_batch = PendingBatch(batch_id=run_id, seq=min((b.seq for b in pending), default=-1))
    admitted, _rejected = head_only_admission(list(pending) + [this_batch])
    admitted_at_head = admitted is not None and admitted.batch_id == run_id

    ops_desc = _ops_from_ir(ir)
    admitted_uids = {o.uid for o in ops_desc if o.in_E} if admitted_at_head else set()
    plan_ops = compute_plan_E(ops_desc, admitted_uids)

    batch_hash = _batch_hash(ir, run_id)
    marker = MaterializationMarker(observation_id=ir.observation_id, interpretation_version=ir.interpretation_version)
    outcome = select_terminal_outcome(admitted_at_head=admitted_at_head, superseded=superseded)
    decision = CommitDecision(
        run_id=run_id, batch_hash=batch_hash, marker=marker, ops_digest=batch_hash[:16], outcome=outcome,
    )

    result = store.commit_transaction(plan_ops, marker, decision)
    applied = not result.idempotent_noop   # a fresh write, not an idempotent re-commit
    # The run's fate is set by admission + supersession (select_terminal_outcome); a store-level
    # idempotency no-op does not change it. ``applied`` separately reports store acceptance.
    terminal = outcome
    # Key the terminal by the batch identity (batch:<hash>) — the SAME key recover_from_head looks up
    # (§7.3 DR15). A complete commit's terminal is then found on restart, so an already-APPLIED batch is
    # NOT double-restored; a crash before this line leaves no terminal and recovery surfaces it from D.
    if applied:
        store.append_terminal(f"batch:{batch_hash}", terminal)
    return CommitReport(admitted_at_head=admitted_at_head, applied=applied, batch_hash=batch_hash,
                       n_ops=len(plan_ops), terminal=terminal)
