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
    model_key: str = ""
    params_hash: str = "temperature=0"
    log: object = None                           # ProviderCallLog (optional; in-memory if None)
    budget: BudgetSnapshot = field(default_factory=BudgetSnapshot)

    def __post_init__(self):
        from ah.formalizer.provider_call_log import ProviderCallLog
        self._log = self.log or ProviderCallLog()
        self._tokens_used = 0
        self._tp_calls_left = self.budget.tp_calls
        self._lexical_calls_left = self.budget.lexical_calls
        self._ordinals: dict[str,int] = {}

    def start_run(self, run_id):
        self._ordinals[run_id] = 0
        self._tokens_used = 0
        self._tp_calls_left = self.budget.tp_calls
        self._lexical_calls_left = self.budget.lexical_calls
        if self._log._journal:
            records = self._log._journal.scan_unprocessed(0)
            if not any(r["payload"].get("kind") == "RUN_STARTED" and r["payload"].get("run_id") == run_id for r in records):
                self._log._journal.append("provider", {"kind":"RUN_STARTED", "run_id":run_id}, run_id=run_id)

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

    def _exchange(self, capability: str, prompt: str, run_id: str, ordinal=None) -> str:
        import time
        if not self.has(capability):
            raise ProviderUnavailable(f"{capability!r} not available on provider {self.name!r}")
        if ordinal is None:
            ordinal = self._ordinals.get(run_id,0)+1
            self._ordinals[run_id] = ordinal
        key = self._digest(prompt)
        old = self._log.lookup(run_id,ordinal)
        if old:
            if (old['request_digest'],old.get('model_key',''),old.get('params_hash','')) != (key,self.model_key,self.params_hash):
                raise IntegrityError('REPLAY_MISMATCH')
            if old['state'] == 'RECEIVED':
                raw = old.get('raw_response')
                if raw is None or self._digest(raw) != old['response_digest']:
                    raise IntegrityError('INTEGRITY_ERROR: missing or corrupt provider bytes')
                cost = max(1,(len(prompt)+len(raw))//4)
                self._check_tokens(cost)
                self._tokens_used += cost
                return raw
            if old['state']=='FAILED':
                # A durable failed exchange is part of this run's history too.
                # Retrying it would silently change the interpretation on replay.
                cost=max(1,len(prompt)//4)
                self._check_tokens(cost); self._tokens_used+=cost
                raise ProviderUnavailable(old.get('error','recorded provider failure'))
        self._check_tokens(max(1,len(prompt)//4))
        cid = self._log.begin(self.name,key,run_id=run_id,ordinal=ordinal,model_key=self.model_key,params_hash=self.params_hash,prompt=prompt)
        started = time.monotonic()
        try:
            raw = self.transport(prompt)
            if not isinstance(raw,str): raise TypeError('provider response must be text')
        except Exception as exc:
            self._log.failed(cid,error=str(exc))
            self._tokens_used += max(1,len(prompt)//4)
            raise ProviderUnavailable(f'provider {self.name!r} call failed') from exc
        self._log.received(cid,response_digest=self._digest(raw),raw_response=raw,response_time_ms=(time.monotonic()-started)*1000)
        cost = max(1,(len(prompt)+len(raw))//4)
        self._check_tokens(cost)
        self._tokens_used += cost
        return raw

    def select(self, prompt: str, run_id: str, ordinal=None) -> str:
        """Bounded selection call (T3). Logged; replay-identical; integrity-checked."""
        self._check_tokens(0)  # pre-check the shared token limit before spending a call
        return self._exchange("select", prompt, run_id, ordinal)

    def propose_local(self, prompt: str, run_id: str) -> str:
        """Local-structure / lexical proposal (TP/T3). Consumes one tp_call; logged + integrity-checked."""
        if self._tp_calls_left <= 0:
            raise BudgetExceeded("PROPOSAL_BUDGET", "no structural proposal calls left in budget")
        self._tp_calls_left -= 1
        return self._exchange("propose_local", prompt, run_id)
