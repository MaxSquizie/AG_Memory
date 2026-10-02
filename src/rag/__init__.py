"""Isolated Vanilla RAG baseline. This package must not import or write AH."""

from .embeddings import EmbeddingClient, EmbeddingClientError, FakeEmbeddingClient
from .vanilla import (
    RAG_DEFAULT_TOP_K,
    RAG_ROLE,
    RAG_SYSTEM_PROMPT,
    GenerativeBackend,
    RagAnswer,
    RagChunk,
    RagHit,
    VanillaRag,
    VanillaRagIndex,
    chunk_documents,
    cosine_similarity,
    is_unknown_answer,
    normalize_text,
    rag_hallucinated,
)

__all__ = [
    "EmbeddingClient",
    "EmbeddingClientError",
    "FakeEmbeddingClient",
    "GenerativeBackend",
    "RAG_DEFAULT_TOP_K",
    "RAG_ROLE",
    "RAG_SYSTEM_PROMPT",
    "RagAnswer",
    "RagChunk",
    "RagHit",
    "VanillaRag",
    "VanillaRagIndex",
    "chunk_documents",
    "cosine_similarity",
    "is_unknown_answer",
    "normalize_text",
    "rag_hallucinated",
]
