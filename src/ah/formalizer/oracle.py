# -*- coding: utf-8 -*-
"""Machine-readable acceptance oracle (V7 §11.2 / WP1.6, cross-cutting WC1).

An OracleCase is a versioned artifact SEPARATE from the implementation. This module is the harness
skeleton: the case schema plus the five comparison rules of §11.2 as pure functions, and ``run_case``
which drives an injected runner (the pipeline) and applies whichever expected fields are present.

Comparison rules (§11.2):
  (1) candidate/decision ids — exact equality of SORTED SETS;
  (2) diagnostics — multiset equality on (code, location);
  (3) forbidden conclusions — ABSENCE in final AH + IR + terminal journal records;
  (4) state delta — structural comparison by CANONICAL-SERIALIZATION HASH (§1.3), never textual;
  (5) replay — identical reproducible input + canonical_run_id -> identical output; a new run_id of the
      same version is investigation-only; budget outcomes are compared only when a StageTimingLog exists.

The full A01–A39 / DR1–DR31 matrix is filled in at G3/G4; this skeleton proves the machinery and gates
the P1-applicable subset that the current T0–T4 prototype can already produce.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Schema (no data) — §11.2
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RawInput:
    text: str
    source_id: str = "src"
    revision: int = 0
    range_: tuple[int, int] | None = None


@dataclass(frozen=True)
class InitialState:
    ah: str = "EMPTY"                 # EMPTY | snapshot_hash
    temporal_ledger: str = "EMPTY"
    journal_tail: str = "EMPTY"
    interpretation_run_binding: str | None = None


@dataclass(frozen=True)
class ResourceSnapshot:
    snapshot_id: str = ""
    resources: tuple[tuple[str, str, str], ...] = ()  # (kind, version, sha256)
    context_version: int = 0


@dataclass(frozen=True)
class ProviderMode:
    kind: str                         # FAKE | PROVIDER
    script_ref: str | None = None     # FAKE
    model_key: str | None = None      # PROVIDER
    params_hash: str | None = None
    run_id: str | None = None
    replay: bool = False


@dataclass(frozen=True)
class Expected:
    candidate_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    coverage_status: str | None = None  # FULL_CANONICAL|OPEN_LEXICAL|PARTIAL|NONE
    covered_spans: tuple[str, ...] = ()
    unresolved_spans: tuple[str, ...] = ()
    surface_role_count: int | None = None
    first_lost_stage: str | None = None  # null when the gold-compatible candidate survives to seal
    diagnostics: tuple[tuple[str, str], ...] = ()  # multiset of (code, location)
    forbidden_conclusions: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateDelta:
    ah: tuple[str, ...] = ()          # canonical-serialization hashes (§1.3), not text
    temporal_ledger: tuple[str, ...] = ()
    journal: tuple[tuple[str, str, str], ...] = ()  # (channel, kind, terminal_status)


@dataclass(frozen=True)
class OracleCase:
    case_id: str                      # A01..A39 | DR1..DR31
    raw_input: RawInput
    expected: Expected = field(default_factory=Expected)
    initial_state: InitialState = field(default_factory=InitialState)
    resource_snapshot: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    provider_mode: ProviderMode = field(default_factory=lambda: ProviderMode(kind="FAKE"))
    timing_log_hash: str | None = None  # required for budget outcomes; else excluded from the guarantee
    state_delta: StateDelta = field(default_factory=StateDelta)


# --------------------------------------------------------------------------- #
# Comparison rules (pure) — §11.2
# --------------------------------------------------------------------------- #
def canonical_hash(obj) -> str:
    """§1.3 — deterministic sha256 of a canonical JSON serialization (sorted keys, no whitespace).

    State-delta and replay comparison are STRUCTURAL via this hash, never textual."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def compare_id_sets(expected: tuple[str, ...], actual) -> list[str]:
    """Rule (1): exact equality of sorted sets. Returns a human-readable diff list (empty = pass)."""
    e, a = set(expected), set(actual)
    diffs = []
    if missing := e - a:
        diffs.append(f"missing {sorted(missing)}")
    if extra := a - e:
        diffs.append(f"unexpected {sorted(extra)}")
    return diffs


def compare_diagnostics_multiset(expected, actual) -> list[str]:
    """Rule (2): multiset equality on (code, location)."""
    ce, ca = Counter(tuple(x) for x in expected), Counter(tuple(x) for x in actual)
    diffs = []
    if missing := ce - ca:
        diffs.append(f"missing {dict(missing)}")
    if extra := ca - ce:
        diffs.append(f"unexpected {dict(extra)}")
    return diffs


def check_forbidden_conclusions(forbidden, final_texts) -> list[str]:
    """Rule (3): every forbidden expression must be ABSENT from the final AH + IR + terminal journal."""
    joined = "\n".join(final_texts)
    return [f for f in forbidden if f in joined]


def compare_state_delta(expected_hashes: tuple[str, ...], actual_objs) -> list[str]:
    """Rule (4): structural comparison by canonical hash of each actual object vs the expected set."""
    e = set(expected_hashes)
    a = {canonical_hash(o) for o in actual_objs}
    diffs = []
    if missing := e - a:
        diffs.append(f"missing hashes {sorted(missing)}")
    if extra := a - e:
        diffs.append(f"unexpected hashes {sorted(extra)}")
    return diffs


def replay_identical(out_a, out_b) -> bool:
    """Rule (5): identical reproducible input + canonical_run_id -> identical output."""
    return canonical_hash(out_a) == canonical_hash(out_b)


# --------------------------------------------------------------------------- #
# Runner integration
# --------------------------------------------------------------------------- #
@dataclass
class CaseReport:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)

    def __str__(self):  # pragma: no cover - convenience
        return f"{self.case_id}: {'PASS' if self.passed else 'FAIL'} {self.failures or ''}"


def run_case(case: OracleCase, runner) -> CaseReport:
    """Drive ``runner(raw_input) -> actual bundle`` and apply whichever expected fields are present.

    The actual bundle is a mapping with optional keys: candidate_ids, decision_ids, coverage_status,
    covered_spans, unresolved_spans, surface_role_count, diagnostics, final_texts (for rule 3),
    state_objects (for rule 4). Absent expected fields are not checked."""
    exp = case.expected
    actual = runner(case.raw_input) or {}
    failures: list[str] = []

    if exp.candidate_ids:
        for d in compare_id_sets(exp.candidate_ids, actual.get("candidate_ids", ())):
            failures.append(f"candidates: {d}")
    if exp.decision_ids:
        for d in compare_id_sets(exp.decision_ids, actual.get("decision_ids", ())):
            failures.append(f"decisions: {d}")
    if exp.coverage_status is not None and "coverage_status" in actual:
        if actual["coverage_status"] != exp.coverage_status:
            failures.append(f"coverage: expected {exp.coverage_status} got {actual['coverage_status']}")
    if exp.diagnostics:
        for d in compare_diagnostics_multiset(exp.diagnostics, actual.get("diagnostics", ())):
            failures.append(f"diagnostics: {d}")
    if exp.forbidden_conclusions:
        for f in check_forbidden_conclusions(exp.forbidden_conclusions, actual.get("final_texts", ())):
            failures.append(f"forbidden conclusion present: {f!r}")
    if case.state_delta.ah and "state_objects" in actual:
        for d in compare_state_delta(case.state_delta.ah, actual["state_objects"]):
            failures.append(f"state-delta: {d}")

    return CaseReport(case_id=case.case_id, passed=not failures, failures=failures)
