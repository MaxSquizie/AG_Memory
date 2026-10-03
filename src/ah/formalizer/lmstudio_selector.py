# -*- coding: utf-8 -*-
"""Real LLM selector adapter for the formalizer pipeline.

The pipeline is backend-agnostic: it only requires an object exposing ``select(prompt) -> raw JSON str``
(see FakeSelector). This adapter satisfies that contract against a local LM Studio server's
OpenAI-compatible ``/v1/chat/completions`` endpoint, so the SAME code path that runs on the scripted
dry-run selector now runs on a real model (e.g. gemma-3n-e4b-it) with no pipeline changes.

It is deliberately minimal and stateless: one synchronous chat completion per call, stream=false, low
temperature for deterministic protocol answers. Provider unavailability raises (the pipeline treats that as
an honest diagnostic, never a fabricated answer).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class LMStudioSelectorError(RuntimeError):
    pass


class LMStudioSelector:
    """Drops into ``run(..., selector=...)`` in place of FakeSelector."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234",
        model: str = "gemma-3n-e4b-it",
        *,
        temperature: float = 0.0,
        max_tokens: int = 96,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout_seconds

    def list_models(self) -> list[str]:
        data = self._request("GET", "/v1/models")
        return [str(m.get("id")) for m in (data.get("data") or []) if isinstance(m, dict)]

    def select(self, prompt: str) -> str:
        """One stateless completion; returns the model's raw text (the selection protocol expects JSON)."""
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(self.temperature),
            "max_tokens": int(self.max_tokens),
            "stream": False,
        }
        data = self._request("POST", "/v1/chat/completions", body)
        choices = data.get("choices") or []
        if not choices:
            raise LMStudioSelectorError(f"LM Studio returned no choices for model {self.model!r}")
        message = choices[0].get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            # some reasoning models put the answer in a separate field; fall back to it rather than fail
            content = str(choices[0].get("reasoning_content") or message.get("reasoning") or "").strip()
        return content

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        payload = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LMStudioSelectorError(f"LM Studio HTTP {exc.code} at {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LMStudioSelectorError(f"LM Studio unreachable at {self.base_url}: {exc.reason}") from exc
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LMStudioSelectorError(f"LM Studio returned invalid JSON from {path}") from exc
        if not isinstance(parsed, dict):
            raise LMStudioSelectorError(f"LM Studio returned non-object JSON from {path}")
        return parsed
