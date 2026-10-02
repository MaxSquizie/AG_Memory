# -*- coding: utf-8 -*-
"""WP2.2 — T5 batch + journal (V7 §7.2): the commit gate that decides what may be materialized.

T5 evaluates, per fragment, the FIVE commit conditions and journals the outcome durably before any
canonical fact is written by T6:

    (i)  generation completed on the current input versions;
    (ii) no pending reads — a declared read whose source version changed after the snapshot, or that was
         RESOURCE_MISSING at resolution, makes the fragment non-materializable: it stays PROVISIONAL with
         WAITING_CONTEXT + subscription and is recomputed on the new version (perturbation A27);
    (iii) dependencies resolved OR represented as linked alternatives with constraint edges;
    (iv) integrity passed — epistemic guard, closure IR, Argument.kind/RoleRegistry mapping; every OPEN_LEXICAL
         has a full lexical anchor/source alignment, unique isolation key, valid OpenTemplatePolicy and closed
         roles/scope. A broken known TemplateMap is NOT bypassed via the open path (§7.1);
    (v)  truth-ground requirement — every fact slot has at least one O/C/W ground; R/D/M/A/P are only
         interpretation grounds and never assert a fact by themselves (§7.4).

All five true AND outcome RESOLVED -> the fragment enters the batch (materialized downstream by T6). A failed
condition is journaled as a durable ``resolution_log`` entry naming the CONDITION NUMBER (not an error); a
non-RESOLVED outcome yields an ObservationRecord WITHOUT a canonical fact. Commit eligibility (§0.8) is checked
against the durable InterpretationRunBinding BEFORE any batch write; a foreign owner -> INTEGRITY_ERROR, and an
investigation-only run emits candidate audit but never a canonical fact. A pre-existing marker of another run is
an early refusal (not journaled). Re-running T5 with the same batch_hash is idempotent.

Pure module: it returns durable journal entries for the caller to append; it performs no store writes itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .run_binding import InterpretationRunBinding


# --------------------------------------------------------------------------- #
# Inputs / outputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FragmentT5Input:
    """Everything T5 needs to gate one fragment (produced by C + the pipeline)."""

    fragment_id: str
    outcome: str                       # RESOLVED | AMBIGUOUS | UNRESOLVED | INSUFFICIENT_CONTEXT | NO_CANDIDATE
    generation_complete: bool = True   # condition (i)
    pending_reads: tuple[str, ...] = ()  # condition (ii): non-empty -> WAITING_CONTEXT
    dependencies_resolved: bool = True  # condition (iii)
    integrity_ok: bool = True          # condition (iv)
    truth_grounds: tuple[str, ...] = ()  # condition (v): O/C/W grounds; must be non-empty for a fact
    known_mapping_missing: bool = False  # C returned CANONICAL_MAPPING_MISSING -> refuse this fragment
    candidate_source_exhausted: bool = False  # NO_CANDIDATE after ALL permitted sources checked


@dataclass(frozen=True)
class T5Result:
    """The deterministic outcome of one T5 pass."""

    batch_hash: str
    eligibility: str                 # OK | INTEGRITY_ERROR | MARKER_REFUSED | INVESTIGATION_ONLY
    committed_fragments: tuple[str, ...] = ()   # all five true + RESOLVED -> materialized by T6
    journal_entries: tuple[dict, ...] = field(default_factory=tuple)  # durable records to append
    idempotent: bool = False         # True when this batch_hash was already journaled (no duplicate written)


# --------------------------------------------------------------------------- #
# Per-fragment condition evaluation
# --------------------------------------------------------------------------- #
def evaluate_fragment(f: FragmentT5Input):
    """Return ``(committable, code)``.

    ``code`` is None for a committable fragment; otherwise it names the FIRST failing T5 condition (COND_1..COND_5),
    a refusal (CANONICAL_MAPPING_MISSING / CANDIDATE_SOURCE_EXHAUSTED), or the non-RESOLVED outcome itself."""
    if f.known_mapping_missing:
        return False, "CANONICAL_MAPPING_MISSING"
    if f.outcome != "RESOLVED":
        # A non-RESOLVED semantic outcome is not a failed T5 condition; it yields an ObservationRecord only.
        return False, f.outcome
    if not f.generation_complete:
        return False, "COND_1"
    if f.pending_reads:
        return False, "COND_2"  # WAITING_CONTEXT + subscription; recompute on the new version (A27)
    if not f.dependencies_resolved:
        return False, "COND_3"
    if not f.integrity_ok:
        return False, "COND_4"
    if not f.truth_grounds:
        return False, "COND_5"  # no O/C/W truth ground -> the fact is not asserted
    return True, None


def _batch_hash(observation_id: str, version: int, fragments: Sequence[FragmentT5Input]) -> str:
    payload = {
        "observation_id": observation_id,
        "version": version,
        "fragments": sorted(
            (f.fragment_id, f.outcome, f.generation_complete, list(f.pending_reads),
             f.dependencies_resolved, f.integrity_ok, tuple(f.truth_grounds))
            for f in fragments
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def t5_batch(
    fragments: Sequence[FragmentT5Input],
    *,
    run_id: str,
    observation_id: str,
    version: int,
    binding: InterpretationRunBinding,
    marker_exists: bool = False,
    investigation_only: bool = False,
    existing_batch_hashes: frozenset[str] = frozenset(),
) -> T5Result:
    """Gate one interpretation's fragments for commit; return the deterministic result + durable journal entries."""

    # (1) Commit eligibility (§0.8): check run_id against the durable binding BEFORE any batch write.
    holder = binding.holder(observation_id, version)
    if holder is not None and holder != run_id:
        # A different owner holds this interpretation version -> INTEGRITY_ERROR; no canonical fact, AH unchanged.
        return T5Result(batch_hash=_batch_hash(observation_id, version, fragments), eligibility="INTEGRITY_ERROR")

    # (2) Marker early refusal (§7.2): another run's COMMITTED marker already present at T5 -> refuse immediately,
    #     NOT journaled (the terminal refusal happens later at the normal T6 claim / recovery-admission).
    if marker_exists:
        return T5Result(batch_hash=_batch_hash(observation_id, version, fragments), eligibility="MARKER_REFUSED")

    bhash = _batch_hash(observation_id, version, fragments)

    # (3) Idempotency: the same batch already journaled -> no duplicate entries.
    if bhash in existing_batch_hashes:
        return T5Result(batch_hash=bhash, eligibility="OK", idempotent=True)

    # (4) Investigation-only run (§0.8): identical inputs may emit candidate audit but never a canonical fact.
    if investigation_only:
        entries = [
            {"kind": "candidate_audit", "fragment_id": f.fragment_id, "outcome": f.outcome} for f in fragments
        ]
        return T5Result(batch_hash=bhash, eligibility="INVESTIGATION_ONLY", journal_entries=tuple(entries))

    # (5) Evaluate every fragment; journal the non-committed ones durably.
    committed: list[str] = []
    entries: list[dict] = []
    for f in fragments:
        committable, code = evaluate_fragment(f)
        if committable:
            committed.append(f.fragment_id)
            continue
        if code and code.startswith("COND_"):
            # A failed T5 condition is a durable resolution_log entry naming the CONDITION NUMBER (not an error).
            entries.append({"kind": "resolution_log", "fragment_id": f.fragment_id, "condition": code})
        elif code == "CANONICAL_MAPPING_MISSING":
            # §7.2 known-mapping refusal: durable record; fragment excluded from the batch, T6 not called for it.
            entries.append({"kind": "resolution_log", "fragment_id": f.fragment_id,
                           "code": "CANONICAL_MAPPING_MISSING"})
        elif code == "CANDIDATE_SOURCE_EXHAUSTED" or (f.candidate_source_exhausted and code == "NO_CANDIDATE"):
            # §7.2 exhaustion refusal: durable audit without a canonical fact / AH ops for this fragment.
            entries.append({"kind": "observation_record", "fragment_id": f.fragment_id,
                           "code": "CANDIDATE_SOURCE_EXHAUSTED"})
        else:
            # Non-RESOLVED semantic outcome -> ObservationRecord WITHOUT a canonical fact (channel 1 independent).
            entries.append({"kind": "observation_record", "fragment_id": f.fragment_id, "outcome": code})

    return T5Result(batch_hash=bhash, eligibility="OK", committed_fragments=tuple(committed),
                   journal_entries=tuple(entries))
