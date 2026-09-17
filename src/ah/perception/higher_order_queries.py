from __future__ import annotations

from ah.model import ActantRole

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .coordination_normalization import CoordinationAwareLLMPerceptionService
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)
from .semantic_predicates import SemanticPredicateAdaptiveParser


class HigherOrderQueryAdaptiveParser(SemanticPredicateAdaptiveParser):
    """Late semantic commitment for a WH span that is not an ordinary role gap.

    The structural parser normally commits every explicit interrogative span to one
    canonical actant role before higher semantic operators are allowed to inspect the
    query.  That ordering is too strong: a question can ask for a relation/schema
    *between already expressed participants* rather than for a missing participant of
    the surface predicate.  In that case role classification can correctly have no
    answer, yet the whole utterance is still well formed.

    We keep the fast deterministic path unchanged.  Only after ordinary requested-role
    resolution has failed do we run one bounded semantic decision over the complete
    local query.  The model does not invent a parse or a role; it can only decide
    whether the unresolved WH material denotes an ordinary predicate argument or a
    higher-order relation description.  A relation description is staged as STATE,
    which is the existing runtime contract for a predicated/relation description and
    is later consumed by association semantics.  Any other outcome preserves the
    original fail-closed error.

    This layer intentionally contains no inventory of question phrases, prepositions,
    predicates, or lexical exceptions.
    """

    _PARTICIPANT_ROLES = frozenset(
        {
            ActantRole.SUBJECT,
            ActantRole.OBJECT,
            ActantRole.RECIPIENT,
            ActantRole.SOURCE,
            ActantRole.ABSENTEE,
            ActantRole.AUXILLIARY,
        }
    )

    def _requested_query_roles(self, *args, **kwargs):
        try:
            return super()._requested_query_roles(*args, **kwargs)
        except AdaptiveParseError as original:
            if "requested role unresolved" not in str(original):
                raise

            if len(args) < 3:
                raise
            text = args[0]
            tokens = args[1]
            predicate = args[2]
            predicate_span = args[3] if len(args) > 3 else kwargs.get("predicate_span")
            used_roles = set(kwargs.get("used_roles") or ())

            # A higher-order binary relation request must already have material to
            # relate.  This structural guard keeps ordinary single-gap WH questions
            # on the mature role-resolution path and avoids an extra model call.
            participant_count = len(used_roles & self._PARTICIPANT_ROLES)
            if participant_count < 2:
                raise

            spans = self._requested_query_spans(text, tokens, predicate_span)
            if len(spans) != 1:
                # Multiple unresolved holes need an explicit compositional contract;
                # do not collapse them into one relation request by guess.
                raise

            span = spans[0]
            role_rows = ", ".join(sorted(role.value for role in used_roles)) or "[none]"
            prompt = (
                f"TEXT:\n{text}\n"
                f"PARSED PREDICATE:\n{predicate.surface}\n"
                f"UNRESOLVED QUESTION MATERIAL:\n{span.text}\n"
                f"ALREADY FILLED SEMANTIC ROLES:\n{role_rows}\n"
                "Decision criterion:\n"
                "Does the unresolved question material ask for a missing semantic "
                "argument/circumstance of the parsed predicate, or does it ask for "
                "the relation/property/schema connecting participants that are "
                "already explicitly present in the utterance?"
            )
            decision, _ = self._deep_semantic_choice_probe(
                "query_gap_level",
                prompt,
                ("ARGUMENT_GAP", "RELATION_DESCRIPTION", "UNCLEAR"),
            )
            if decision != "RELATION_DESCRIPTION":
                raise original

            # STATE is a staging representation of the requested relation
            # description, not a claim that STATE is a filled world fact.  The
            # association semantic overlay removes it from endpoint selection.
            self._deterministic_trace(
                "query_gap_level_commitment",
                prompt,
                "RELATION_DESCRIPTION->STATE",
            )
            return (ActantRole.STATE,), spans


class HigherOrderQueryLLMPerceptionService(CoordinationAwareLLMPerceptionService):
    """Production perception service with coarse-to-fine query commitment."""

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
        parser = HigherOrderQueryAdaptiveParser(
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
