# -*- coding: utf-8 -*-
"""StoreInterface — the single store contract for the formalizer (R1, WP0.7).

One interface, two implementations (see FORMALIZER_IMPLEMENTATION_PLAN_V7.md §2/§6):

* ``memory_store``  — a fast in-memory double used ONLY to unit-test PURE decisions
  (head-only admission, computing E and plan\\E, terminal-outcome selection). It
  deliberately CANNOT prove transactional guarantees.
* ``ah_adapter``    — the minimal AH adapter (P0) that makes those guarantees real:
  append-only journal, global head read, atomic durable write of plan\\E + marker +
  COMMIT_DECISION D, and status retraction.

Why a contract instead of "build an in-memory store then port it":
V7 §7.3/§8.3 make the T6 outcome depend on properties that only a real store can
exhibit — (a) the materialization marker and COMMIT_DECISION D land in ONE atomic
durable unit, and (b) recovery after a crash before APPLIED restores the outcome
from D without re-admission. A memory double cannot demonstrate either; declaring
P2 "passed" on it would leave exactly those properties unverified. So the AH
contract is fixed now, and memory stays a fast test double for pure logic only.

Every method below names the V7 clause it serves and the property an implementation
MUST guarantee. The memory double may satisfy the signatures but is not held to the
durability/atomicity properties; the AH adapter is.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence


# --------------------------------------------------------------------------- #
# Terminal outcomes and assertion statuses (§7.3 / §8)
# --------------------------------------------------------------------------- #
class TerminalOutcome(str, Enum):
    """Terminal status appended to the journal for a committed batch/assertion."""

    PENDING_ADMISSION_ORDER = "PENDING_ADMISSION_ORDER"  # transient; never journaled as terminal
    REJECTED_COMMIT_ELIGIBILITY = "REJECTED_COMMIT_ELIGIBILITY"
    RESOLUTION_ONLY = "RESOLUTION_ONLY"  # no batch/marker/world-fact mutation
    APPLIED = "APPLIED"
    REJECTED_CONFLICT_ADMISSION = "REJECTED_CONFLICT_ADMISSION"  # §7.3 head-only admission lost
    STALE_SUPERSEDED = "STALE_SUPERSEDED"                      # §8 superseded by a newer version


class AssertionStatus(str, Enum):
    """Lifecycle status of an assertion. Retraction TRANSITIONS this; it never deletes."""

    LIVE = "LIVE"
    SUPERSEDED = "SUPERSEDED"  # §8: replaced by a newer interpretation (kept for audit)
    STALE = "STALE"           # §8: path died / premise invalidated (kept for audit)


# --------------------------------------------------------------------------- #
# Record and operation descriptors (AH-agnostic; the adapter interprets them)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class JournalRecord:
    """One append-only journal entry. ``seq`` is assigned by the store on append."""

    channel: str            # "observation" | "resolution_log" (§7.2 two channels)
    run_id: str            # InterpretationRunBinding canonical_run_id (§0.8)
    payload: dict          # opaque record body (pre-commit T5 record, terminal outcome, ...)
    seq: int = -1          # store-assigned; -1 until appended


@dataclass(frozen=True)
class StoreOp:
    """An opaque graph mutation in a commit plan.

    The interface carries ops without knowing AH element types: the memory double
    stores them opaquely (enough to test plan\\E *computation*), while the AH
    adapter interprets ``op_type``/``payload`` against ``AHStore`` write ops.
    """

    op_type: str          # e.g. "ADD_ELEMENT" | "ADD_LINK" | "SET_MARKER" | ...
    payload: dict         # operation arguments, interpreted by the concrete store
    fragment_refs: tuple[str, ...] = ()
    deps: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaterializationMarker:
    """(observation_id, interpretation_version) marker — §7.3 step 1/7."""

    observation_id: str
    interpretation_version: int


@dataclass(frozen=True)
class CommitDecision:
    """COMMIT_DECISION D — the durable record recovery restores from (§7.3/§8.3).

    ``batch_hash`` makes re-commit idempotent; ``outcome`` is the terminal outcome
    the batch was decided to have, so a crash before APPLIED can be recovered from D
    without re-running admission.
    """

    run_id: str
    batch_hash: str
    marker: MaterializationMarker
    ops_digest: str       # stable hash of plan\\E ops (integrity check on recovery)
    outcome: TerminalOutcome
    committed: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    cited: tuple[str, ...] = ()
    excluded_evidence: tuple[dict, ...] = ()
    precheck_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommitResult:
    """What a commit transaction produced."""

    seq: int                          # journal seq of the atomic unit
    applied_uids: tuple              # uids materialized by plan\\E (empty if rejected)
    outcome: TerminalOutcome
    idempotent_noop: bool = False    # True when batch_hash already committed (§7.3 re-commit)


@dataclass(frozen=True)
class RecoveryReport:
    """Result of draining the journal from head after a crash (§8.3 step 3)."""

    recovered: tuple                # (assertion_id, TerminalOutcome) restored from D
    drained_to_seq: int
    re_admitted: bool = False       # MUST be False: recovery restores from D, no re-admission


# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #
class Store(ABC):
    """Minimal store contract for T5/T6 commit + retraction (P0 scope).

    P0 needs exactly four capabilities; the read helpers exist so those four are
    testable in isolation. Full formalizer is NOT required to use this yet.
    """

    # -- append-only journal (§7.2) ----------------------------------------- #
    @abstractmethod
    def append_journal(self, channel: str, record: JournalRecord) -> int:
        """Append one record to a channel and fsync it; return its ``seq``.

        Guarantees (AH adapter): the record is durable before this returns; seq is
        monotonically increasing per store and defines admission order.
        """

    # -- global head (§7.3) ------------------------------------------------- #
    @abstractmethod
    def read_global_head(self) -> int:
        """Highest committed seq across channels — the basis of head-only admission."""

    @abstractmethod
    def scan_unprocessed(self, after_seq: int) -> tuple[JournalRecord, ...]:
        """Records with ``seq > after_seq`` in ascending seq order (recovery/admission)."""

    # -- atomic durable commit (§7.3 step 1/7) ------------------------------ #
    @abstractmethod
    def commit_transaction(
        self,
        plan_ops: Sequence[StoreOp],
        marker: MaterializationMarker,
        decision: CommitDecision,
    ) -> CommitResult:
        """Apply ``plan_ops`` + SetMarker + COMMIT_DECISION D as ONE atomic durable unit.

        Guarantees (AH adapter): either all of {ops, marker, D} become visible and
        durable together, or none do; a re-commit with the same ``batch_hash`` is an
        idempotent no-op. The memory double may apply ops in-memory but does NOT
        provide durability/atomicity — that property is only real on the AH adapter.
        """

    # -- terminal status append (§7.3 / §8) --------------------------------- #
    @abstractmethod
    def append_terminal(self, assertion_id: str, outcome: TerminalOutcome, reason: str = "") -> int:
        """Append a durable terminal-status record for an assertion; return its ``seq``."""

    # -- status retraction without deletion (§8) ---------------------------- #
    @abstractmethod
    def retract(self, assertion_id: str, new_status: AssertionStatus, reason: str = "") -> bool:
        """Transition an assertion's status (LIVE→SUPERSEDED/STALE). Never deletes.

        Guarantees (AH adapter): the transition is durable and auditable; the record
        remains readable for audit after retraction. Returns False if unknown id.
        """

    # -- crash recovery from head (§7.3 / §8.3 step 3) ---------------------- #
    @abstractmethod
    def recover_from_head(self) -> RecoveryReport:
        """Drain the journal from head and restore terminal outcomes from COMMIT_DECISION D.

        Guarantees (AH adapter): a batch that committed D but crashed before APPLIED is
        restored to its decided outcome WITHOUT re-running admission (``re_admitted``
        stays False). The memory double has no crash window, so this is a no-op there.
        """

    # -- read helpers (thin; make the four capabilities testable) ---------- #
    @abstractmethod
    def has_uid(self, uid: str) -> bool: ...

    @abstractmethod
    def get_element_any_domain(self, uid: str) -> Any | None: ...
