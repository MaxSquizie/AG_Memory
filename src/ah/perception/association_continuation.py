from __future__ import annotations

from ah.agent.interaction_context import InteractionContext

from .adaptive_parser import AdaptiveParseError, AdaptiveSettings
from .contracts import PerceptionResult, PredicateCandidate, QueryCandidate, QueryMode
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import PerceptionParseError
from .semantic_predicates import (
    SemanticPredicateAdaptiveParser,
    SemanticPredicateLLMPerceptionService,
)


class AssociationContinuationQueryCandidate(QueryCandidate):
    """Typed discourse query that reuses the active association endpoints."""


class AssociationContinuationLLMPerceptionService(SemanticPredicateLLMPerceptionService):
    """Recognize an elliptical request for another association result.

    The semantic probe is enabled only while InteractionContext owns an active
    association session. It never sees canonical endpoint UIDs and only decides the
    discourse operation CONTINUE/ORDINARY/UNCLEAR. Endpoint reuse and exclusion of
    previously returned results remain deterministic GoalCompiler/runtime work.
    """

    def _association_continuation_decision(self, text: str) -> str:
        semantic_reranker = (
            EmbeddingSemanticReranker(self.backend)  # type: ignore[arg-type]
            if self.settings.embedding_model.strip()
            and callable(getattr(self.backend, "embed_texts", None))
            else None
        )
        parser = SemanticPredicateAdaptiveParser(
            self.backend,
            AdaptiveSettings(
                prompt_dir=self.settings.probe_prompt_dir,
                generation=self.settings.generation,
                retry_attempts=self.settings.probe_retry_attempts,
                max_actants_per_act=self.settings.max_actants_per_act,
                predicate_symbol_language=self.settings.predicate_symbol_language,
                morphology_backend=self.settings.morphology_backend,
                verify_predicate_symbol=(self.settings.protocol == "adaptive_v3"),
            ),
            semantic_reranker=semantic_reranker,
        )
        prompt = (
            f"CURRENT UTTERANCE:\n{text}\n"
            "DIALOGUE STATE:\n"
            "A binary association/commonality search is active and at least one result "
            "may already have been returned. Decide only whether this utterance asks "
            "for another distinct result for that same comparison."
        )
        try:
            choice, _ = parser._deep_semantic_choice_probe(
                "association_continuation",
                prompt,
                ("CONTINUE", "ORDINARY", "UNCLEAR"),
            )
        except AdaptiveParseError as exc:
            raise PerceptionParseError(str(exc)) from exc
        return choice or "UNCLEAR"

    @staticmethod
    def _continuation_result(text: str) -> PerceptionResult:
        query = AssociationContinuationQueryCandidate(
            predicate=PredicateCandidate(
                surface="быть",
                normalized_hint="быть",
                sense_hint="ASSOCIATION_CONTINUATION",
            ),
            actants=(),
            query_mode=QueryMode.EXISTS,
            local_id="Q_ASSOC_CONTINUE",
        )
        return PerceptionResult(
            source_text=text,
            queries=(query,),
            diagnostics=("ASSOCIATION_CONTINUATION",),
        )

    def parse(self, text: str, interaction_context: InteractionContext) -> PerceptionResult:
        if (
            interaction_context.association_session is not None
            and self.settings.protocol in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}
        ):
            decision = self._association_continuation_decision(text)
            if decision == "CONTINUE":
                result = self._continuation_result(text)
                self._record_diagnostic(text, [], result)
                return result
            if decision == "ORDINARY":
                # The association session is dialogue state, not permanent memory.
                # A real topic change closes it; a new explicit association query
                # will deterministically open a fresh session during GoalCompiler.
                interaction_context.association_session = None
            # UNCLEAR is fail-closed with respect to the optional continuation
            # overlay: preserve ordinary perception without destroying the session.
        return super().parse(text, interaction_context)
