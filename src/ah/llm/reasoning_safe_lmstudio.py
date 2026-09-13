from __future__ import annotations

from typing import Any
import uuid

from ah.llm.lmstudio_backend import (
    LMStudioBackend as _BaseLMStudioBackend,
    _compose_prompt,
    _strip_thinking,
)
from ah.llm.process_backend import (
    LLMActiveRequestDiagnostic,
    LLMRequestDiagnostic,
    LLMResponse,
)


class LMStudioBackend(_BaseLMStudioBackend):
    """LM Studio backend whose ``enable_thinking=False`` is a transport guarantee.

    The OpenAI-compatible endpoint accepts ``enable_thinking`` only as a
    model/template-specific extension and some LM Studio/Qwen combinations still
    spend the complete output budget on hidden reasoning. LM Studio's native chat
    API exposes the explicit ``reasoning='off'`` contract, so every request that
    disables thinking uses that endpoint -- including final ``role='agent'``
    generation, not only bounded perception probes.

    When thinking is explicitly enabled we retain the base compatibility transport
    unchanged. There is deliberately no silent transport fallback: a deployment
    that cannot honour the requested reasoning mode must fail rather than consume
    hidden reasoning as visible protocol/answer content.
    """

    @staticmethod
    def _is_protocol_probe(role: str) -> bool:
        return (
            role.startswith("perception_")
            or role.startswith("semantic_")
            or role == "lexical_recovery_choice"
        )

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict[str, Any] | None = None,
        role: str = "generic",
    ) -> LLMResponse:
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

        # Explicit thinking remains owned by the original implementation. This also
        # preserves its validation for unsupported choice_outputs requests.
        if bool(defaults.get("enable_thinking", False)):
            return super().generate(
                prompt,
                system=system,
                override=override,
                role=role,
            )

        if not self._running or not self._ready:
            raise RuntimeError("LLM backend is not running")
        if defaults.get("choice_outputs") is not None:
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
            self._active_request = LLMActiveRequestDiagnostic(
                seq, req_id, role, prompt, system
            )

        response_text = ""
        response_data: dict[str, Any] = {}
        error: str | None = None
        input_tokens: int | None = None
        is_protocol_probe = self._is_protocol_probe(role)
        try:
            options = self._generation_options(defaults)
            response_data = self._client.native_chat(
                model=self._active_model,
                prompt=str(prompt),
                system=str(system or ""),
                temperature=options["temperature"],
                top_p=options["top_p"],
                top_k=options["top_k"],
                repeat_penalty=options["repeat_penalty"],
                max_tokens=options["max_tokens"],
                reasoning="off",
            )
            response_text = self._client.native_chat_text(response_data)
            stats = response_data.get("stats")
            if isinstance(stats, dict):
                try:
                    input_tokens = int(stats.get("input_tokens"))
                except (TypeError, ValueError):
                    input_tokens = None

            # Protocol calls are always stripped; ordinary generation follows the
            # configured presentation policy. Hidden native reasoning items are
            # never returned by native_chat_text in either case.
            if self.config.llm.strip_thinking or is_protocol_probe:
                response_text = _strip_thinking(response_text)
            return LLMResponse(
                response_text,
                {"text": response_text, **response_data},
            )
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
