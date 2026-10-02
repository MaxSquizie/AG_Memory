# -*- coding: utf-8 -*-
"""WP2.3 — T6 claim + admission decision (V7 §7.3): the single-writer gate before any plan is applied.

``claim`` encodes the mandatory, atomic claim step that runs on EVERY T6 call and precedes plan\\E / terminal
append:

* an unprocessed record with a smaller unprocessed global seq -> ``PENDING_ADMISSION_ORDER`` (no journal writes,
  no terminal status, AH unchanged; the record stays unprocessed until its head-call or recovery-drain);
* an already-terminal record repeat -> idempotent no-op;
* a reached-head batch whose pair already has a COMMITTED marker: matching ``batch_hash`` -> idempotent completion
  without re-ops; MISMATCHING hash -> ``INTEGRITY_ERROR`` (commit forbidden, investigation-only) and the record's
  journal entry is assigned terminal ``REJECTED_COMMIT_ELIGIBILITY``;
* no marker yet: a foreign run_id (per InterpretationRunBinding) or an already-closed version -> terminal
  ``REJECTED_COMMIT_ELIGIBILITY`` without AH change; otherwise the global head is admitted to proceed.

``STALE_SUPERSEDED`` is created ONLY here, on plan-check failure of the global head (§7.3 step 1); recovery skips a
stale record and continues draining the next head (§8.3 step 3). Pure module: it returns decisions for the caller;
it performs no store writes itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .run_binding import InterpretationRunBinding


@dataclass(frozen=True)
class JournalRecord:
    """A journal record as seen by the claim step."""

    seq: int
    batch_id: str
    run_id: str
    observation_id: str
    version: int
    batch_hash: str
    terminal: str | None = None   # APPLIED / REJECTED_* / STALE_SUPERSEDED, or None if unprocessed


@dataclass(frozen=True)
class ClaimDecision:
    """The deterministic outcome of one T6 claim."""

    outcome: str                 # PENDING_ADMISSION_ORDER | IDEMPOTENT_NOOP | INTEGRITY_ERROR | REJECTED_COMMIT_ELIGIBILITY | ADMIT
    blocking_seqs: tuple[int, ...] = ()
    terminal_status: str | None = None   # assigned to the record now (if any)


def _unprocessed(records: Sequence[JournalRecord]) -> list[JournalRecord]:
    return [r for r in records if r.terminal is None]


def claim(
    record: JournalRecord,
    all_records: Sequence[JournalRecord],
    committed_markers: Mapping[tuple[str, int], str],
    binding: InterpretationRunBinding,
) -> ClaimDecision:
    """Run the mandatory T6 claim for ``record``; return the decision (no store writes)."""

    # (1) An already-terminal record repeat is an idempotent no-op.
    if record.terminal is not None:
        return ClaimDecision(outcome="IDEMPOTENT_NOOP", terminal_status=record.terminal)

    unprocessed = _unprocessed(all_records)
    min_seq = min((r.seq for r in unprocessed), default=None)

    # (2) A smaller unprocessed global seq exists -> PENDING_ADMISSION_ORDER (nothing written, AH unchanged).
    if min_seq is not None and record.seq > min_seq:
        blocking = tuple(sorted(r.seq for r in unprocessed if r.seq < record.seq))
        return ClaimDecision(outcome="PENDING_ADMISSION_ORDER", blocking_seqs=blocking)

    # (3) ``record`` is the global head. Check the pair's COMMITTED marker first.
    marker_hash = committed_markers.get((record.observation_id, record.version))
    if marker_hash is not None:
        if marker_hash == record.batch_hash:
            return ClaimDecision(outcome="IDEMPOTENT_NOOP")  # idempotent completion; no re-ops
        # Mismatching hash -> INTEGRITY_ERROR; commit forbidden (investigation-only); terminal assigned.
        return ClaimDecision(outcome="INTEGRITY_ERROR", terminal_status="REJECTED_COMMIT_ELIGIBILITY")

    # (4) No marker yet: foreign run_id / already-closed version -> REJECTED_COMMIT_ELIGIBILITY without AH change.
    holder = binding.holder(record.observation_id, record.version)
    if holder is not None and holder != record.run_id:
        return ClaimDecision(outcome="REJECTED_COMMIT_ELIGIBILITY", terminal_status="REJECTED_COMMIT_ELIGIBILITY")

    # (5) The global head with a clean claim proceeds to plan\E + terminal append.
    return ClaimDecision(outcome="ADMIT")


def drain_order(records: Sequence[JournalRecord]) -> tuple[int, ...]:
    """§7.3 step 1 / §8.3 step 3 — the recovery-drain order: unprocessed records by ascending seq (head first).

    A STALE_SUPERSEDED record is skipped (it never re-applies); already-terminal records are not drained."""
    return tuple(sorted(r.seq for r in _unprocessed(records)))


def mark_stale(record: JournalRecord) -> JournalRecord:
    """§7.3 step 1 — the ONLY place STALE_SUPERSEDED is created: on plan-check failure of the global head."""
    if record.terminal is not None:
        return record
    return JournalRecord(
        seq=record.seq, batch_id=record.batch_id, run_id=record.run_id,
        observation_id=record.observation_id, version=record.version,
        batch_hash=record.batch_hash, terminal="STALE_SUPERSEDED",
    )
