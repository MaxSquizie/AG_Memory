from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any
import uuid

from ah.config import AppConfig
from ah.llm.ollama_client import OllamaClient, OllamaClientError
from ah.llm.process_backend import (
    LLMActiveRequestDiagnostic,
    LLMBackendStatus,
    LLMRequestDiagnostic,
    LLMResponse,
)


def _compose_prompt(system: str, prompt: str) -> str:
    system = str(system or "").strip()
    prompt = str(prompt or "").strip()
    return f"{system}\n\n{prompt}" if system and prompt else system or prompt


def _rank_choice_scores(scores: dict[str, float]) -> tuple[str, float]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        raise RuntimeError("fixed-choice scoring produced no result")
    best_choice, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else best_score
    return best_choice, float(best_score - second_score)


class OllamaBackend:
    """Stateless HTTP backend for a local Ollama server.

    It exposes the same mechanical generate/status/diagnostics contract as the
    builtin process backend, so perception/agent code stays backend-agnostic.
    """
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = OllamaClient(config.llm.ollama_base_url, timeout_seconds=config.llm.request_timeout_seconds)
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

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> LLMBackendStatus:
        model = self.config.llm.ollama_model
        with self._status_lock:
            return LLMBackendStatus(
                running=self._running,
                pid=None,
                ready=self._ready,
                model_dir=model,
                configured_model_dir=model,
                loader_type="ollama",
                context_window=None,
                transformers_version=None,
                cuda_available=None,
                cuda_summary=f"ollama={self.config.llm.ollama_base_url}",
                placement_summary=(f"models={len(self._available_models)}" if self._available_models else "models=unknown"),
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

    def list_models(self) -> tuple[str, ...]:
        return self._available_models

    def start(self) -> None:
        if self._running:
            return
        if self.config.llm.history_messages != 0:
            raise ValueError("Only stateless LLM requests (history_messages=0) are supported")
        model = self.config.llm.ollama_model.strip()
        if not model:
            raise ValueError("llm.ollama_model is not configured")
        with self._status_lock:
            self._stage = "starting"
            self._recent_log.clear()
        try:
            models = self._client.list_models()
        except OllamaClientError as exc:
            with self._status_lock:
                self._stage = "stopped"
            raise RuntimeError(str(exc)) from exc
        self._available_models = tuple(models)
        if model not in models:
            available = ", ".join(models[:8]) + ("…" if len(models) > 8 else "")
            raise RuntimeError(f"Ollama model {model!r} is not available. Pulled models: {available or '<none>'}")
        self._running = True
        self._ready = True
        with self._status_lock:
            self._stage = "ready"
            self._recent_log.append(f"[ready] ollama model={model}")

    def stop(self) -> None:
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
            "num_predict": int(override.get("max_new_tokens", self.config.llm.max_new_tokens)),
        }

    def _score_exact_continuations(self, prefix: str, choices: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for choice in choices:
            if not str(choice).strip():
                raise ValueError("choice_outputs must contain non-empty strings")
            data = self._client.generate(
                model=self.config.llm.ollama_model,
                prompt=prefix + str(choice),
                options={"temperature": 0, "num_predict": 1},
                logprobs=True,
            )
            scores[str(choice)] = self._client.mean_logprob(data)
        return scores

    def generate(self, prompt: str, *, system: str = "", override: dict[str, Any] | None = None, role: str = "generic") -> LLMResponse:
        if not self._running:
            raise RuntimeError("LLM backend is not running")
        defaults = {
            "max_new_tokens": self.config.llm.max_new_tokens,
            "temperature": self.config.llm.temperature,
            "top_p": self.config.llm.top_p,
            "top_k": self.config.llm.top_k,
            "repetition_penalty": self.config.llm.repetition_penalty,
            "no_repeat_ngram_size": self.config.llm.no_repeat_ngram_size,
        }
        defaults.update(override or {})
        req_id = uuid.uuid4().hex
        with self._status_lock:
            self._request_count += 1
            seq = self._request_count
            self._last_role = role
            self._stage = f"generating:{role}"
            self._active_request = LLMActiveRequestDiagnostic(seq, req_id, role, prompt, system)
        response_text = ""
        meta: dict[str, Any] = {}
        error: str | None = None
        try:
            prefix = _compose_prompt(system, prompt)
            raw_choices = defaults.get("choice_outputs")
            if raw_choices is not None:
                if not isinstance(raw_choices, list):
                    raise ValueError("choice_outputs must be a JSON list")
                choices = [str(item) for item in raw_choices]
                if len(set(choices)) != len(choices):
                    raise ValueError("choice_outputs must be unique")
                actual = self._score_exact_continuations(prefix, choices)
                calibration_prompt = defaults.get("choice_calibration_prompt")
                if calibration_prompt is not None:
                    cal_system = str(defaults.get("choice_calibration_system", system or ""))
                    baseline = self._score_exact_continuations(_compose_prompt(cal_system, str(calibration_prompt)), choices)
                    calibrated = {c: actual[c] - baseline[c] for c in choices}
                    winner, margin = _rank_choice_scores(calibrated)
                    _, raw_margin = _rank_choice_scores(actual)
                    meta = {
                        "choice": winner,
                        "choice_scores": actual,
                        "calibration_choice_scores": baseline,
                        "calibrated_choice_scores": calibrated,
                        "raw_choice_margin": raw_margin,
                        "choice_margin": margin,
                        "choice_scoring_mode": "content_free_calibrated_semantic_completion",
                    }
                else:
                    winner, margin = _rank_choice_scores(actual)
                    meta = {"choice": winner, "choice_scores": actual, "choice_margin": margin, "choice_scoring_mode": "raw_exact_continuation"}
                response_text = str(meta["choice"])
            else:
                messages: list[dict[str, str]] = []
                if system.strip():
                    messages.append({"role": "system", "content": system.strip()})
                messages.append({"role": "user", "content": prompt})
                think = bool(defaults.get("enable_thinking", self.config.llm.enable_thinking))
                if role.startswith("perception_") or role == "perception":
                    think = False
                response_text = self._client.chat(
                    model=self.config.llm.ollama_model,
                    messages=messages,
                    options=self._generation_options(defaults),
                    think=think,
                )
                meta = {"ok": True}
            return LLMResponse(response_text, {"text": response_text, **meta})
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            threshold = defaults.get("decision_margin_threshold")
            try:
                threshold_f = None if threshold is None else float(threshold)
            except (TypeError, ValueError):
                threshold_f = None
            margin = meta.get("choice_margin")
            try:
                margin_f = None if margin is None else float(margin)
            except (TypeError, ValueError):
                margin_f = None
            diagnostic = LLMRequestDiagnostic(
                sequence=seq,
                req_id=req_id,
                role=role,
                prompt=prompt,
                system=system,
                response_text=response_text,
                rendered_prompt=_compose_prompt(system, prompt),
                choice_outputs=tuple(str(x) for x in defaults.get("choice_outputs", []) or []),
                choice_scores=meta.get("choice_scores"),
                calibration_choice_scores=meta.get("calibration_choice_scores"),
                calibrated_choice_scores=meta.get("calibrated_choice_scores"),
                choice_winner=meta.get("choice"),
                raw_choice_margin=meta.get("raw_choice_margin"),
                choice_margin=margin_f,
                choice_scoring_mode=meta.get("choice_scoring_mode"),
                decision_margin_threshold=threshold_f,
                decision_accepted=(None if margin_f is None or threshold_f is None else margin_f >= threshold_f),
                error=error,
            )
            with self._status_lock:
                self._request_diagnostics.append(diagnostic)
                self._recent_log.append(f"[request #{seq}] role={role} {'ERROR' if error else 'OK'}" + (f": {error}" if error else ""))
                self._stage = "ready" if self._ready else "stopped"
                self._active_request = None
            try:
                from ah.diagnostics.session_log import log_llm_request
                log_llm_request(sequence=seq, req_id=req_id, role=role, prompt=prompt, system=system, response_text=response_text, error=error)
            except Exception:
                pass
