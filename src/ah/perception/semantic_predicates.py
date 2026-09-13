from __future__ import annotations

from dataclasses import replace

from ah.model import ActantRole

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .contracts import (
    QueryMode,
    QueryQuantifierOperator,
    QuantifiedQueryBinding,
    QuantifiedQuerySpec,
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

    This layer contains no phrase inventory.  It does three bounded jobs:

    * for an implicit nominal *question*, provide provisional grammatical roles so
      the base parser can finish before the existing identity-query rewrite decides
      whether the construction is identity or ordinary predication;
    * distinguish a possession relation from an unrelated binary predicate and give
      all possession paraphrases one canonical predicate lemma;
    * when a possession question contains a bare nominal SUBJECT, distinguish a
      generic class-level question from a question about one specific entity.  A
      generic reading becomes the existing typed FORALL query contract instead of
      fabricating an entity named after the class.

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

    def _generic_subject_kind(self, source_text: str, query, subject) -> str:
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE SEMANTICS:\n{query.predicate.sense_hint or query.predicate.surface}\n"
            f"SUBJECT CANDIDATE:\n{subject.lookup_text or subject.mention or ''}\n"
            "Decision criterion:\nDoes SUBJECT denote a generic class member for which "
            "the question asks a general rule/property of the class, or one specific "
            "entity/referent?\nCandidate labels:\nGENERIC_CLASS\nSPECIFIC_ENTITY\nUNCLEAR"
        )
        decision, _ = self._deep_semantic_choice_probe(
            "generic_subject",
            prompt,
            ("GENERIC_CLASS", "SPECIFIC_ENTITY", "UNCLEAR"),
        )
        assert decision is not None
        return decision

    def _formalize_generic_possession_query(self, source_text: str, query):
        if (
            query.query_mode is not QueryMode.EXISTS
            or query.quantified is not None
            or (query.predicate.sense_hint or "").upper() != "POSSESSION"
        ):
            return query, False
        subjects = tuple(
            actant
            for actant in query.actants
            if actant.role is ActantRole.SUBJECT
            and actant.entity_ref is None
            and actant.candidate_ref is None
            and actant.composition is None
            and actant.proposition is None
            and actant.quantifier is None
        )
        if len(subjects) != 1:
            return query, False
        subject = subjects[0]
        decision = self._generic_subject_kind(source_text, query, subject)
        if decision == "SPECIFIC_ENTITY":
            return query, False
        if decision == "UNCLEAR":
            raise AdaptiveParseError(
                "possession question subject is ambiguous between generic class and specific entity",
                tuple(self._traces),
            )
        if query.local_id is None:
            raise AdaptiveParseError(
                "generic quantified query requires a parser-local query id",
                tuple(self._traces),
            )
        restriction = (subject.normalized_hint or subject.mention or "").strip()
        if not restriction:
            raise AdaptiveParseError(
                "generic quantified query has no nominal restriction",
                tuple(self._traces),
            )
        entity_ref = f"{query.local_id}:generic_subject"
        rebound = replace(subject, entity_ref=entity_ref)
        actants = tuple(rebound if item is subject else item for item in query.actants)
        spec = QuantifiedQuerySpec(
            bindings=(
                QuantifiedQueryBinding(
                    entity_ref=entity_ref,
                    variable_id=0,
                    operator=QueryQuantifierOperator.FORALL,
                    restriction_lemma=restriction,
                ),
            ),
            body_negated=False,
        )
        return replace(query, actants=actants, quantified=spec), True

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
            rewritten, generic_changed = self._formalize_generic_possession_query(
                text, rewritten
            )
            queries.append(rewritten)
            changed = changed or local_changed or generic_changed

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
