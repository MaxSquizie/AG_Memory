# -*- coding: utf-8 -*-
"""Pure T6 decisions — store-agnostic logic testable on any Store double.

These functions depend only on :mod:`store_interface` types, so they run identically
on the in-memory double (fast unit tests) and against the AH adapter (crash-stop runs).
They encode three V7 §7.3/§6.3 decisions:

* head-only admission (§6.3 PENDING_ADMISSION_ORDER): only the batch at the head of
  the pending order is admitted; concurrent batches behind it are rejected as conflict.
* plan\\E computation (§7.3): the commit plan = admitted ops ∪ their transitive
  dependency closure ∪ common (non-E) ops, which are always preserved.
* terminal-outcome selection (§7.3/§8): APPLIED vs REJECTED_CONFLICT_ADMISSION vs
  STALE_SUPERSEDED from admission + supersession facts.

No AH import here: this is the seam both store implementations share.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .store_interface import StoreOp, TerminalOutcome


@dataclass(frozen=True)
class PendingBatch:
    """A batch waiting for admission, positioned by its journal seq."""

    batch_id: str
    seq: int
    run_id: str = ""


@dataclass(frozen=True)
class PlanOp:
    """Descriptor used to compute plan\\E (independent of concrete store ops)."""

    uid: str
    deps: tuple[str, ...] = ()   # uids this op depends on (transitive closure taken)
    in_E: bool = True            # True = version-specific E op; False = common (always kept)


def head_only_admission(pending: Sequence[PendingBatch]) -> tuple[PendingBatch | None, tuple[str, ...]]:
    """Admit only the batch at the head of the pending order.

    Order is by journal seq (ties broken by batch_id for determinism). The earliest
    unprocessed batch is admitted; every other concurrent batch is rejected as a
    conflict admission. Returns ``(admitted | None, rejected_batch_ids)``.
    """
    if not pending:
        return None, ()
    ordered = sorted(pending, key=lambda b: (b.seq, b.batch_id))
    admitted = ordered[0]
    rejected = tuple(b.batch_id for b in ordered[1:])
    return admitted, rejected


def compute_plan_E(ops: Sequence[PlanOp], admitted_uids) -> tuple[StoreOp, ...]:
    """Compute plan\\E = admitted ∪ transitive-closure(admitted) ∪ common ops.

    Common (``in_E=False``) operations are always preserved regardless of admission.
    Version-specific E ops enter only if admitted or reachable as a dependency of an
    admitted op. Output preserves input order and is de-duplicated by uid.
    """
    by_uid = {o.uid: o for o in ops}
    included: set[str] = set()

    stack = list(admitted_uids)
    while stack:
        u = stack.pop()
        if u in included or u not in by_uid:
            continue
        included.add(u)
        stack.extend(by_uid[u].deps)

    for o in ops:
        if not o.in_E:
            included.add(o.uid)

    return tuple(StoreOp(op_type="MUTATE", payload={"uid": o.uid}) for o in ops if o.uid in included)


def select_terminal_outcome(*, admitted_at_head: bool, superseded: bool) -> TerminalOutcome:
    """Pick the terminal outcome from admission + supersession facts (§7.3/§8)."""
    if not admitted_at_head:
        return TerminalOutcome.REJECTED_CONFLICT_ADMISSION
    if superseded:
        return TerminalOutcome.STALE_SUPERSEDED
    return TerminalOutcome.APPLIED
