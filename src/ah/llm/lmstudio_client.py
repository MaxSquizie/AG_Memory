from __future__ import annotations

from typing import Any
import json
import urllib.error
import urllib.request


class LMStudioClientError(RuntimeError):
    pass


class LMStudioClient:
    """Small dependency-free client for LM Studio's local HTTP server.

    Model discovery uses LM Studio's OpenAI-compatible ``/v1/models`` endpoint.
    This endpoint is available across a wider range of LM Studio server versions
    than the newer native ``/api/v1/models`` API and is sufficient for selecting
    the configured model. Inference uses the stateless OpenAI-compatible
    ``/v1/chat/completions`` endpoint, matching AH's requirement that every
    mechanical call owns no hidden chat history.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 240.0,
        api_key: str = "",
    ) -> None:
        raw = str(base_url or "").strip().rstrip("/")
        # Accept either the server root or an OpenAI-style base URL ending in /v1.
        if raw.endswith("/v1"):
            raw = raw[:-3].rstrip("/")
        if not raw:
            raise ValueError("LM Studio base URL must not be empty")
        self.base_url = raw
        self.timeout_seconds = float(timeout_seconds)
        self.api_key = str(api_key or "").strip()

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        payload: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise LMStudioClientError(
                f"LM Studio HTTP {exc.code} from {url}{suffix}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LMStudioClientError(
                f"LM Studio unreachable at {self.base_url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise LMStudioClientError(
                f"LM Studio request timed out at {self.base_url}"
            ) from exc

        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LMStudioClientError(
                f"LM Studio returned invalid JSON from {path}"
            ) from exc
        if not isinstance(parsed, dict):
            raise LMStudioClientError(
                f"LM Studio returned non-object JSON from {path}"
            )
        return parsed

    def list_models(self) -> list[dict[str, Any]]:
        """Return LM Studio models normalized to the backend's internal shape.

        LM Studio's OpenAI-compatible endpoint returns ``{"data": [...]}`` with
        each model identified by ``id``. Keep discovery on the same compatibility
        surface as chat completions instead of depending on the newer native REST
        API, which is not available/reliable in every LM Studio server build.
        """
        data = self._request("GET", "/v1/models")
        raw_models = data.get("data") or []
        if not isinstance(raw_models, list):
            raise LMStudioClientError("LM Studio /v1/models response missing data list")

        models: list[dict[str, Any]] = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            normalized = dict(item)
            normalized.setdefault("type", "llm")
            normalized["key"] = model_id
            normalized.setdefault("display_name", model_id)
            normalized.setdefault("loaded_instances", [])
            normalized["discovery_api"] = "openai-compatible"
            models.append(normalized)
        return models

    def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        top_p: float,
        top_k: int,
        repeat_penalty: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "top_k": int(top_k),
            "repeat_penalty": float(repeat_penalty),
            "max_tokens": int(max_tokens),
            # AH's backend contract is synchronous/stateless. Keep this explicit;
            # it also avoids clients/servers disagreeing about streaming defaults.
            "stream": False,
        }
        return self._request("POST", "/v1/chat/completions", body)

    @staticmethod
    def chat_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LMStudioClientError("LM Studio chat response missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise LMStudioClientError("LM Studio chat response contains invalid choice")
        message = first.get("message")
        if not isinstance(message, dict):
            raise LMStudioClientError("LM Studio chat response missing message")
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        # Some OpenAI-compatible servers represent content as typed parts.
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(str(item["text"]))
            return "".join(parts).strip()
        return ""
