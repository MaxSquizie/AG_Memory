from __future__ import annotations

from typing import Protocol, Sequence
import hashlib
import math
import re


class EmbeddingClientError(RuntimeError):
    pass


class EmbeddingClient(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FakeEmbeddingClient:
    """Deterministic embedder for pytest. No network, no AH writes."""

    def __init__(
        self,
        table: dict[str, Sequence[float]] | None = None,
        *,
        dim: int = 8,
    ) -> None:
        self.dim = int(dim)
        if self.dim <= 0:
            raise ValueError("FakeEmbeddingClient dim must be > 0")
        self.table = {
            _normalize_embed_key(key): [float(value) for value in vector]
            for key, vector in (table or {}).items()
        }
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        batch = tuple(str(item) for item in texts)
        self.calls.append(batch)
        vectors: list[list[float]] = []
        for text in batch:
            key = _normalize_embed_key(text)
            if key in self.table:
                vectors.append(list(self.table[key]))
            elif text in self.table:
                vectors.append([float(value) for value in self.table[text]])
            else:
                vectors.append(_hash_vector(text, self.dim))
        return vectors


def _normalize_embed_key(value: str) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def _hash_vector(text: str, dim: int) -> list[float]:
    digest = hashlib.sha256(str(text).encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < dim:
        digest = hashlib.sha256(digest).digest()
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dim:
                break
    norm = math.sqrt(sum(item * item for item in values))
    if norm <= 0.0:
        values[0] = 1.0
        return values
    return [item / norm for item in values]
