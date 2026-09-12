from __future__ import annotations

from types import SimpleNamespace

from ah.perception import lexical_recovery_core as core
from ah.perception.lexical_recovery import (
    LexicalRecovery,
    LexicalRecoveryStatus,
)


class _Morphology:
    def is_known(self, word: str) -> bool:
        return False

    def indexed_candidates(self, word: str, *, max_distance: int, limit: int):
        del word, max_distance, limit
        return ("купал", "купил")


class _TieRecovery(LexicalRecovery):
    def _rank_candidates(self, token, candidates, tokens, graph):
        del token, candidates, tokens, graph
        return (
            core._RankedCandidate("купал", (), 0.72, 1.0, 0.8, 0.5, 1.00),
            core._RankedCandidate("купил", (), 0.72, 1.0, 0.8, 0.5, 0.99),
        )

    def _protected_oov(self, token, tokens, graph, ranked):
        del token, tokens, graph, ranked
        return False

    @staticmethod
    def _has_lexical_context(token, tokens, graph):
        del token, tokens, graph
        return True

    def _context_text(self, token, tokens, graph):
        del token, tokens, graph
        return "Иван … книгу"


class _WeakEmbeddingThenChoice:
    def __init__(self) -> None:
        self.embedding_calls = 0
        self.choice_calls = 0

    def rank_embedding(self, context, candidates):
        assert context == "Иван … книгу"
        assert candidates == ("купал", "купил")
        self.embedding_calls += 1
        return {"купал": 0.50, "купил": 0.50}

    def rank(self, context, candidates):
        raise AssertionError("rank_embedding should be preferred")

    def choose(self, context, candidates):
        assert self.embedding_calls == 1
        self.choice_calls += 1
        return "купил"


class _EmbeddingFailure:
    def __init__(self) -> None:
        self.choice_calls = 0

    def rank_embedding(self, context, candidates):
        del context, candidates
        raise RuntimeError("embedding offline")

    def rank(self, context, candidates):
        raise AssertionError("rank_embedding should be preferred")

    def choose(self, context, candidates):
        del context, candidates
        self.choice_calls += 1
        return "купил"


def _token():
    return SimpleNamespace(
        index=1,
        text="купл",
        provenance_text="купл",
        recovery=None,
    )


def test_bounded_llm_choice_runs_only_after_complete_weak_embedding_result() -> None:
    reranker = _WeakEmbeddingThenChoice()
    recovery = _TieRecovery(_Morphology(), semantic_reranker=reranker)

    decision = recovery.recover("Иван купл книгу.", (_token(),), object())[0]

    assert reranker.embedding_calls == 1
    assert reranker.choice_calls == 1
    assert decision.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert decision.normalized_text == "купил"
    assert decision.confidence == 0.90
    assert "bounded lexical LLM tie-break" in (decision.reason or "")


def test_embedding_transport_failure_never_escalates_to_llm_autocorrection() -> None:
    reranker = _EmbeddingFailure()
    recovery = _TieRecovery(_Morphology(), semantic_reranker=reranker)

    decision = recovery.recover("Иван купл книгу.", (_token(),), object())[0]

    assert reranker.choice_calls == 0
    assert decision.status is LexicalRecoveryStatus.AMBIGUOUS
    assert decision.normalized_text is None
    assert "embedding offline" in (decision.reason or "")
