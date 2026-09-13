from __future__ import annotations

from collections import deque
from collections.abc import Callable
from threading import Lock
from typing import Any, Sequence
import json
import time
import uuid

from ah.config import AppConfig
from ah.llm.process_backend import (
    LLMActiveRequestDiagnostic,
    LLMBackendStatus,
    LLMRequestDiagnostic,
    LLMResponse,
)


GenerateEngine = Callable[[str, str, dict[str, Any], str], str]

_ENGINE: GenerateEngine | None = None


def register_engine(engine: GenerateEngine | None) -> None:
    """Bind the on-device generator used by AndroidNpuBackend.

    Kotlin registers a Java object whose ``generate`` method matches
    ``(prompt, system, override_json, role) -> str``. Tests may register a
    plain Python callable with the GenerateEngine signature.
    """

    global _ENGINE
    _ENGINE = engine


def bound_engine() -> GenerateEngine | None:
    return _ENGINE


def _invoke_engine(prompt: str, system: str, override: dict[str, Any], role: str) -> str:
    engine = _ENGINE
    packed = json.dumps(override, ensure_ascii=False)
    if engine is not None:
        generate = getattr(engine, "generate", None)
        if generate is not None:
            return str(generate(prompt, system, packed, role))
        if callable(engine):
            return str(engine(prompt, system, override, role))
        raise RuntimeError("Android NPU engine has no generate() method")
    try:
        from com.ahmemory.app.llm import AndroidNpuEngine  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Android NPU engine is not registered") from exc
    return str(AndroidNpuEngine.generate(prompt, system, packed, role))


class AndroidNpuBackend:
    """Stateless on-device LLM backend with the same generate() contract as desktop."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._status_lock = Lock()
        self._recent_log: deque[str] = deque(maxlen=200)
        self._stage = "stopped"
        self._last_role: str | None = None
        self._request_count = 0
        self._request_diagnostics: deque[LLMRequestDiagnostic] = deque(maxlen=50)
        self._active_request: LLMActiveRequestDiagnostic | None = None
        self._running = False
        self._ready = False

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> LLMBackendStatus:
        with self._status_lock:
            return LLMBackendStatus(
                running=self._running,
                pid=None,
                ready=self._ready,
                model_dir="android_npu",
                configured_model_dir="android_npu",
                loader_type="android_npu",
                context_window=self.config.llm.ctx_total or None,
                transformers_version=None,
                cuda_available=False,
                cuda_summary="android_npu",
                placement_summary="on-device TPU/NPU",
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

    def start(self) -> None:
        if self._running:
            return
        if self.config.llm.history_messages != 0:
            raise ValueError("Only stateless LLM requests (history_messages=0) are supported")
        with self._status_lock:
            self._stage = "starting"
            self._recent_log.clear()
        self._running = True
        self._ready = True
        with self._status_lock:
            self._stage = "ready"
            self._recent_log.append("[ready] android_npu")

    def stop(self) -> None:
        self._running = False
        self._ready = False
        with self._status_lock:
            self._stage = "stopped"
            self._active_request = None

    def restart(self) -> None:
        self.stop()
        self.start()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise RuntimeError("android_npu does not provide embeddings")

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict[str, Any] | None = None,
        role: str = "generic",
    ) -> LLMResponse:
        if not self._running:
            raise RuntimeError("LLM backend is not running")
        if self.config.llm.history_messages != 0:
            raise RuntimeError("LLM request history must stay disabled for mechanical role calls")
        defaults = {
            "max_new_tokens": self.config.llm.max_new_tokens,
            "temperature": self.config.llm.temperature,
            "top_p": self.config.llm.top_p,
            "top_k": self.config.llm.top_k,
            "repetition_penalty": self.config.llm.repetition_penalty,
            "no_repeat_ngram_size": self.config.llm.no_repeat_ngram_size,
        }
        defaults.update(override or {})
        if defaults.get("choice_outputs") is not None:
            raise RuntimeError(
                "android_npu does not implement choice_outputs continuation scoring; "
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
        error: str | None = None
        started = time.monotonic()
        try:
            response_text = _invoke_engine(prompt, system, defaults, role).strip()
            return LLMResponse(response_text, {"text": response_text, "ok": True})
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            from ah.diagnostics.session_log import log_llm_request

            elapsed_ms = int((time.monotonic() - started) * 1000)
            log_llm_request(
                sequence=seq,
                req_id=req_id,
                role=role,
                prompt=prompt[:800],
                system=system[:400],
                response_text=response_text[:2000],
                error=error,
                elapsed_ms=elapsed_ms,
            )
            with self._status_lock:
                self._request_diagnostics.append(
                    LLMRequestDiagnostic(
                        sequence=seq,
                        req_id=req_id,
                        role=role,
                        prompt=prompt,
                        system=system,
                        response_text=response_text,
                        error=error,
                    )
                )
                state = "ERROR" if error else "OK"
                detail = f": {error}" if error else ""
                self._recent_log.append(
                    f"[request #{seq}] role={role} {state} {elapsed_ms}ms{detail}"
                )
                self._stage = "ready" if self._ready else "stopped"
                self._active_request = None
