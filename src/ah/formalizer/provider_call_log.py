# -*- coding: utf-8 -*-
"""ProviderCallLog — durable PENDING→RECEIVED/FAILED call tracking (§9, WP0.2).

Every LLM/provider call is logged with a per-provider monotonic ordinal and attempt number so a
crash can distinguish "call was sent but response lost" (PENDING) from a completed exchange
(RECEIVED) or a failure (FAILED). When a :class:`JournalChannel` is supplied each transition is
appended durably; the in-memory map mirrors it for fast lookups.
"""

from __future__ import annotations

from typing import Optional


class ProviderCallLog:
    def __init__(self, journal=None) -> None:
        self._journal = journal
        self._calls: dict[str, dict] = {}
        self._ordinal: dict[str, int] = {}

    def begin(self, provider: str, request_digest: str) -> str:
        """Open a PENDING call; returns its id ``provider#ordinal``."""
        n = self._ordinal.get(provider, 0) + 1
        self._ordinal[provider] = n
        call_id = f"{provider}#{n}"
        self._calls[call_id] = {"state": "PENDING", "attempt": n, "request_digest": request_digest}
        if self._journal is not None:
            self._journal.append(
                "resolution_log",
                {"kind": "prov_call", "id": call_id, "provider": provider, "attempt": n, "state": "PENDING"},
            )
        return call_id

    def _transition(self, call_id: str, state: str, **extra) -> bool:
        rec = self._calls.get(call_id)
        if rec is None:
            return False
        rec["state"] = state
        rec.update(extra)
        if self._journal is not None:
            payload = {"kind": "prov_call", "id": call_id, "state": state}
            payload.update(extra)
            self._journal.append("resolution_log", payload)
        return True

    def received(self, call_id: str, response_digest: Optional[str] = None) -> bool:
        return self._transition(call_id, "RECEIVED", response_digest=response_digest)

    def failed(self, call_id: str, error: str = "") -> bool:
        # The per-provider ordinal already counts every begin (success or not), so the next
        # retry naturally gets attempt = previous + 1 without any extra bump here.
        return self._transition(call_id, "FAILED", error=error)

    def state(self, call_id: str) -> Optional[str]:
        rec = self._calls.get(call_id)
        return None if rec is None else rec["state"]
