from __future__ import annotations

from ah.config import AppConfig
from ah.llm.lmstudio_backend import LMStudioBackend
from ah.llm.ollama_backend import OllamaBackend
from ah.llm.process_backend import LocalLLMProcessBackend

LLMBackend = LocalLLMProcessBackend | OllamaBackend | LMStudioBackend


def build_llm_backend(config: AppConfig) -> LLMBackend | None:
    if not config.llm.enabled:
        return None
    backend = config.llm.backend.strip().lower()
    if backend == "ollama":
        return OllamaBackend(config)
    if backend == "lmstudio":
        return LMStudioBackend(config)
    if backend == "builtin_process":
        return LocalLLMProcessBackend(config)
    raise ValueError(f"Unsupported llm.backend: {config.llm.backend}")
