from __future__ import annotations

from types import SimpleNamespace

import pytest

from ah.documents import DocumentProcessingError, DocumentProcessor


def _processor(*, max_chunk_chars: int = 256) -> DocumentProcessor:
    return DocumentProcessor(SimpleNamespace(), max_chunk_chars=max_chunk_chars)


def test_chunking_never_uses_arbitrary_whitespace_inside_a_semantic_unit():
    processor = _processor()
    text = "слово " * 60

    with pytest.raises(DocumentProcessingError, match="source-grounded"):
        processor.chunk_text(text)


def test_chunking_prefers_real_sentence_boundary_and_preserves_exact_offsets():
    processor = _processor()
    first = "А" * 180 + "."
    second = " " + ("Б" * 120) + "."
    text = first + second

    chunks = processor.chunk_text(text)

    assert len(chunks) == 2
    assert chunks[0].text == first
    assert chunks[0].start == 0
    assert chunks[0].end == len(first)
    assert chunks[1].text == second
    assert chunks[1].start == len(first)
    assert chunks[1].end == len(text)
    assert "".join(chunk.text for chunk in chunks) == text


def test_semicolon_is_not_treated_as_safe_relation_boundary():
    processor = _processor()
    first_clause = "А" * 190 + ";"
    second_clause = " поэтому " + ("Б" * 120) + "."
    text = first_clause + second_clause

    with pytest.raises(DocumentProcessingError, match="source-grounded"):
        processor.chunk_text(text)


def test_single_newline_is_not_treated_as_safe_semantic_boundary():
    processor = _processor()
    first_line = "А" * 190 + "\n"
    second_line = "потому что " + ("Б" * 120) + "."
    text = first_line + second_line

    with pytest.raises(DocumentProcessingError, match="source-grounded"):
        processor.chunk_text(text)


def test_paragraph_chunks_cover_source_once_with_contiguous_global_offsets():
    processor = _processor()
    paragraph = ("Связное предложение. " * 9).rstrip() + ".\n\n"
    text = paragraph * 4 + "Финал."

    chunks = processor.chunk_text(text)

    assert len(chunks) > 1
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)
    assert all(left.end == right.start for left, right in zip(chunks, chunks[1:]))
    assert sum(chunk.end - chunk.start for chunk in chunks) == len(text)
    assert "".join(chunk.text for chunk in chunks) == text
