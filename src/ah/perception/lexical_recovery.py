from __future__ import annotations

"""Lexical recovery facade with bounded semantic tie-breaking.

The deterministic implementation remains in :mod:`lexical_recovery_core`.  This
facade adds exactly one extra stage after that implementation has narrowed an OOV
token to a small, morphosyntactically plausible shortlist:

    deterministic ranking -> embeddings -> bounded SOURCE/correction choice

The model never proposes a spelling.  It can only preserve the exact source token,
return one label for an existing correction candidate, or return UNKNOWN.  Preserving
the source yields ``UNKNOWN_TOKEN`` rather than a fabricated dictionary correction;
UNKNOWN remains a genuine unresolved ambiguity.  If embeddings fail rather than
merely remain uncertain, the LLM stage is not used and recovery still fails closed.
"""

from pathlib import Path
from typing import Any, Mapping, Sequence

from . import lexical_recovery_core as _core
from .lexical_recovery_core import *  # noqa: F401,F403 - stable public surface
from .probe_protocol import (
    CHOICE_MAX_NEW_TOKENS,
    ProbeProtocolError,
    compose_choice_prompt,
    decode_choice,
)


LexicalRecoveryStatus = _core.LexicalRecoveryStatus
TokenCandidate = _core.TokenCandidate
SemanticCandidateReranker = _core.SemanticCandidateReranker
EmbeddingProvider = _core.EmbeddingProvider
weighted_damerau_levenshtein = _core.weighted_damerau_levenshtein


class EmbeddingSemanticReranker(_core.EmbeddingSemanticReranker):
    """Embedding reranker plus an optional one-shot fixed-choice semantic probe."""

    def __init__(self, provider: EmbeddingProvider, *, choice_prompt_path: Path | None = None) -> None:
        super().__init__(provider)
        self.choice_prompt_path = choice_prompt_path or (
            Path(__file__).resolve().parents[3]
            / "prompts"
            / "perception"
            / "lexical_recovery_choice.txt"
        )

    def rank_embedding(
        self, context: str, candidates: tuple[str, ...]
    ) -> dict[str, float]:
        return super().rank(context, candidates)

    def rank(self, context: str, candidates: tuple[str, ...]) -> dict[str, float]:
        # Compatibility for callers that only implement/use the historical scorer.
        return self.rank_embedding(context, candidates)

    def _bounded_choice(
        self,
        context: str,
        candidates: tuple[str, ...],
        *,
        source: str | None = None,
    ) -> str | None:
        """Resolve SOURCE vs supplied corrections without inventing lexical forms."""

        generate = getattr(self.provider, "generate", None)
        minimum_candidates = 1 if source is not None else 2
        if (
            not callable(generate)
            or not context.strip()
            or len(candidates) < minimum_candidates
        ):
            return None
        if not self.choice_prompt_path.is_file():
            # A missing explicit service prompt is a configuration problem.  The
            # caller catches this and remains AMBIGUOUS rather than inventing hidden
            # instructions or silently selecting a candidate.
            raise FileNotFoundError(
                f"lexical recovery choice prompt is missing: {self.choice_prompt_path}"
            )
        instruction = self.choice_prompt_path.read_text(encoding="utf-8").strip()
        if not instruction:
            raise ValueError("lexical recovery choice prompt is empty")
        system_path = self.choice_prompt_path.with_name("probe_system.txt")
        if not system_path.is_file():
            raise FileNotFoundError(
                f"shared probe system prompt is missing: {system_path}"
            )
        system = system_path.read_text(encoding="utf-8").strip()
        if not system:
            raise ValueError("shared probe system prompt is empty")

        labels = tuple(f"C{index}" for index in range(1, len(candidates) + 1))
        options = "\n".join(
            f"{label} = {candidate}"
            for label, candidate in zip(labels, candidates)
        )
        context_lines = [f"CONTEXT:\n{context}"]
        choices: tuple[str, ...]
        if source is not None:
            context_lines.append(f"SOURCE TOKEN:\n{source}")
            choices = ("SOURCE", *labels, "UNKNOWN")
        else:
            choices = (*labels, "UNKNOWN")
        context_lines.append(f"CANDIDATE CORRECTIONS:\n{options}")
        prompt = compose_choice_prompt(
            "\n\n".join(context_lines),
            instruction,
            choices,
        )
        response = generate(
            prompt,
            system=system,
            override={
                "max_new_tokens": CHOICE_MAX_NEW_TOKENS,
                "temperature": 0.0,
                "top_p": 1.0,
                "top_k": 0,
                "repetition_penalty": 1.0,
                "no_repeat_ngram_size": 0,
                # This is an exact-label machine protocol.  Thinking-capable
                # templates must not spend the tiny answer budget on a hidden
                # reasoning channel before emitting SOURCE/C1/C2/UNKNOWN.
                "enable_thinking": False,
            },
            role="lexical_recovery_choice",
        )
        try:
            label = decode_choice(str(getattr(response, "text", "")), choices)
        except ProbeProtocolError:
            return None
        if label == "UNKNOWN":
            return None
        if label == "SOURCE":
            return source
        return candidates[labels.index(label)]

    def choose(self, context: str, candidates: tuple[str, ...]) -> str | None:
        """Backward-compatible correction-only fixed choice."""
        return self._bounded_choice(context, candidates)

    def choose_source(
        self,
        context: str,
        source: str,
        candidates: tuple[str, ...],
    ) -> str | None:
        """Choose exact SOURCE, one supplied correction, or unresolved UNKNOWN."""
        if not source.strip():
            return None
        return self._bounded_choice(context, candidates, source=source)


class LexicalRecovery(_core.LexicalRecovery):
    """Core recovery with a fixed-choice LLM only after embedding evidence."""

    def recover(self, text: str, tokens: tuple[Any, ...], graph: Any) -> tuple[TokenCandidate, ...]:
        del text  # offsets/raw evidence remain owned by the caller's graph
        if not self.available():
            return tuple(
                TokenCandidate(
                    token.index,
                    token.text,
                    token.text,
                    LexicalRecoveryStatus.EXACT,
                    confidence=1.0,
                    reason="dictionary index unavailable; recovery disabled",
                )
                for token in tokens
            )

        is_known = getattr(self.morphology, "is_known")
        indexed_candidates = getattr(self.morphology, "indexed_candidates")
        decisions: list[TokenCandidate] = []
        for token in tokens:
            raw = token.provenance_text

            prior = token.recovery
            if prior is not None and prior.status in {
                LexicalRecoveryStatus.EXACT,
                LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE,
                LexicalRecoveryStatus.UNKNOWN_TOKEN,
            }:
                decisions.append(prior)
                continue

            if not self._is_word(raw):
                word_like = bool(_core.re.search(r"\w", raw, flags=_core.re.UNICODE))
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        raw,
                        (
                            LexicalRecoveryStatus.UNKNOWN_TOKEN
                            if word_like
                            else LexicalRecoveryStatus.EXACT
                        ),
                        confidence=0.0 if word_like else 1.0,
                        reason=(
                            "protected non-Cyrillic/alphanumeric token"
                            if word_like
                            else "non-lexical token"
                        ),
                    )
                )
                continue
            if is_known(raw):
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        raw,
                        LexicalRecoveryStatus.EXACT,
                        confidence=1.0,
                        reason="dictionary exact",
                    )
                )
                continue
            if len(raw.replace("-", "")) < 3:
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        raw,
                        LexicalRecoveryStatus.UNKNOWN_TOKEN,
                        confidence=0.0,
                        reason="short OOV is unsafe to autocorrect",
                    )
                )
                continue

            generated = tuple(
                indexed_candidates(raw, max_distance=1, limit=self.max_candidates)
            )
            if not generated and len(raw.replace("-", "")) >= 7:
                generated = tuple(
                    indexed_candidates(raw, max_distance=2, limit=self.max_candidates)
                )
            ranked = self._rank_candidates(token, generated, tokens, graph)
            display = tuple(
                self._restore_case(raw, item.text) for item in ranked[:8]
            )

            if self._protected_oov(token, tokens, graph, ranked):
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        raw,
                        LexicalRecoveryStatus.UNKNOWN_TOKEN,
                        alternatives=display,
                        confidence=0.0,
                        reason="protected name/term/acronym OOV",
                    )
                )
                continue
            if not ranked:
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        raw,
                        LexicalRecoveryStatus.UNKNOWN_TOKEN,
                        confidence=0.0,
                        reason="no indexed candidate",
                    )
                )
                continue

            best = ranked[0]
            base_margin = (
                float("inf")
                if len(ranked) == 1
                else best.base_score - ranked[1].base_score
            )
            selected = best
            confidence = 0.0
            reason = ""
            preserve_source = False
            has_context = self._has_lexical_context(token, tokens, graph)

            # These deterministic gates are intentionally identical to the core
            # implementation.  The semantic model never sees cases already
            # decidable by a strong local typo signal.
            if len(ranked) == 1:
                confidence = 0.97
                reason = "unique orthographic+morphosyntactic candidate"
            elif has_context and base_margin >= 0.20:
                confidence = min(0.96, 0.84 + base_margin / 2.0)
                reason = "morphosyntactic margin"
            elif has_context and (
                best.grammar_score - ranked[1].grammar_score >= 0.35
                and best.distance <= ranked[1].distance + 0.25
            ):
                confidence = 0.88
                reason = "strong grammatical dominance"
            elif has_context and (
                ranked[1].distance - best.distance >= 0.45
                and best.grammar_score >= ranked[1].grammar_score - 0.10
            ):
                confidence = 0.87
                reason = "weighted orthographic dominance"
            elif has_context and self._noisy_channel_dominates(raw, best, ranked[1]):
                confidence = 0.88
                reason = "contextual noisy-channel dominance"
            else:
                close = tuple(
                    item
                    for item in ranked[:8]
                    if best.base_score - item.base_score <= 0.20
                )
                semantic_scores: dict[str, float] = {}
                rerank_attempted = False
                rerank_error: str | None = None
                observed_semantic_margin: float | None = None
                observed_combined_margin: float | None = None
                llm_attempted = False
                llm_error: str | None = None
                llm_unresolved = False

                if has_context and self.semantic_reranker is not None and len(close) >= 2:
                    rerank_attempted = True
                    context = self._context_text(token, tokens, graph)
                    rank_embedding = getattr(
                        self.semantic_reranker, "rank_embedding", None
                    )
                    rank = (
                        rank_embedding
                        if callable(rank_embedding)
                        else self.semantic_reranker.rank
                    )
                    try:
                        semantic_scores = rank(
                            context,
                            tuple(item.text for item in close),
                        )
                    except Exception as exc:
                        semantic_scores = {}
                        detail = " ".join(str(exc).split())
                        rerank_error = f"{type(exc).__name__}: {detail}"[:240]

                embedding_was_complete = bool(
                    semantic_scores
                    and all(item.text in semantic_scores for item in close)
                )
                if embedding_was_complete:
                    sem_sorted = sorted(
                        close,
                        key=lambda item: (
                            -(item.base_score + 0.35 * semantic_scores[item.text]),
                            item.distance,
                            item.text,
                        ),
                    )
                    semantic_best = sem_sorted[0]
                    semantic_margin = (
                        semantic_best.base_score
                        + 0.35 * semantic_scores[semantic_best.text]
                        - sem_sorted[1].base_score
                        - 0.35 * semantic_scores[sem_sorted[1].text]
                    )
                    raw_semantic_margin = (
                        semantic_scores[semantic_best.text]
                        - semantic_scores[sem_sorted[1].text]
                    )
                    observed_combined_margin = semantic_margin
                    observed_semantic_margin = raw_semantic_margin

                    # Production lexical recovery must consider that an OOV may be
                    # intentional language (slang, jargon, a neologism, borrowing,
                    # etc.), not merely a misspelling of one dictionary entry.  The
                    # source-aware bounded probe sees the exact source token and the
                    # already narrowed correction shortlist.  It may preserve only
                    # that exact source form; it still cannot invent a replacement.
                    source_chooser = getattr(
                        self.semantic_reranker, "choose_source", None
                    )
                    if callable(source_chooser):
                        llm_attempted = True
                        try:
                            chosen = source_chooser(
                                context,
                                raw,
                                tuple(item.text for item in close),
                            )
                        except Exception as exc:
                            chosen = None
                            detail = " ".join(str(exc).split())
                            llm_error = f"{type(exc).__name__}: {detail}"[:240]
                        if chosen == raw:
                            preserve_source = True
                            reason = (
                                "bounded lexical LLM preserved exact source OOV "
                                "after deterministic+embedding ambiguity"
                            )
                        elif chosen is not None:
                            by_text = {item.text: item for item in close}
                            selected_candidate = by_text.get(str(chosen))
                            if selected_candidate is not None:
                                selected = selected_candidate
                                confidence = 0.90
                                reason = (
                                    "bounded lexical LLM correction after "
                                    "deterministic+embedding ambiguity"
                                )
                            else:
                                llm_unresolved = True
                        elif llm_error is None:
                            llm_unresolved = True
                    elif semantic_margin >= 0.10 and raw_semantic_margin >= 0.05:
                        selected = semantic_best
                        confidence = min(0.94, 0.82 + semantic_margin / 2.0)
                        reason = "local embedding rerank after deterministic narrowing"
                    else:
                        # Compatibility path for older/custom rerankers that expose
                        # only correction selection and cannot preserve SOURCE.
                        chooser = getattr(self.semantic_reranker, "choose", None)
                        if callable(chooser):
                            llm_attempted = True
                            try:
                                chosen = chooser(
                                    context,
                                    tuple(item.text for item in close),
                                )
                            except Exception as exc:
                                chosen = None
                                detail = " ".join(str(exc).split())
                                llm_error = f"{type(exc).__name__}: {detail}"[:240]
                            if chosen is not None:
                                by_text = {item.text: item for item in close}
                                selected_candidate = by_text.get(str(chosen))
                                if selected_candidate is not None:
                                    selected = selected_candidate
                                    confidence = 0.90
                                    reason = (
                                        "bounded lexical LLM tie-break after "
                                        "deterministic+embedding ambiguity"
                                    )
                                else:
                                    llm_unresolved = True
                            elif llm_error is None:
                                llm_unresolved = True

            if preserve_source:
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        raw,
                        LexicalRecoveryStatus.UNKNOWN_TOKEN,
                        alternatives=display,
                        confidence=0.90,
                        reason=reason,
                    )
                )
            elif confidence > 0.0:
                normalized = self._restore_case(raw, selected.text)
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        normalized,
                        LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE,
                        alternatives=display,
                        confidence=confidence,
                        reason=reason,
                    )
                )
            else:
                if rerank_error is not None:
                    ambiguity_reason = (
                        f"semantic reranker unavailable ({rerank_error})"
                    )
                elif rerank_attempted and not semantic_scores:
                    ambiguity_reason = (
                        "semantic reranker returned no complete scores"
                    )
                elif llm_error is not None:
                    ambiguity_reason = (
                        "embedding margin below safe threshold; bounded lexical "
                        f"LLM unavailable ({llm_error})"
                    )
                elif llm_attempted and llm_unresolved:
                    ambiguity_reason = (
                        "embedding margin below safe threshold; bounded lexical "
                        "LLM returned UNKNOWN/malformed choice"
                    )
                elif (
                    observed_combined_margin is not None
                    and observed_semantic_margin is not None
                ):
                    ambiguity_reason = (
                        "embedding margin below safe threshold "
                        f"(combined={observed_combined_margin:.3f}, "
                        f"semantic={observed_semantic_margin:.3f}); "
                        "no bounded lexical LLM decision"
                    )
                elif self.semantic_reranker is None:
                    ambiguity_reason = (
                        "no safe deterministic margin; semantic reranker disabled"
                    )
                else:
                    ambiguity_reason = (
                        "no safe deterministic or embedding margin"
                    )
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        None,
                        LexicalRecoveryStatus.AMBIGUOUS,
                        alternatives=display,
                        confidence=0.0,
                        reason=ambiguity_reason,
                    )
                )
        return tuple(decisions)


def __getattr__(name: str) -> Any:
    return getattr(_core, name)
