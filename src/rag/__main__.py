from __future__ import annotations

print(
    "Package `rag` is the isolated Vanilla RAG baseline: chunk, embed, retrieve, generate.\n"
    "It does not import AH Core and does not write memory.\n\n"
    "Offline tests:\n"
    "  PYTHONPATH=src python3 -m pytest tests/test_m4_rag_baseline.py\n\n"
    "Live AH vs RAG (needs Ollama or LM Studio embeddings + generator):\n"
    "  PYTHONPATH=src python3 -m ah.cli --config config/ollama.toml m4-acceptance\n"
    "  PYTHONPATH=src python3 -m ah.cli --config config/lmstudio.toml m4-acceptance\n\n"
    "Document corpus: data/document_acceptance/README.md"
)
