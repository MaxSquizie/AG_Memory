from __future__ import annotations

from dataclasses import replace

from ah.model import ActantRole

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .identity_query import IdentityQueryAdaptiveParser, IdentityQueryLLMPerceptionService
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)


class SemanticPredicateAdaptiveParser(IdentityQueryAdaptiveParser):
    """Production semantic normalization after source-structural parsing.

    This layer contains no phrase inventory.  It does two bounded jobs:

    * for an implicit nominal *question*, provide provisional grammatical roles so
      the base parser can finish before the existing identity-query rewrite decides
      whether the construction is identity or ordinary predication;
    * distinguish a possession relation from an unrelated binary predicate and give
      all possession paraphrases one canonical predicate lemma.  The LLM chooses
      only POSSESSION / OTHER_RELATION / UNCLEAR over already source-grounded roles.

    Canonical AH UIDs are unavailable here.
    """

    _POSSESSION_CANONICAL_PREDICATE = "иметь"

    def _deterministic_role_candidates(
        self,
        tokens,
        predicate_span,
        predicate,
        span,
    ):
        # ``Кто Илья?`` contains no written copula.  The generic role probe sees two
        # bare nominals and can legitimately return UNCLEAR before the higher-level
        # identity layer gets a chance to inspect the complete shell.  For an
        # IMPLICIT copula only, morphology already tells us which source token is
        # interrogative.  SUBJECT/STATE are provisional copular roles, not the final
        # identity interpretation; the bounded identity decision consumes them when
        # appropriate.  Assertions such as ``Я Илья`` are deliberately untouched.
        if (predicate.sense_hint or "").upper() == "IMPLICIT":
            graph = self._candidate_graph
            clause = None if graph is None else graph.clause_for_token(span.start_index)
            start = 1 if clause is None else clause.span.start_index
            end = len(tokens) if clause is None else clause.span.end_index
            clause_has_question = any(
                start <= token.index <= end and self._question_form(token)
                for token in tokens
            )
            if clause_has_question:
                span_has_question = any(
                    span.start_index <= token.index <= span.end_index
                    and self._question_form(token)
                    for token in tokens
                )
                return (
                    (ActantRole.SUBJECT,)
                    if span_has_question
                    else (ActantRole.STATE,)
                )
        return super()._deterministic_role_candidates(
            tokens,
            predicate_span,
            predicate,
            span,
        )

    @staticmethod
    def _binary_entity_relation(item) -> bool:
        roles = {actant.role for actant in item.actants}
        if ActantRole.SUBJECT not in roles or ActantRole.OBJECT not in roles:
            return False
        return not any(
            actant.candidate_ref is not None
            or actant.proposition is not None
            or actant.composition is not None
            for actant in item.actants
        )

    def _possession_kind(self, source_text: str, item) -> str:
        role_rows = "\n".join(
            f"{actant.role.value}={actant.lookup_text or '[structured]'}"
            for actant in item.actants
        )
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE:\n{item.predicate.surface}\n"
            f"SEMANTIC ROLES:\n{role_rows}\n"
            "Decision criterion:\n"
            "Does this proposition express POSSESSION/availability where the "
            "already identified SUBJECT is the possessor/holder and OBJECT is the "
            "thing possessed/available to that subject? This includes existential "
            "possessive wording, but not an action merely performed on an object, "
            "location near an object, or another binary relation.\n"
            "Candidate labels:\nPOSSESSION\nOTHER_RELATION\nUNCLEAR"
        )
        decision, _ = self._deep_semantic_choice_probe(
            "predicate_semantics",
            prompt,
            ("POSSESSION", "OTHER_RELATION", "UNCLEAR"),
        )
        assert decision is not None
        return decision

    def _normalize_predicate_semantics(self, source_text: str, item):
        if not self._binary_entity_relation(item):
            return item, False
        decision = self._possession_kind(source_text, item)
        if decision == "OTHER_RELATION":
            return item, False
        if decision == "UNCLEAR":
            raise AdaptiveParseError(
                "binary predicate semantics is ambiguous between possession and another relation",
                tuple(self._traces),
            )

        predicate = item.predicate
        canonical = self._POSSESSION_CANONICAL_PREDICATE
        same_lookup = predicate.lookup_form.casefold().replace("ё", "е") == canonical
        rewritten_predicate = replace(
            predicate,
            normalized_hint=canonical,
            sense_hint="POSSESSION",
            # A selection made for a lexically different predicate cannot survive
            # semantic canonicalization. Integration will deterministically resolve
            # the canonical predicate/template again. If it was already canonical,
            # preserve the existing selection.
            template_selection=(predicate.template_selection if same_lookup else None),
        )
        if rewritten_predicate == predicate:
            return item, False
        return replace(item, predicate=rewritten_predicate), True

    def parse(self, text: str, *, structural_resolution: str | None = None):
        parsed = super().parse(text, structural_resolution=structural_resolution)
        assertions = []
        queries = []
        changed = False

        for assertion in parsed.perception.assertions:
            rewritten, local_changed = self._normalize_predicate_semantics(text, assertion)
            assertions.append(rewritten)
            changed = changed or local_changed
        for query in parsed.perception.queries:
            rewritten, local_changed = self._normalize_predicate_semantics(text, query)
            queries.append(rewritten)
            changed = changed or local_changed

        if not changed:
            return parsed
        return replace(
            parsed,
            perception=replace(
                parsed.perception,
                assertions=tuple(assertions),
                queries=tuple(queries),
            ),
        )


class SemanticPredicateLLMPerceptionService(IdentityQueryLLMPerceptionService):
    """Runtime service that instantiates the semantic-predicate parser above."""

    def _parse_structural_adaptive(
        self,
        text: str,
        *,
        structural_resolution: str | None = None,
    ):
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
        try:
            parsed = parser.parse(
                text,
                structural_resolution=structural_resolution,
            )
        except AdaptiveStructuralClarificationRequired as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role=trace.stage,
                    raw_text=trace.raw_text,
                    error=trace.error,
                    prompt=trace.prompt,
                    normalized_answer=trace.normalized_answer,
                    retry_index=trace.retry_index,
                )
                for trace in exc.traces
            ]
            self._record_diagnostic(text, attempts, None, str(exc))
            raise PerceptionClarificationRequired(exc.spec) from exc
        except AdaptiveParseError as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role=trace.stage,
                    raw_text=trace.raw_text,
                    error=trace.error,
                    prompt=trace.prompt,
                    normalized_answer=trace.normalized_answer,
                    retry_index=trace.retry_index,
                )
                for trace in exc.traces
            ]
            final_error = str(exc)
            self._record_diagnostic(text, attempts, None, final_error)
            raise PerceptionParseError(final_error) from exc

        attempts = [
            PerceptionAttemptDiagnostic(
                role=trace.stage,
                raw_text=trace.raw_text,
                error=trace.error,
                prompt=trace.prompt,
                normalized_answer=trace.normalized_answer,
                retry_index=trace.retry_index,
            )
            for trace in parsed.traces
        ]
        self._record_diagnostic(text, attempts, parsed.perception)
        return parsed.perception
