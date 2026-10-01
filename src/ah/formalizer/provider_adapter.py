# -*- coding: utf-8 -*-
"""ProviderAdapter + BudgetSnapshot (V7 §0.8 / §14 line 514 — WP0.2).

The single logged entry point for every model call. ``select`` and ``propose_local`` are the same
logged exchange (a stable per-provider ordinal within a run, PENDING -> RECEIVED/FAILED via
:class:`~ah.formalizer.provider_call_log.ProviderCallLog`); an identical replay input returns the same
bytes, while a brand-new run reusing an already-seen input digest is ``INTEGRITY_ERROR`` with no AH write.

Contract points enforced here:
- missing capability -> :class:`ProviderUnavailable` (PROVIDER_UNAVAILABLE), never AMBIGUOUS and never a
  silently substituted external service — deterministic candidates continue with an honest miss;
- budget pre-checks use INDEPENDENT limits (tp_calls, lexical_calls, max_nodes/edges/depth) plus one shared
  token limit; exceeding raises COMPUTATION_LIMIT / PROPOSAL_BUDGET, not AMBIGUOUS.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


class ProviderUnavailable(Exception):
    """PROVIDER_UNAVAILABLE — the capability is absent or no transport is wired; deterministic candidates
    continue with an honest miss (never AMBIGUOUS)."""


class IntegrityError(Exception):
    """INTEGRITY_ERROR — a new run reuses an input digest already owned by another run; no AH write."""


class BudgetExceeded(Exception):
    """COMPUTATION_LIMIT / PROPOSAL_BUDGET — a budget limit was exceeded (never AMBIGUOUS)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class BudgetSnapshot:
    """Independent per-run limits plus one shared token limit (§14 line 514)."""

    tp_calls: int = 0          # structural local-structure proposals (TP)
    lexical_calls: int = 0     # lexical sense proposals (T3 open path)
    max_nodes: int = 0
    max_edges: int = 0
    max_depth: int = 0
    token_limit: int = 0       # shared across the whole run


@dataclass
class ProviderAdapter:
    """Logged facade over a backend transport. ``transport(prompt) -> raw JSON string`` is injected so the
    contract machinery (capability, budget, ordinal, replay, integrity) is testable without a live model."""

    name: str
    capabilities: frozenset[str] = frozenset()  # e.g. {"select", "propose_local"}
    transport: object = None                     # callable(prompt) -> raw JSON
    log: object = None                           # ProviderCallLog (optional; in-memory if None)
    budget: BudgetSnapshot = field(default_factory=BudgetSnapshot)

    def __post_init__(self):
        from ah.formalizer.provider_call_log import ProviderCallLog
        self._log = self.log or ProviderCallLog()
        self._tokens_used = 0
        self._tp_calls_left = self.budget.tp_calls
        self._lexical_calls_left = self.budget.lexical_calls
        # (run_id, digest) -> raw JSON for replay identity; digest -> owning run_id for integrity.
        self._cache: dict[tuple[str, str], str] = {}
        self._input_owner: dict[str, str] = {}

    def has(self, capability: str) -> bool:
        return capability in self.capabilities and self.transport is not None

    @staticmethod
    def _digest(prompt: str) -> str:
        return hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()

    def validate_structure(self, node_count: int, edge_count: int, depth: int) -> None:
        """PROPOSAL_BUDGET gate on the structural envelope (independent max_nodes/edges/depth limits)."""
        b = self.budget
        if node_count > b.max_nodes or edge_count > b.max_edges or depth > b.max_depth:
            raise BudgetExceeded("PROPOSAL_BUDGET", f"nodes={node_count} edges={edge_count} depth={depth}")

    def _check_tokens(self, cost: int) -> None:
        if self.budget.token_limit and self._tokens_used + cost > self.budget.token_limit:
            raise BudgetExceeded("COMPUTATION_LIMIT", f"token budget {self.budget.token_limit} exhausted")

    def _exchange(self, capability: str, prompt: str, run_id: str) -> str:
        if not self.has(capability):
            raise ProviderUnavailable(f"{capability!r} not available on provider {self.name!r}")
        digest = self._digest(prompt)

        # Replay identity within the same run.
        cached = self._cache.get((run_id, digest))
        if cached is not None:
            return cached

        # Integrity: a NEW run reusing an input already owned by another run -> INTEGRITY_ERROR (no AH write).
        owner = self._input_owner.get(digest)
        if owner is not None and owner != run_id:
            raise IntegrityError(f"INTEGRITY_ERROR: input digest reused across runs ({owner!r} vs {run_id!r})")

        call_id = self._log.begin(self.name, digest)
        try:
            raw = str(self.transport(prompt))
        except Exception as exc:  # a failed exchange is logged FAILED, not swallowed
            self._log.failed(call_id, error=str(exc))
            raise ProviderUnavailable(f"provider {self.name!r} call failed") from exc
        cost = max(1, len(raw) // 4)
        if self.budget.token_limit and self._tokens_used + cost > self.budget.token_limit:
            raise BudgetExceeded("COMPUTATION_LIMIT", f"token budget {self.budget.token_limit} exhausted")
        self._tokens_used += cost
        self._log.received(call_id, response_digest=digest)
        self._cache[(run_id, digest)] = raw
        self._input_owner.setdefault(digest, run_id)
        return raw

    def select(self, prompt: str, run_id: str) -> str:
        """Bounded selection call (T3). Logged; replay-identical; integrity-checked."""
        self._check_tokens(0)  # pre-check the shared token limit before spending a call
        return self._exchange("select", prompt, run_id)

    def propose_local(self, prompt: str, run_id: str) -> str:
        """Local-structure / lexical proposal (TP/T3). Consumes one tp_call; logged + integrity-checked."""
        if self._tp_calls_left <= 0:
            raise BudgetExceeded("PROPOSAL_BUDGET", "no structural proposal calls left in budget")
        self._tp_calls_left -= 1
        return self._exchange("propose_local", prompt, run_id)
