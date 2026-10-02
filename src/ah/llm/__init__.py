from .process_backend import (
    LLMActiveRequestDiagnostic,
    LLMBackendStatus,
    LLMRequestDiagnostic,
    LLMResponse,
    LocalLLMProcessBackend,
)
from .ollama_client import OllamaClient, OllamaClientError
from .ollama_backend import OllamaBackend
from .lmstudio_client import LMStudioClient, LMStudioClientError
from .lmstudio_backend import LMStudioBackend
from .android_npu_backend import AndroidNpuBackend, register_engine
from .factory import LLMBackend, build_llm_backend

_EMBEDDING_EXPORTS = {
    "EmbeddingClient",
    "EmbeddingClientError",
    "FakeEmbeddingClient",
    "LMStudioEmbeddingClient",
    "OllamaEmbeddingClient",
    "build_embedding_client",
}

__all__ = [
    "LLMActiveRequestDiagnostic", "LLMBackendStatus", "LLMRequestDiagnostic",
    "LLMResponse", "LocalLLMProcessBackend", "OllamaClient", "OllamaClientError",
    "OllamaBackend", "LMStudioClient", "LMStudioClientError", "LMStudioBackend",
    "AndroidNpuBackend", "register_engine",
    "LLMBackend", "build_llm_backend",
    "EmbeddingClient", "EmbeddingClientError", "FakeEmbeddingClient",
    "LMStudioEmbeddingClient", "OllamaEmbeddingClient", "build_embedding_client",
]


def __getattr__(name: str):
    if name in _EMBEDDING_EXPORTS:
        from . import embeddings as _embeddings
        value = getattr(_embeddings, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
