from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Any
import uuid

from ah.config import AppConfig
from ah.diagnostics.session_log import log_llm_request
from ah.llm.ollama_client import OllamaClient, OllamaClientError
from ah.llm.process_backend import (
    LLMBackendStatus,
    LLMRequestDiagnostic,
    LLMResponse,
)


def _compose_prompt(system: str, prompt: str) -> str:
    system = str(system or "").strip()
    prompt = str(prompt or "").strip()
    if system and prompt:
        return f"{system}\n\n{prompt}"
    return system or prompt


def _rank_choice_scores(scores: dict[str, float]) -> tuple[str, float]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        raise RuntimeError("fixed-choice scoring produced no result")
    best_choice, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else best_score
    return best_choice, float(best_score - second_score)


class OllamaBackend:
    """HTTP backend for a local Ollama server (no torch in AH process)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = OllamaClient(
            config.llm.ollama_base_url,
            timeout_seconds=config.llm.request_timeout_seconds,
        )
        self._status_lock = Lock()
        self._recent_log: deque[str] = deque(maxlen=200)
        self._stage = "stopped"
        self._last_role: str | None = None
        self._request_count = 0
        self._request_diagnostics: deque[LLMRequestDiagnostic] = deque(maxlen=50)
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
                placement_summary=(
                    f"models={len(self._available_models)}"
                    if self._available_models
                    else "models=unknown"
                ),
                effective_4bit=None,
                current_stage=self._stage,
                last_role=self._last_role,
                request_count=self._request_count,
                recent_log=tuple(self._recent_log),
            )

    def request_diagnostics(self) -> tuple[LLMRequestDiagnostic, ...]:
        with self._status_lock:
            return tuple(self._request_diagnostics)

    def list_models(self) -> tuple[str, ...]:
        return self._available_models

    def _append_log(self, text: str) -> None:
        with self._status_lock:
            self._recent_log.append(text)

    def _record_request(
        self,
        *,
        req_id: str,
        role: str,
        prompt: str,
        system: str,
        response_text: str,
        override: dict[str, Any] | None = None,
        response_meta: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        override = override or {}
        response_meta = response_meta or {}
        raw_choices = override.get("choice_outputs")
        choice_outputs = tuple(str(item) for item in raw_choices) if isinstance(raw_choices, list) else ()

        def _score_map(name: str) -> dict[str, float] | None:
            raw = response_meta.get(name)
            if not isinstance(raw, dict):
                return None
            parsed: dict[str, float] = {}
            for key, value in raw.items():
                try:
                    parsed[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
            return parsed or None

        choice_scores = _score_map("choice_scores")
        calibration_choice_scores = _score_map("calibration_choice_scores")
        calibrated_choice_scores = _score_map("calibrated_choice_scores")
        raw_winner = response_meta.get("choice")
        choice_winner = None if raw_winner is None else str(raw_winner)
        try:
            raw_choice_margin = float(response_meta.get("raw_choice_margin"))
        except (TypeError, ValueError):
            raw_choice_margin = None
        try:
            choice_margin = float(response_meta.get("choice_margin"))
        except (TypeError, ValueError):
            choice_margin = None
        raw_mode = response_meta.get("choice_scoring_mode")
        choice_scoring_mode = None if raw_mode is None else str(raw_mode)
        try:
            threshold = float(override.get("decision_margin_threshold"))
        except (TypeError, ValueError):
            threshold = None
        decision_accepted = None
        if choice_margin is not None and threshold is not None:
            decision_accepted = choice_margin >= threshold

        with self._status_lock:
            sequence = self._request_count
            self._request_diagnostics.append(
                LLMRequestDiagnostic(
                    sequence=sequence,
                    req_id=req_id,
                    role=role,
                    prompt=prompt,
                    system=system,
                    response_text=response_text,
                    choice_outputs=choice_outputs,
                    choice_scores=choice_scores,
                    calibration_choice_scores=calibration_choice_scores,
                    calibrated_choice_scores=calibrated_choice_scores,
                    choice_winner=choice_winner,
                    raw_choice_margin=raw_choice_margin,
                    choice_margin=choice_margin,
                    choice_scoring_mode=choice_scoring_mode,
                    decision_margin_threshold=threshold,
                    decision_accepted=decision_accepted,
                    error=error,
                )
            )
            state = "ERROR" if error else "OK"
            detail = f": {error}" if error else ""
            self._recent_log.append(f"[request #{sequence}] role={role} {state}{detail}")
        log_llm_request(
            sequence=sequence,
            req_id=req_id,
            role=role,
            prompt=prompt,
            system=system,
            response_text=response_text,
            error=error,
            choice_winner=choice_winner,
            choice_margin=choice_margin,
            choice_outputs=choice_outputs,
        )

    def start(self) -> None:
        if self._running:
            return
        if self.config.llm.history_messages != 0:
            raise ValueError("Only stateless LLM requests (history_messages=0) are supported")
        model = self.config.llm.ollama_model.strip()
        if not model:
            raise ValueError("llm.ollama_model is not configured")
        with self._status_lock:
            self._recent_log.clear()
            self._stage = "starting"
        self._append_log(f"[starting] connecting to {self.config.llm.ollama_base_url}")
        try:
            models = self._client.list_models()
        except OllamaClientError as exc:
            self._stage = "stopped"
            raise RuntimeError(str(exc)) from exc
        self._available_models = tuple(models)
        if model not in models:
            available = ", ".join(models[:8]) + ("…" if len(models) > 8 else "")
            raise RuntimeError(
                f"Ollama model {model!r} is not available. Pulled models: {available or '<none>'}"
            )
        self._running = True
        self._ready = True
        with self._status_lock:
            self._stage = "ready"
        self._append_log(f"[ready] ollama model={model}")

    def stop(self) -> None:
        self._running = False
        self._ready = False
        with self._status_lock:
            self._stage = "stopped"

    def restart(self) -> None:
        self.stop()
        self.start()

    def _generation_options(self, override: dict[str, Any]) -> dict[str, Any]:
        temperature = float(override.get("temperature", self.config.llm.temperature))
        top_p = float(override.get("top_p", self.config.llm.top_p))
        top_k = int(override.get("top_k", self.config.llm.top_k))
        repetition_penalty = float(override.get("repetition_penalty", self.config.llm.repetition_penalty))
        max_new = int(override.get("max_new_tokens", self.config.llm.max_new_tokens))
        options: dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repetition_penalty,
            "num_predict": max_new,
        }
        if temperature <= 0:
            options["temperature"] = 0
        return options

    def _score_exact_continuations(self, prefix: str, choices: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        model = self.config.llm.ollama_model
        for choice in choices:
            if not str(choice).strip():
                raise ValueError("choice_outputs must contain non-empty strings")
            data = self._client.generate(
                model=model,
                prompt=prefix + str(choice),
                options={"temperature": 0, "num_predict": 1},
                logprobs=True,
            )
            scores[str(choice)] = self._client.mean_logprob(data)
        return scores

    def _score_fixed_choice_details(self, prefix: str, choices: list[str]) -> dict[str, Any]:
        scores = self._score_exact_continuations(prefix, choices)
        best_choice, margin = _rank_choice_scores(scores)
        return {
            "choice": best_choice,
            "choice_scores": scores,
            "choice_margin": margin,
            "choice_scoring_mode": "raw_exact_continuation",
        }

    def _score_calibrated_choice_details(
        self,
        prefix: str,
        calibration_prefix: str,
        choices: list[str],
    ) -> dict[str, Any]:
        actual = self._score_exact_continuations(prefix, choices)
        baseline = self._score_exact_continuations(calibration_prefix, choices)
        calibrated = {choice: float(actual[choice] - baseline[choice]) for choice in choices}
        best_choice, calibrated_margin = _rank_choice_scores(calibrated)
        _raw_best, raw_margin = _rank_choice_scores(actual)
        return {
            "choice": best_choice,
            "choice_scores": actual,
            "calibration_choice_scores": baseline,
            "calibrated_choice_scores": calibrated,
            "raw_choice_margin": raw_margin,
            "choice_margin": calibrated_margin,
            "choice_scoring_mode": "content_free_calibrated_semantic_completion",
        }

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
        if not system:
            fallback = self.config.paths.agent_prompt_path or self.config.paths.system_prompt_path
            if fallback is not None:
                try:
                    system = fallback.read_text(encoding="utf-8")
                except FileNotFoundError:
                    system = ""
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
            self._last_role = role
            self._request_count += 1
            self._stage = f"generating:{role}"
        try:
            prefix = _compose_prompt(system, prompt)
            choice_outputs_raw = defaults.get("choice_outputs")
            if choice_outputs_raw is not None:
                if not isinstance(choice_outputs_raw, list):
                    raise ValueError("choice_outputs must be a JSON list")
                choices = [str(item) for item in choice_outputs_raw]
                if len(set(choices)) != len(choices):
                    raise ValueError("choice_outputs must be unique")
                calibration_prompt = defaults.get("choice_calibration_prompt")
                if calibration_prompt is not None:
                    calibration_system = str(
                        defaults.get("choice_calibration_system", system or "")
                    )
                    calibration_prefix = _compose_prompt(calibration_system, str(calibration_prompt))
                    details = self._score_calibrated_choice_details(prefix, calibration_prefix, choices)
                else:
                    details = self._score_fixed_choice_details(prefix, choices)
                response_text = str(details["choice"])
                response_meta = {"text": response_text, **details}
                self._record_request(
                    req_id=req_id,
                    role=role,
                    prompt=prompt,
                    system=system,
                    response_text=response_text,
                    override=defaults,
                    response_meta=response_meta,
                )
                return LLMResponse(response_text, response_meta)

            messages: list[dict[str, str]] = []
            if system.strip():
                messages.append({"role": "system", "content": system.strip()})
            messages.append({"role": "user", "content": prompt})
            response_text = self._client.chat(
                model=self.config.llm.ollama_model,
                messages=messages,
                options=self._generation_options(defaults),
            )
            response_meta = {"text": response_text, "ok": True}
            self._record_request(
                req_id=req_id,
                role=role,
                prompt=prompt,
                system=system,
                response_text=response_text,
                override=defaults,
                response_meta=response_meta,
            )
            return LLMResponse(response_text, response_meta)
        except Exception as exc:
            error = str(exc)
            self._record_request(
                req_id=req_id,
                role=role,
                prompt=prompt,
                system=system,
                response_text="",
                override=defaults,
                error=error,
            )
            raise
        finally:
            with self._status_lock:
                self._stage = "ready" if self._ready else "stopped"
