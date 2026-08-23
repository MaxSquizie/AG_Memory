from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import re

from ah.config import LLMRoleSettings
from ah.projection.contracts import AgentContext
from ah.integration.contracts import ClarificationRequest


class GeneratedText(Protocol):
    text: str


class GeneratorBackend(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict | None = None,
        role: str = "generic",
    ) -> GeneratedText: ...


class AgentOutputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LLMAgentSettings:
    system_prompt_path: Path | None = None
    generation: LLMRoleSettings = LLMRoleSettings(
        max_new_tokens=384,
        temperature=0.2,
        top_p=0.9,
        top_k=40,
        repetition_penalty=1.05,
        no_repeat_ngram_size=0,
    )
    repair_attempts: int = 1
    sanitize_context_echo: bool = True
    context_max_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.repair_attempts < 0 or self.repair_attempts > 2:
            raise ValueError("agent repair_attempts must be in [0, 2]")
        if self.context_max_tokens is not None and self.context_max_tokens <= 0:
            raise ValueError("agent context_max_tokens must be > 0 when set")


class LLMAgent:
    """Natural-language response role over deterministic AgentContext.

    This is not a second model. It is a role wrapper around the same backend used
    by LLMPerceptionService. The backend remains stateless between role calls.

    The response is also guarded against accidental AgentContext echo. H must store
    what the agent actually said, not internal CURRENT INPUT / ACTIVE MEMORY blocks.
    Raw model output remains available through backend diagnostics for debugging.
    """

    _CONTEXT_MARKERS = (
        "\nCURRENT INPUT:",
        "\nCURRENT INPUT\n",
        "\n# CURRENT INPUT",
        "\nACTIVE MEMORY:",
        "\nACTIVE MEMORY\n",
        "\n# ACTIVE MEMORY",
        "\nINFERENCE RESULTS:",
        "\nINFERENCE RESULTS\n",
        "\n# INFERENCE RESULTS",
        "\nSOURCE:",
        "\nTOKENS:",
        "\n<agent_context>",
    )

    def __init__(self, backend: GeneratorBackend, settings: LLMAgentSettings | None = None) -> None:
        self.backend = backend
        self.settings = settings or LLMAgentSettings()

    def respond(self, context: AgentContext) -> str:
        generation = self.settings.generation
        override = self._generation_override(generation)
        if self.settings.context_max_tokens is not None:
            override["max_input_tokens"] = self.settings.context_max_tokens
        response = self.backend.generate(
            context.rendered,
            system=self._system_prompt(),
            override=override,
            role="agent",
        )
        raw = str(response.text).strip()
        cleaned, contaminated = self._sanitize(raw)
        if cleaned and (not contaminated or self.settings.sanitize_context_echo):
            return cleaned
        if not self.settings.sanitize_context_echo:
            return raw

        last_raw = raw
        for _ in range(self.settings.repair_attempts):
            repaired = self.backend.generate(
                self._repair_prompt(context, last_raw),
                system=_AGENT_REPAIR_SYSTEM_PROMPT,
                override=override,
                role="agent_repair",
            )
            last_raw = str(repaired.text).strip()
            cleaned, contaminated = self._sanitize(last_raw)
            if cleaned:
                return cleaned

        raise AgentOutputError(
            "Agent output contained only internal context echo after repair; "
            "response was not committed to H"
        )

    def clarify(self, request: ClarificationRequest) -> str:
        """Verbalize a deterministic clarification request without selecting an option."""
        generation = self.settings.generation
        override = self._generation_override(generation)
        options = "\n".join(f"[{item.index}] {item.label}" for item in request.options)
        prompt = (
            f"AMBIGUOUS EXPRESSION:\n{request.mention}\n\n"
            f"CANDIDATES:\n{options}\n\n"
            "Ask the user one short natural-language clarification question that lets "
            "them identify exactly one candidate. Mention only the candidate labels above. "
            "Do not decide which candidate is correct and do not mention internal system details."
        )
        response = self.backend.generate(
            prompt,
            system=self._system_prompt(),
            override=override,
            role="agent_clarification",
        )
        raw = str(response.text).strip()
        cleaned, _contaminated = self._sanitize(raw)
        if cleaned and self._clarification_mentions_all_labels(cleaned, request):
            return cleaned
        # Clarification structure is deterministic.  A model may improve phrasing,
        # but it may not replace real option labels by opaque "[1]/[2]" placeholders
        # or silently drop one of the choices.
        return self._deterministic_clarification(request)

    @staticmethod
    def _normalize_clarification_label(text: str) -> str:
        return re.sub(r"[^\wёЁ]+", " ", text.casefold(), flags=re.UNICODE).strip()

    @classmethod
    def _clarification_mentions_all_labels(
        cls, text: str, request: ClarificationRequest
    ) -> bool:
        normalized_text = f" {cls._normalize_clarification_label(text)} "
        if not normalized_text.strip():
            return False
        for option in request.options:
            label = cls._normalize_clarification_label(option.label)
            if not label or f" {label} " not in normalized_text:
                return False
        return True

    @staticmethod
    def _deterministic_clarification(request: ClarificationRequest) -> str:
        labels = ", ".join(item.label for item in request.options)
        return f"Уточните, кого или что означает «{request.mention}»: {labels}?"

    @staticmethod
    def _generation_override(generation: LLMRoleSettings) -> dict:
        return {
            "max_new_tokens": generation.max_new_tokens,
            "temperature": generation.temperature,
            "top_p": generation.top_p,
            "top_k": generation.top_k,
            "repetition_penalty": generation.repetition_penalty,
            "no_repeat_ngram_size": generation.no_repeat_ngram_size,
            "use_cache": generation.use_cache,
        }

    def _sanitize(self, text: str) -> tuple[str, bool]:
        if not self.settings.sanitize_context_echo:
            return text.strip(), False
        candidate = text.strip()
        earliest: int | None = None
        # Prefix a newline for marker matching at position 0 without special cases.
        search = "\n" + candidate
        for marker in self._CONTEXT_MARKERS:
            idx = search.find(marker)
            if idx >= 0:
                # compensate for the synthetic leading newline
                real = max(0, idx - 1)
                earliest = real if earliest is None else min(earliest, real)
        if earliest is None:
            return candidate, False
        return candidate[:earliest].strip(), True

    @staticmethod
    def _repair_prompt(context: AgentContext, bad_output: str) -> str:
        return (
            "CURRENT USER INPUT:\n" + context.current_input
            + "\n\nBAD DRAFT:\n" + bad_output
            + "\n\nReturn only the final assistant utterance. Do not repeat any memory/context sections."
        )

    def _system_prompt(self) -> str:
        path = self.settings.system_prompt_path
        if path is not None and path.is_file():
            return path.read_text(encoding="utf-8")
        return _DEFAULT_AGENT_PROMPT


_AGENT_REPAIR_SYSTEM_PROMPT = """Верни только конечную реплику агента пользователю. Не повторяй CURRENT INPUT, ACTIVE MEMORY, INFERENCE RESULTS, UID или служебный контекст."""

_DEFAULT_AGENT_PROMPT = """Ты — текстовый агент поверх АГ-памяти.
Тебе передаётся только текущий ввод, активная семантика Workspace и результаты deterministic reasoner-а.
Отвечай пользователю естественно и по существу. Не выдумывай факты, которых нет в текущем вводе или переданной памяти.
Не обсуждай внутренние UID, x, w, ticks, decay, Workspace, trace и устройство памяти, если пользователь прямо об этом не спрашивает.
Не выполняй скрытый логический proof вместо reasoner-а и не объявляй неизвестное известным.
Не повторяй секции CURRENT INPUT, ACTIVE MEMORY или INFERENCE RESULTS в ответе.
"""

