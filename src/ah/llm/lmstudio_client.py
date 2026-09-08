from __future__ import annotations

from typing import Any, Sequence
import json
import urllib.error
import urllib.request


class LMStudioClientError(RuntimeError):
    pass


class LMStudioClient:
    """Small dependency-free client for LM Studio's local HTTP server.

    Model discovery uses LM Studio's OpenAI-compatible ``/v1/models`` endpoint.
    Generic generation keeps using stateless ``/v1/chat/completions``. Bounded
    machine-protocol probes use the native ``/api/v1/chat`` endpoint because it
    exposes a first-class ``reasoning=off`` control; the OpenAI-compatible endpoint
    does not define request-level thinking control in its supported payload. Both
    paths explicitly disable server-side conversation storage/history.
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
        enable_thinking: bool | None = None,
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
        if enable_thinking is not None:
            # LM Studio model.yaml exposes reasoning through the Jinja variable
            # ``enable_thinking``. Different LM Studio builds have accepted this
            # setting through different compatibility surfaces, so send the same
            # explicit value through both known request forms. Servers that ignore
            # one form can still honor the other; neither changes AH semantics.
            flag = bool(enable_thinking)
            body["enable_thinking"] = flag
            body["chat_template_kwargs"] = {"enable_thinking": flag}
        return self._request("POST", "/v1/chat/completions", body)

    @staticmethod
    def embed_request_body(*, model: str, texts: Sequence[str]) -> dict[str, Any]:
        inputs = [str(item) for item in texts]
        if not str(model or "").strip():
            raise LMStudioClientError("LM Studio embed request requires a model")
        if not inputs:
            raise LMStudioClientError("LM Studio embed request requires at least one input")
        return {"model": str(model).strip(), "input": inputs}

    @staticmethod
    def parse_embed_response(data: dict[str, Any]) -> list[list[float]]:
        raw = data.get("data")
        if not isinstance(raw, list) or not raw:
            raise LMStudioClientError("LM Studio embeddings response missing data list")
        indexed: list[tuple[int, list[float]]] = []
        for position, item in enumerate(raw):
            if not isinstance(item, dict):
                raise LMStudioClientError("LM Studio embeddings response contains an invalid item")
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise LMStudioClientError("LM Studio embeddings response missing embedding vector")
            try:
                values = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise LMStudioClientError("LM Studio embeddings response contained a non-numeric vector") from exc
            try:
                index = int(item.get("index", position))
            except (TypeError, ValueError) as exc:
                raise LMStudioClientError("LM Studio embeddings response contained an invalid index") from exc
            indexed.append((index, values))
        indexed.sort(key=lambda pair: pair[0])
        return [vector for _, vector in indexed]

    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
        body = self.embed_request_body(model=model, texts=texts)
        data = self._request("POST", "/v1/embeddings", body)
        vectors = self.parse_embed_response(data)
        if len(vectors) != len(body["input"]):
            raise LMStudioClientError(
                f"LM Studio embeddings returned {len(vectors)} vectors for {len(body['input'])} inputs"
            )
        return vectors


    def native_chat(
        self,
        *,
        model: str,
        prompt: str,
        system: str,
        temperature: float,
        top_p: float,
        top_k: int,
        repeat_penalty: float,
        max_tokens: int,
        reasoning: str = "off",
    ) -> dict[str, Any]:
        """Run one stateless request through LM Studio's native v1 chat API.

        The native endpoint has an explicit ``reasoning`` switch. This is required
        for AH's bounded protocol probes: a reasoning-capable model must not spend
        the tiny label budget in a hidden reasoning channel. ``store=False`` keeps
        the call stateless, matching the backend contract.
        """
        mode = str(reasoning or "off").strip().lower()
        if mode not in {"off", "low", "medium", "high", "on"}:
            raise ValueError(f"Unsupported LM Studio reasoning mode: {reasoning!r}")
        body: dict[str, Any] = {
            "model": model,
            "input": str(prompt),
            "temperature": float(temperature),
            "top_p": float(top_p),
            "top_k": int(top_k),
            "repeat_penalty": float(repeat_penalty),
            "max_output_tokens": int(max_tokens),
            "reasoning": mode,
            "stream": False,
            "store": False,
        }
        if str(system or "").strip():
            body["system_prompt"] = str(system).strip()
        return self._request("POST", "/api/v1/chat", body)

    @staticmethod
    def native_chat_text(data: dict[str, Any]) -> str:
        output = data.get("output")
        if not isinstance(output, list):
            raise LMStudioClientError("LM Studio native chat response missing output list")
        messages: list[str] = []
        has_reasoning = False
        for item in output:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "").strip().lower()
            content = item.get("content")
            if kind == "reasoning":
                if isinstance(content, str) and content.strip():
                    has_reasoning = True
                continue
            if kind == "message" and isinstance(content, str) and content.strip():
                messages.append(content.strip())
        text = "\n".join(messages).strip()
        if text:
            return text
        stats = data.get("stats")
        reasoning_tokens = None
        total_output_tokens = None
        if isinstance(stats, dict):
            reasoning_tokens = stats.get("reasoning_output_tokens")
            total_output_tokens = stats.get("total_output_tokens")
        details = []
        if total_output_tokens is not None:
            details.append(f"total_output_tokens={total_output_tokens}")
        if reasoning_tokens is not None:
            details.append(f"reasoning_output_tokens={reasoning_tokens}")
        details.append(f"reasoning_content={'present' if has_reasoning else 'absent'}")
        raise LMStudioClientError(
            "LM Studio native chat returned no message content (" + "; ".join(details) + ")"
        )

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
        text = ""
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            # Some OpenAI-compatible servers represent content as typed parts.
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(str(item["text"]))
            text = "".join(parts).strip()
        if text:
            return text

        # Never silently treat an empty assistant message as a valid protocol
        # answer. Reasoning-capable LM Studio models can spend the entire small
        # generation budget in ``reasoning_content`` and leave ``content`` empty.
        # Feeding that hidden reasoning to the parser would violate the bounded
        # semantic-probe contract, so fail closed with transport diagnostics only.
        has_reasoning = any(
            isinstance(message.get(key), str) and bool(str(message.get(key)).strip())
            for key in ("reasoning_content", "reasoning")
        )
        finish_reason = first.get("finish_reason")
        usage = data.get("usage")
        reasoning_tokens = None
        completion_tokens = None
        if isinstance(usage, dict):
            completion_tokens = usage.get("completion_tokens")
            details = usage.get("completion_tokens_details")
            if isinstance(details, dict):
                reasoning_tokens = details.get("reasoning_tokens")
        details: list[str] = []
        if finish_reason is not None:
            details.append(f"finish_reason={finish_reason}")
        if completion_tokens is not None:
            details.append(f"completion_tokens={completion_tokens}")
        if reasoning_tokens is not None:
            details.append(f"reasoning_tokens={reasoning_tokens}")
        details.append(f"reasoning_content={'present' if has_reasoning else 'absent'}")
        suffix = "; ".join(details)
        raise LMStudioClientError(
            "LM Studio returned empty assistant content (" + suffix + "). "
            "For bounded AH perception probes, disable model Thinking in LM Studio; "
            "the backend already requests enable_thinking=false and does not consume hidden reasoning as an answer."
        )
