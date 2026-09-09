from __future__ import annotations

from typing import Sequence

from ah.config import AppConfig
from ah.llm.lmstudio_client import LMStudioClient
from ah.llm.ollama_client import OllamaClient
from rag.embeddings import (
    EmbeddingClient,
    EmbeddingClientError,
    FakeEmbeddingClient,
)


class OllamaEmbeddingClient:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self.client = client
        self.model = str(model).strip()
        if not self.model:
            raise EmbeddingClientError("Ollama embedding model is not configured")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.client.embed(model=self.model, texts=texts)


class LMStudioEmbeddingClient:
    def __init__(self, client: LMStudioClient, model: str) -> None:
        self.client = client
        self.model = str(model).strip()
        if not self.model:
            raise EmbeddingClientError("LM Studio embedding model is not configured")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self.client.embed(model=self.model, texts=texts)


def build_embedding_client(config: AppConfig) -> EmbeddingClient:
    backend = str(config.llm.backend or "").strip().lower()
    if backend == "builtin_process":
        raise EmbeddingClientError(
            "M4 embeddings require ollama or lmstudio; builtin_process is fail-closed"
        )
    model = config.llm.embedding_model_name()
    if not model:
        raise EmbeddingClientError(f"{backend} embedding model is not configured")
    if backend == "ollama":
        return OllamaEmbeddingClient(
            OllamaClient(config.llm.ollama_base_url, timeout_seconds=config.llm.request_timeout_seconds),
            model,
        )
    if backend == "lmstudio":
        return LMStudioEmbeddingClient(
            LMStudioClient(
                config.llm.lmstudio_base_url,
                timeout_seconds=config.llm.request_timeout_seconds,
                api_key=config.llm.lmstudio_api_key,
            ),
            model,
        )
    raise EmbeddingClientError(f"Unsupported llm.backend for embeddings: {config.llm.backend}")


__all__ = [
    "EmbeddingClient",
    "EmbeddingClientError",
    "FakeEmbeddingClient",
    "LMStudioEmbeddingClient",
    "OllamaEmbeddingClient",
    "build_embedding_client",
]
