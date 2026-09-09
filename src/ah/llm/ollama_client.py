from __future__ import annotations

from typing import Any, Sequence
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
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
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
        return sorted(str(item["name"]) for item in models if isinstance(item, dict) and item.get("name"))

    def chat(self, *, model: str, messages: list[dict[str, str]], options: dict[str, Any] | None = None, think: bool | None = None) -> str:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if think is not None:
            body["think"] = think
        if options:
            body["options"] = options
        data = self._request("POST", "/api/chat", body)
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaClientError("Ollama chat response missing message")
        content = str(message.get("content") or "").strip()
        if content:
            return content
        return str(message.get("thinking") or "").strip()

    def generate(self, *, model: str, prompt: str, options: dict[str, Any] | None = None, logprobs: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if logprobs:
            body["logprobs"] = True
        if options:
            body["options"] = options
        return self._request("POST", "/api/generate", body)

    @staticmethod
    def embed_request_body(*, model: str, texts: Sequence[str]) -> dict[str, Any]:
        inputs = [str(item) for item in texts]
        if not str(model or "").strip():
            raise OllamaClientError("Ollama embed request requires a model")
        if not inputs:
            raise OllamaClientError("Ollama embed request requires at least one input")
        return {"model": str(model).strip(), "input": inputs}

    @staticmethod
    def parse_embed_response(data: dict[str, Any]) -> list[list[float]]:
        raw = data.get("embeddings")
        if raw is None and isinstance(data.get("embedding"), list):
            raw = [data.get("embedding")]
        if not isinstance(raw, list) or not raw:
            raise OllamaClientError("Ollama embed response missing embeddings")
        vectors: list[list[float]] = []
        for item in raw:
            if not isinstance(item, list) or not item:
                raise OllamaClientError("Ollama embed response contained an empty vector")
            try:
                vectors.append([float(value) for value in item])
            except (TypeError, ValueError) as exc:
                raise OllamaClientError("Ollama embed response contained a non-numeric vector") from exc
        return vectors

    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
        body = self.embed_request_body(model=model, texts=texts)
        data = self._request("POST", "/api/embed", body)
        vectors = self.parse_embed_response(data)
        if len(vectors) != len(body["input"]):
            raise OllamaClientError(
                f"Ollama embed returned {len(vectors)} vectors for {len(body['input'])} inputs"
            )
        return vectors

    @staticmethod
    def mean_logprob(data: dict[str, Any]) -> float:
        raw = data.get("logprobs")
        if not isinstance(raw, list) or not raw:
            raise OllamaClientError("Ollama did not return logprobs for choice scoring")
        values: list[float] = []
        for item in raw:
            if isinstance(item, dict) and "logprob" in item:
                try:
                    values.append(float(item["logprob"]))
                except (TypeError, ValueError):
                    pass
        if not values:
            raise OllamaClientError("Ollama logprobs payload contained no numeric scores")
        return sum(values) / len(values)
