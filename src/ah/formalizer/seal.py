# -*- coding: utf-8 -*-
"""Structural seal stage (V7 §4.3 / WP1.1) — freeze the closed structural set into one snapshot.

The existing I30 closure (:meth:`FormalizationState.close_structures`) only flips a boolean flag.
This stage completes it per §4.3 without reinventing that mechanism — it reuses ``close_structures``
/ ``require_structures_open`` and adds exactly the two missing pieces:

1. CLOSURE VALIDATION — every cross-object reference in the frozen set resolves to a defined object;
   a dangling reference is an INTEGRITY_ERROR (T3/T4/C must never decide over a broken snapshot).
2. STRUCTURAL HASH — a deterministic sha256 over the canonical serialization of the frozen set, so
   replay can detect divergence and every downstream stage operates on one stable identity.

Then it freezes: ``close_structures()`` + record ``(seal_snapshot_id, structural_hash)`` on the state.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass

from .state import FormalizationState


class SealError(RuntimeError):
    """Raised when the structural set is not closed (a dangling reference)."""


@dataclass(frozen=True)
class SealResult:
    snapshot_id: str
    structural_hash: str
    object_counts: dict[str, int]
    closed: bool = True


def _canonical_records(state: FormalizationState) -> list[dict]:
    """Order-stable plain-dict records for the frozen structural set (nested provenance included)."""
    groups = [
        ("frame", state.frames),
        ("clause", state.clause_candidates),
        ("boundary", state.boundary_candidates),
        ("ellipsis", state.ellipsis_candidates),
        ("missing_arg", state.missing_argument_candidates),
        ("reference", state.reference_candidates),
        ("linked_alt", state.linked_alternatives),
        ("constraint", state.constraints),
        ("rejection", state.rejections),
    ]
    records: list[dict] = []
    for tag, objs in groups:
        for obj in objs:
            rec = dataclasses.asdict(obj)
            rec["_kind"] = tag
            records.append(rec)
    records.extend({**rec, '_kind': 'syntax_trace'} for rec in state.syntax_trace)
    records.extend({'_kind':'logical_root','tree':rec} for rec in state.logical_roots)
    if state.query_intents:
        records.extend({'_kind':'query_intent',**rec} for rec in state.query_intents)
    return records


def _jsonable(x):
    """Make a record JSON-safe (asdict leaves frozenset/set as-is; json cannot encode them)."""
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (frozenset, set)):
        return sorted(_jsonable(i) for i in x)
    if isinstance(x, tuple):
        return [_jsonable(i) for i in x]
    if isinstance(x, list):
        return [_jsonable(i) for i in x]
    return x


def structural_hash(state: FormalizationState) -> str:
    """Deterministic identity of the frozen structural set (replay-divergence detector)."""
    records = [_jsonable(r) for r in _canonical_records(state)]
    records.sort(key=lambda record:json.dumps(record,sort_keys=True,ensure_ascii=False,separators=(",", ":")))
    blob = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate_closure(state: FormalizationState) -> tuple[str, ...]:
    """Return descriptions of dangling references (empty when the set is self-contained)."""
    # IDs name immutable candidate payloads. Equal IDs with different content
    # must not silently collapse at seal, even when references happen to close.
    identities={}
    for record in _canonical_records(state):
        identifier=next((record[k] for k in ('candidate_id','frame_id','mention_id','hypothesis_id') if k in record),None)
        if identifier is None: continue
        key=(record['_kind'],identifier)
        payload=_jsonable(record)
        if key in identities and identities[key]!=payload:
            return ('INTEGRITY_ERROR: candidate ID collision '+str(identifier),)
        identities[key]=payload
    frame_ids = {f.frame_id for f in state.frames}
    spans = {ev.span for ev in state.evidence} | set(state.memory_mentions)
    dangling: list[str] = []

    for ma in state.missing_argument_candidates:
        if ma.frame_ref not in frame_ids:
            dangling.append(f"missing_arg {ma.candidate_id}: unknown frame_ref {ma.frame_ref!r}")

    for f in state.frames:
        for span in (*f.participants, *f.arguments):
            if span not in spans:
                dangling.append(f"frame {f.frame_id}: participant/argument {span!r} not observed")
        # attachment = the matrix predicate center this subclause hangs off: a span or a frame id.
        if f.attachment is not None and f.attachment not in (spans | frame_ids):
            dangling.append(f"frame {f.frame_id}: attachment {f.attachment!r} unknown")

    for e in state.ellipsis_candidates:
        if e.gap_ref not in spans:
            dangling.append(f"ellipsis {e.candidate_id}: gap_ref {e.gap_ref!r} not observed")
        if e.antecedent_ref is not None and e.antecedent_ref not in (spans | frame_ids):
            dangling.append(f"ellipsis {e.candidate_id}: antecedent_ref {e.antecedent_ref!r} unknown")

    for r in state.reference_candidates:
        for cand in r.candidates:
            if cand not in spans:
                dangling.append(f"reference {r.mention_id}: candidate {cand!r} not observed")

    return tuple(dangling)


def structural_seal(state: FormalizationState, *, strict: bool = True) -> SealResult:
    """Validate closure, compute the hash, and freeze the structural set (idempotent)."""
    dangling = validate_closure(state)
    if dangling:
        state.diag("INTEGRITY_ERROR", "unclosed structural reference(s): " + "; ".join(dangling))
        if strict:
            raise SealError("; ".join(dangling))

    snapshot_id = f"seal:{state.source_uid}:v{state.interpretation_version}"
    h = structural_hash(state)
    state.structural_hash = h
    state.seal_snapshot_id = snapshot_id
    state.close_structures()  # I30: from here T3/T4 may only DECIDE, never add structure

    counts = {tag: sum(1 for r in _canonical_records(state) if r["_kind"] == tag)
              for tag in ("frame", "clause", "boundary", "ellipsis", "missing_arg", "reference",
                          "linked_alt", "constraint")}
    return SealResult(snapshot_id=snapshot_id, structural_hash=h, object_counts=counts)
