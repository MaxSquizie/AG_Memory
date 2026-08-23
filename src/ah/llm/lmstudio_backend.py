from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any
import re
import uuid

from ah.config import AppConfig
from ah.llm.lmstudio_client import LMStudioClient, LMStudioClientError
from ah.llm.process_backend import (
    LLMActiveRequestDiagnostic,
    LLMBackendStatus,
    LLMRequestDiagnostic,
    LLMResponse,
)


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", flags=re.S | re.I)


def _compose_prompt(system: str, prompt: str) -> str:
    system = str(system or "").strip()
    prompt = str(prompt or "").strip()
    return f"{system}\n\n{prompt}" if system and prompt else system or prompt


def _strip_thinking(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", str(text or "")).strip()


def _model_key(item: dict[str, Any]) -> str:
    return str(item.get("key") or "").strip()


def _model_display(item: dict[str, Any]) -> str:
    return str(item.get("display_name") or "").strip()


def _model_alias(value: str) -> str:
    """Normalize only transport/packaging decoration for model-name matching.

    LM Studio may expose a loaded GGUF by a runtime key that omits the repository
    packaging suffix, e.g. ``Qwen...-GGUF`` -> ``qwen...``. Exact keys still win;
    this alias is used only as a final, uniqueness-checked compatibility match.
    """
    leaf = str(value or "").replace("\\", "/").rstrip("/").split("/")[-1].strip().casefold()
    if leaf.endswith(".gguf"):
        leaf = leaf[:-5]
    if leaf.endswith("-gguf"):
        leaf = leaf[:-5]
    return leaf


def _loaded_instances(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw = item.get("loaded_instances") or []
    if not isinstance(raw, list):
        return []
    return [dict(x) for x in raw if isinstance(x, dict)]


class LMStudioBackend:
    """Stateless HTTP backend for an externally managed LM Studio server.

    The server/model lifecycle remains owned by LM Studio. ``start()`` means
    "validate the server and attach this runtime", not "spawn a second model".
    Perception and agent calls therefore share the one LM Studio model while still
    sending a fresh system+user message list for every AH mechanical request.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = self._new_client()
        self._status_lock = Lock()
        self._recent_log: deque[str] = deque(maxlen=200)
        self._stage = "stopped"
        self._last_role: str | None = None
        self._request_count = 0
        self._request_diagnostics: deque[LLMRequestDiagnostic] = deque(maxlen=50)
        self._active_request: LLMActiveRequestDiagnostic | None = None
        self._running = False
        self._ready = False
        self._available_models: tuple[str, ...] = ()
        self._active_model = ""
        self._active_model_info: dict[str, Any] = {}

    def _new_client(self) -> LMStudioClient:
        return LMStudioClient(
            self.config.llm.lmstudio_base_url,
            timeout_seconds=self.config.llm.request_timeout_seconds,
            api_key=self.config.llm.lmstudio_api_key,
        )

    @property
    def is_running(self) -> bool:
        return self._running

    def list_models(self) -> tuple[str, ...]:
        return self._available_models

    def _context_window(self) -> int | None:
        instances = _loaded_instances(self._active_model_info)
        for instance in instances:
            cfg = instance.get("config")
            if isinstance(cfg, dict):
                try:
                    return int(cfg.get("context_length"))
                except (TypeError, ValueError):
                    pass
        return None

    def _placement_summary(self) -> str:
        if not self._active_model_info:
            return "models=unknown"
        if self._active_model_info.get("discovery_api") == "openai-compatible":
            return f"available={len(self._available_models)}; discovery=/v1/models"
        loaded = len(_loaded_instances(self._active_model_info))
        quant = self._active_model_info.get("quantization")
        quant_name = ""
        if isinstance(quant, dict) and quant.get("name"):
            quant_name = f"; quant={quant.get('name')}"
        return f"available={len(self._available_models)}; loaded_instances={loaded}{quant_name}"

    def status(self) -> LLMBackendStatus:
        model = self._active_model or self.config.llm.lmstudio_model
        with self._status_lock:
            return LLMBackendStatus(
                running=self._running,
                pid=None,
                ready=self._ready,
                model_dir=model,
                configured_model_dir=self.config.llm.lmstudio_model,
                loader_type="lmstudio",
                context_window=self._context_window(),
                transformers_version=None,
                cuda_available=None,
                cuda_summary=f"lmstudio={self.config.llm.lmstudio_base_url}",
                placement_summary=self._placement_summary(),
                effective_4bit=None,
                current_stage=self._stage,
                last_role=self._last_role,
                request_count=self._request_count,
                recent_log=tuple(self._recent_log),
            )

    def active_request_diagnostic(self) -> LLMActiveRequestDiagnostic | None:
        with self._status_lock:
            return self._active_request

    def request_diagnostics(self) -> tuple[LLMRequestDiagnostic, ...]:
        with self._status_lock:
            return tuple(self._request_diagnostics)

    @staticmethod
    def _select_model(configured: str, models: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        llms = [m for m in models if str(m.get("type") or "").lower() in {"", "llm"} and _model_key(m)]
        if not llms:
            raise RuntimeError("LM Studio reported no LLM models")

        requested = str(configured or "").strip()
        if requested and requested.lower() != "auto":
            exact = [m for m in llms if _model_key(m) == requested]
            if not exact:
                exact = [m for m in llms if _model_display(m) == requested]
            if not exact:
                folded = requested.casefold()
                exact = [m for m in llms if _model_key(m).casefold() == folded or _model_display(m).casefold() == folded]
            if len(exact) == 1:
                return _model_key(exact[0]), exact[0]
            if len(exact) > 1:
                raise RuntimeError(f"LM Studio model name {requested!r} is ambiguous; use its exact model key")

            # OpenAI-compatible /v1/models can expose an id with a publisher or
            # directory prefix. Accept the configured human-visible model name
            # only when it uniquely matches the final id component.
            requested_leaf = requested.replace("\\", "/").rstrip("/").split("/")[-1].casefold()
            leaf_matches = [
                m for m in llms
                if _model_key(m).replace("\\", "/").rstrip("/").split("/")[-1].casefold() == requested_leaf
            ]
            if len(leaf_matches) == 1:
                return _model_key(leaf_matches[0]), leaf_matches[0]
            if len(leaf_matches) > 1:
                raise RuntimeError(f"LM Studio model name {requested!r} is ambiguous; use its exact model key")

            # LM Studio can expose a GGUF repository/display name without the
            # trailing packaging marker in the actual runtime key. Accept that
            # deterministic alias only when it resolves to exactly one model.
            requested_alias = _model_alias(requested)
            alias_matches = [
                m for m in llms
                if _model_alias(_model_key(m)) == requested_alias
                or _model_alias(_model_display(m)) == requested_alias
            ]
            if len(alias_matches) == 1:
                return _model_key(alias_matches[0]), alias_matches[0]
            if len(alias_matches) > 1:
                raise RuntimeError(f"LM Studio model name {requested!r} is ambiguous; use its exact model key")

            available = ", ".join(_model_key(m) for m in llms[:12])
            if len(llms) > 12:
                available += ", …"
            raise RuntimeError(
                f"LM Studio model {requested!r} was not found. Available LLM keys: {available}"
            )

        loaded = [m for m in llms if _loaded_instances(m)]
        if len(loaded) == 1:
            return _model_key(loaded[0]), loaded[0]
        if len(loaded) > 1:
            keys = ", ".join(_model_key(m) for m in loaded)
            raise RuntimeError(
                "Several LM Studio LLMs are loaded. Set llm.lmstudio_model to one exact model key: " + keys
            )
        if len(llms) == 1:
            return _model_key(llms[0]), llms[0]
        keys = ", ".join(_model_key(m) for m in llms[:12])
        if len(llms) > 12:
            keys += ", …"
        raise RuntimeError(
            "No unique LM Studio model can be selected automatically. Load exactly one LLM or set "
            f"llm.lmstudio_model. Available keys: {keys}"
        )

    def start(self) -> None:
        if self._running:
            return
        if self.config.llm.history_messages != 0:
            raise ValueError("Only stateless LLM requests (history_messages=0) are supported")
        # Rebuild here so a GUI-configured URL/token actually takes effect after
        # the requested LLM restart rather than keeping a stale client instance.
        self._client = self._new_client()
        with self._status_lock:
            self._stage = "starting"
            self._recent_log.clear()
        try:
            models = self._client.list_models()
            model, info = self._select_model(self.config.llm.lmstudio_model, models)
        except Exception as exc:
            with self._status_lock:
                self._stage = "stopped"
            if isinstance(exc, LMStudioClientError):
                raise RuntimeError(str(exc)) from exc
            raise
        self._available_models = tuple(sorted(
            _model_key(m) for m in models
            if _model_key(m) and str(m.get("type") or "llm").lower() == "llm"
        ))
        self._active_model = model
        self._active_model_info = info
        self._running = True
        self._ready = True
        with self._status_lock:
            self._stage = "ready"
            self._recent_log.append(f"[ready] lmstudio model={model}")

    def stop(self) -> None:
        # LM Studio owns the server and the loaded model; disconnect only.
        self._running = False
        self._ready = False
        with self._status_lock:
            self._stage = "stopped"
            self._active_request = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def _generation_options(self, override: dict[str, Any]) -> dict[str, Any]:
        return {
            "temperature": float(override.get("temperature", self.config.llm.temperature)),
            "top_p": float(override.get("top_p", self.config.llm.top_p)),
            "top_k": int(override.get("top_k", self.config.llm.top_k)),
            "repeat_penalty": float(override.get("repetition_penalty", self.config.llm.repetition_penalty)),
            "max_tokens": int(override.get("max_new_tokens", self.config.llm.max_new_tokens)),
        }

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict[str, Any] | None = None,
        role: str = "generic",
    ) -> LLMResponse:
        if not self._running or not self._ready:
            raise RuntimeError("LLM backend is not running")
        defaults: dict[str, Any] = {
            "max_new_tokens": self.config.llm.max_new_tokens,
            "temperature": self.config.llm.temperature,
            "top_p": self.config.llm.top_p,
            "top_k": self.config.llm.top_k,
            "repetition_penalty": self.config.llm.repetition_penalty,
            "no_repeat_ngram_size": self.config.llm.no_repeat_ngram_size,
            "enable_thinking": self.config.llm.enable_thinking,
        }
        defaults.update(override or {})
        if defaults.get("choice_outputs") is not None:
            # Current adaptive_v3 production probes intentionally use ordinary
            # deterministic generation. Refuse to invent a second semantic voter
            # when an older caller asks for continuation-likelihood scoring.
            raise RuntimeError(
                "LM Studio backend does not implement choice_outputs continuation scoring; "
                "use ordinary fail-closed protocol generation"
            )

        req_id = uuid.uuid4().hex
        with self._status_lock:
            self._request_count += 1
            seq = self._request_count
            self._last_role = role
            self._stage = f"generating:{role}"
            self._active_request = LLMActiveRequestDiagnostic(seq, req_id, role, prompt, system)

        response_text = ""
        response_data: dict[str, Any] = {}
        error: str | None = None
        input_tokens: int | None = None
        try:
            messages: list[dict[str, str]] = []
            if str(system or "").strip():
                messages.append({"role": "system", "content": str(system).strip()})
            messages.append({"role": "user", "content": str(prompt)})
            response_data = self._client.chat_completions(
                model=self._active_model,
                messages=messages,
                **self._generation_options(defaults),
            )
            response_text = self._client.chat_text(response_data)
            # LM Studio/OpenAI-compatible endpoints may still expose Qwen-style
            # reasoning inside the content. Keep machine protocols clean even if
            # the loaded chat template chooses to reason internally.
            if self.config.llm.strip_thinking or role.startswith("perception_") or role.startswith("semantic_"):
                response_text = _strip_thinking(response_text)
            usage = response_data.get("usage")
            if isinstance(usage, dict):
                try:
                    input_tokens = int(usage.get("prompt_tokens"))
                except (TypeError, ValueError):
                    input_tokens = None
            return LLMResponse(response_text, {"text": response_text, **response_data})
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            diagnostic = LLMRequestDiagnostic(
                sequence=seq,
                req_id=req_id,
                role=role,
                prompt=prompt,
                system=system,
                response_text=response_text,
                rendered_prompt=_compose_prompt(system, prompt),
                input_tokens=input_tokens,
                error=error,
            )
            with self._status_lock:
                self._request_diagnostics.append(diagnostic)
                self._recent_log.append(
                    f"[request #{seq}] role={role} {'ERROR' if error else 'OK'}"
                    + (f": {error}" if error else "")
                )
                self._stage = "ready" if self._ready else "stopped"
                self._active_request = None
            try:
                from ah.diagnostics.session_log import log_llm_request
                log_llm_request(
                    sequence=seq,
                    req_id=req_id,
                    role=role,
                    prompt=prompt,
                    system=system,
                    response_text=response_text,
                    error=error,
                )
            except Exception:
                pass
