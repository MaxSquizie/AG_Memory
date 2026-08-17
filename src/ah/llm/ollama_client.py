from __future__ import annotations

from typing import Any
import json
import urllib.error
import urllib.request


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 240.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaClientError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OllamaClientError(f"Ollama unreachable at {self.base_url}: {exc.reason}") from exc
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaClientError(f"Ollama returned invalid JSON from {path}") from exc
        if not isinstance(parsed, dict):
            raise OllamaClientError(f"Ollama returned non-object JSON from {path}")
        return parsed

    def list_models(self) -> list[str]:
        data = self._request("GET", "/api/tags")
        models = data.get("models") or []
        names: list[str] = []
        for item in models:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
        return sorted(names)

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            body["options"] = options
        data = self._request("POST", "/api/chat", body)
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaClientError("Ollama chat response missing message")
        return str(message.get("content") or "").strip()

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        options: dict[str, Any] | None = None,
        logprobs: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if logprobs:
            body["logprobs"] = True
        if options:
            body["options"] = options
        return self._request("POST", "/api/generate", body)

    @staticmethod
    def mean_logprob(data: dict[str, Any]) -> float:
        logprobs = data.get("logprobs")
        if not isinstance(logprobs, list) or not logprobs:
            raise OllamaClientError("Ollama did not return logprobs for choice scoring")
        values: list[float] = []
        for item in logprobs:
            if isinstance(item, dict) and "logprob" in item:
                try:
                    values.append(float(item["logprob"]))
                except (TypeError, ValueError):
                    continue
        if not values:
            raise OllamaClientError("Ollama logprobs payload contained no numeric scores")
        return sum(values) / len(values)
