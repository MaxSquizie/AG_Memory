from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence
import math
import re

from rag.embeddings import EmbeddingClient


RAG_DEFAULT_TOP_K = 6
RAG_ROLE = "m4_rag"
RAG_SYSTEM_PROMPT = (
    "Отвечай только по приведённым выдержкам корпуса. "
    "Если ответа нет в выдержках, ответь ровно UNKNOWN. "
    "Не используй внешние знания и не выдумывай факты."
)


class GenerativeBackend(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict | None = None,
        role: str = "generic",
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class RagChunk:
    chunk_id: str
    document_id: str
    text: str
    vector: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class RagHit:
    chunk: RagChunk
    score: float


@dataclass(frozen=True, slots=True)
class RagAnswer:
    answer: str
    chunk_ids: tuple[str, ...]
    retrieved_texts: tuple[str, ...]
    scores: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class VanillaRagIndex:
    chunks: tuple[RagChunk, ...]
    embed_model: str = ""

    def retrieve(self, query_vector: Sequence[float], *, top_k: int = RAG_DEFAULT_TOP_K) -> tuple[RagHit, ...]:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        scored: list[RagHit] = []
        for chunk in self.chunks:
            if chunk.vector is None:
                continue
            scored.append(RagHit(chunk, cosine_similarity(query_vector, chunk.vector)))
        scored.sort(key=lambda item: item.score, reverse=True)
        return tuple(scored[:top_k])


class VanillaRag:
    """Isolated vector RAG. Chunks, retrieves, and generates without writing AH."""

    def __init__(
        self,
        embedder: EmbeddingClient,
        generator: GenerativeBackend | None = None,
        *,
        top_k: int = RAG_DEFAULT_TOP_K,
        embed_model: str = "",
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        self.embedder = embedder
        self.generator = generator
        self.top_k = int(top_k)
        self.embed_model = str(embed_model or "")

    def build_index(self, specs: Sequence[object]) -> VanillaRagIndex:
        chunks = chunk_documents(specs)
        if not chunks:
            return VanillaRagIndex((), self.embed_model)
        vectors = self.embedder.embed([item.text for item in chunks])
        if len(vectors) != len(chunks):
            raise RuntimeError("Embedding client returned the wrong number of vectors")
        indexed = tuple(
            RagChunk(item.chunk_id, item.document_id, item.text, tuple(float(value) for value in vector))
            for item, vector in zip(chunks, vectors)
        )
        return VanillaRagIndex(indexed, self.embed_model)

    def retrieve(self, query: str, index: VanillaRagIndex) -> tuple[RagHit, ...]:
        vector = self.embedder.embed([query])[0]
        return index.retrieve(vector, top_k=self.top_k)

    def answer(self, question: str, index: VanillaRagIndex) -> RagAnswer:
        hits = self.retrieve(question, index)
        if not hits:
            return RagAnswer("UNKNOWN", (), (), ())
        if self.generator is None:
            raise RuntimeError("Vanilla RAG generate requires an LLM backend")
        prompt = _rag_user_prompt(question, hits)
        response = self.generator.generate(
            prompt,
            system=RAG_SYSTEM_PROMPT,
            override={"temperature": 0.0},
            role=RAG_ROLE,
        )
        text = str(getattr(response, "text", response) or "").strip() or "UNKNOWN"
        return RagAnswer(
            text,
            tuple(item.chunk.chunk_id for item in hits),
            tuple(item.chunk.text for item in hits),
            tuple(item.score for item in hits),
        )


def chunk_documents(specs: Sequence[object]) -> tuple[RagChunk, ...]:
    """Chunk objects with ``document_id`` and ``paragraphs`` (``text``, ``paragraph_index``)."""

    chunks: list[RagChunk] = []
    for spec in specs:
        document_id = str(getattr(spec, "document_id"))
        for paragraph in getattr(spec, "paragraphs"):
            text = str(getattr(paragraph, "text", "") or "").strip()
            if not text:
                continue
            index = getattr(paragraph, "paragraph_index", len(chunks))
            chunks.append(
                RagChunk(
                    chunk_id=f"{document_id}:{index}",
                    document_id=document_id,
                    text=text,
                )
            )
    return tuple(chunks)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        fa = float(a)
        fb = float(b)
        dot += fa * fb
        left_norm += fa * fa
        right_norm += fb * fb
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def normalize_text(value: str) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def is_unknown_answer(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return True
    if normalized in {"unknown", "неизвестно"}:
        return True
    return normalized.startswith("unknown")


def answer_supported_by_chunks(
    answer: str,
    retrieved_texts: Sequence[str],
    must_contain: Sequence[str] = (),
) -> bool:
    blob = normalize_text(" ".join(str(item) for item in retrieved_texts))
    answer_norm = normalize_text(answer)
    if not blob or not answer_norm or is_unknown_answer(answer):
        return False
    if answer_norm in blob:
        return True
    anchors = [normalize_text(item) for item in must_contain if normalize_text(item)]
    if anchors and all(item in blob for item in anchors) and any(item in answer_norm for item in anchors):
        return True
    words = [word for word in answer_norm.split() if len(word) >= 4]
    if not words:
        return False
    hits = sum(1 for word in words if word in blob)
    return hits >= max(1, (len(words) + 1) // 2)


def rag_hallucinated(
    answer: str,
    retrieved_texts: Sequence[str],
    must_contain: Sequence[str] = (),
) -> bool:
    if is_unknown_answer(answer):
        return False
    return not answer_supported_by_chunks(answer, retrieved_texts, must_contain)


def _rag_user_prompt(question: str, hits: Sequence[RagHit]) -> str:
    blocks: list[str] = ["Выдержки:"]
    for index, hit in enumerate(hits, 1):
        blocks.append(
            f"[{index}] {hit.chunk.chunk_id} ({hit.chunk.document_id})\n{hit.chunk.text.strip()}"
        )
    blocks.append(f"Вопрос: {str(question).strip()}")
    blocks.append("Ответь кратко только по выдержкам. Если ответа нет — UNKNOWN.")
    return "\n\n".join(blocks)
