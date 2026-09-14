from __future__ import annotations

from types import SimpleNamespace

from ah.llm import LLMResponse
from ah.perception import lexical_recovery_core as core
from ah.perception.lexical_recovery import (
    EmbeddingSemanticReranker,
    LexicalRecovery,
    LexicalRecoveryStatus,
)


_CANDIDATES = ("хамово", "пайпов", "хайдов", "хасково")


class _Morphology:
    def is_known(self, word: str) -> bool:
        return False

    def indexed_candidates(self, word: str, *, max_distance: int, limit: int):
        del word, max_distance, limit
        return _CANDIDATES


class _SlangRecovery(LexicalRecovery):
    def _rank_candidates(self, token, candidates, tokens, graph):
        del token, candidates, tokens, graph
        return tuple(
            core._RankedCandidate(
                candidate,
                (),
                0.80,
                1.0,
                0.50,
                0.50,
                1.00,
            )
            for candidate in _CANDIDATES
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
        return "Звучит …"


class _SourceAwareReranker:
    def __init__(self) -> None:
        self.source_calls = 0

    def rank_embedding(self, context, candidates):
        assert context == "Звучит …"
        assert candidates == _CANDIDATES
        return {candidate: 0.50 for candidate in candidates}

    def rank(self, context, candidates):
        raise AssertionError("rank_embedding should be preferred")

    def choose_source(self, context, source, candidates):
        assert context == "Звучит …"
        assert source == "хайпово"
        assert candidates == _CANDIDATES
        self.source_calls += 1
        return source


def _token():
    return SimpleNamespace(
        index=2,
        text="хайпово",
        provenance_text="хайпово",
        recovery=None,
    )


def test_contextually_valid_oov_is_preserved_instead_of_forced_to_dictionary_word() -> None:
    reranker = _SourceAwareReranker()
    recovery = _SlangRecovery(_Morphology(), semantic_reranker=reranker)

    decision = recovery.recover("Звучит хайпово", (_token(),), object())[0]

    assert reranker.source_calls == 1
    assert decision.status is LexicalRecoveryStatus.UNKNOWN_TOKEN
    assert decision.normalized_text == "хайпово"
    assert decision.alternatives == _CANDIDATES
    assert "preserved exact source OOV" in (decision.reason or "")


class _SourceChoiceProvider:
    def __init__(self) -> None:
        self.prompt = ""
        self.override = None

    def embed(self, texts):
        return [[1.0] for _ in texts]

    def generate(self, prompt, *, system="", override=None, role="generic"):
        del system
        assert role == "lexical_recovery_choice"
        self.prompt = prompt
        self.override = override
        return LLMResponse("SOURCE", {})


def test_source_aware_fixed_choice_exposes_exact_oov_without_allowing_invention() -> None:
    provider = _SourceChoiceProvider()
    reranker = EmbeddingSemanticReranker(provider)

    chosen = reranker.choose_source("Звучит …", "хайпово", _CANDIDATES)

    assert chosen == "хайпово"
    assert "SOURCE TOKEN:\nхайпово" in provider.prompt
    assert "C1 = хамово" in provider.prompt
    assert provider.override["enable_thinking"] is False
