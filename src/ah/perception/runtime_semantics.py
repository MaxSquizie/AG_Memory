from __future__ import annotations

from dataclasses import replace
import re

from ah.model import ActantRole
from ah.temporal import TemporalAnchorContext, TemporalNormalizer

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .contracts import EvidenceSpan
from .generalized_naming import (
    GeneralizedNamingAdaptiveParser,
    GeneralizedNamingLLMPerceptionService,
)
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)
from .query_semantics import EventSetQueryCandidate


class RuntimeSemanticAdaptiveParser(GeneralizedNamingAdaptiveParser):
    """Production source-operator boundary for ordinary runtime parsing.

    Two source classes must be consumed before generic actant-role probing:

    * expressions already recognized by the canonical ``TemporalNormalizer`` are
      explicit TIME material.  They are staged as TIME even when the local model
      would otherwise stop actant enumeration or misclassify an adverb;
    * pure adverb/particle spans receive one bounded *scope* decision before role
      classification.  Event-internal adverbs remain available to ordinary role
      semantics, transition operators are reserved for transition normalization,
      and utterance/query operators are consumed as discourse material.

    This layer contains no surface-word dictionary.  Candidate spans and POS come
    from the existing source graph, temporal recognition comes from the canonical
    deterministic normalizer, and the only model decision is over the fixed
    EVENT_RELATION / EVENT_TRANSITION / DISCOURSE_OPERATOR / UNCLEAR protocol.
    """

    _ADVERBIAL_SCOPE_CHOICES = (
        "EVENT_RELATION",
        "EVENT_TRANSITION",
        "DISCOURSE_OPERATOR",
        "UNCLEAR",
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._runtime_temporal_normalizer = TemporalNormalizer()
        self._runtime_adverbial_scope: dict[tuple[int, int], str] = {}
        self._runtime_discourse_operator_spans: list[EvidenceSpan] = []

    @staticmethod
    def _span_key(span) -> tuple[int, int]:
        return span.start_index, span.end_index

    @staticmethod
    def _overlaps_any(span, others) -> bool:
        return any(span.overlaps(other) for other in others)

    def _pure_adverbial_span(self, span, tokens) -> bool:
        lexical = [
            tokens[index - 1]
            for index in range(span.start_index, span.end_index + 1)
            if re.search(r"\w", tokens[index - 1].text, flags=re.UNICODE)
        ]
        if not lexical:
            return False
        for token in lexical:
            analyses = tuple(self._material_morph_analyses(token))
            poses = {item.pos for item in analyses if item.pos is not None}
            if not poses or not poses.issubset({"ADVB", "PRCL"}):
                return False
        return True

    def _temporal_source_span(
        self,
        text,
        tokens,
        predicate_span,
        requested_spans,
        *,
        requested_roles,
        role_whitelist,
    ):
        if ActantRole.TIME in requested_roles:
            return None
        if role_whitelist is not None and ActantRole.TIME not in role_whitelist:
            return None

        candidates = self._candidate_phrase_spans(
            text,
            tokens,
            predicate_span,
            [],
            requested_spans=requested_spans,
        )
        temporal = []
        for span in candidates:
            semantic = self._semantic_span(span)
            if self._runtime_temporal_normalizer.normalize(
                semantic.text,
                TemporalAnchorContext(),
            ) is not None:
                temporal.append(span)

        if not temporal:
            return None
        if len(temporal) == 1:
            return temporal[0]

        # Several adjacent source fragments may jointly denote one temporal value
        # (for example a relative day plus a clock point).  Merge only when the
        # same deterministic normalizer recognizes the complete source interval.
        ordered = sorted(temporal, key=lambda item: item.start_index)
        merged = self._resolve_span_from_source(
            tokens,
            ordered[0].start_index,
            ordered[-1].end_index,
        )
        if (
            predicate_span is None or not merged.overlaps(predicate_span)
        ) and not self._overlaps_any(merged, requested_spans):
            semantic = self._semantic_span(merged)
            if self._runtime_temporal_normalizer.normalize(
                semantic.text,
                TemporalAnchorContext(),
            ) is not None:
                return merged

        # One canonical frame has one TIME slot.  Distinct temporal source values
        # require an explicit richer representation; never silently drop one.
        raise AdaptiveParseError(
            "multiple independent temporal source spans require explicit temporal composition",
            tuple(self._traces),
        )

    def _adverbial_scope_decision(self, text, predicate, span) -> str:
        key = self._span_key(span)
        cached = self._runtime_adverbial_scope.get(key)
        if cached is not None:
            return cached
        prompt = (
            f"TEXT:\n{text}\n"
            f"PREDICATE:\n{predicate.surface}\n"
            f"TARGET:\n{self._semantic_span(span).text}\n"
            "SCOPE MEANINGS:\n"
            "EVENT_RELATION: TARGET directly describes the predicate occurrence as "
            "a circumstance/filler such as manner, degree, place, cause, purpose, etc.\n"
            "EVENT_TRANSITION: TARGET explicitly changes the phase/recurrence of the "
            "same predicate occurrence: beginning, stopping, continuing, occurring "
            "again, or no longer holding.\n"
            "DISCOURSE_OPERATOR: TARGET modifies the utterance/question/focus or the "
            "set of requested/available answers, rather than the predicate event. "
            "Requesting an additional or alternative answer belongs here.\n"
            "UNCLEAR: the source does not determine the scope safely.\n"
            "CHOICES:\n"
            + "\n".join(self._ADVERBIAL_SCOPE_CHOICES)
        )
        decision, _ = self._deep_semantic_choice_probe(
            "adverbial_scope",
            prompt,
            self._ADVERBIAL_SCOPE_CHOICES,
        )
        assert decision is not None
        if decision == "UNCLEAR":
            raise AdaptiveParseError(
                "adverbial source scope is unresolved",
                tuple(self._traces),
            )
        self._runtime_adverbial_scope[key] = decision
        return decision

    def _preconsume_source_semantics(
        self,
        text,
        tokens,
        predicate_span,
        predicate,
        requested_spans,
        temporal_span,
    ) -> set[int]:
        blocked: set[int] = set()
        candidates = self._candidate_phrase_spans(
            text,
            tokens,
            predicate_span,
            [],
            requested_spans=requested_spans,
        )
        for span in candidates:
            if temporal_span is not None and span.overlaps(temporal_span):
                continue
            if self._overlaps_any(span, requested_spans):
                continue
            if not self._pure_adverbial_span(span, tokens):
                continue
            decision = self._adverbial_scope_decision(text, predicate, span)
            if decision == "EVENT_RELATION":
                continue

            indices = {
                index
                for index in range(span.start_index, span.end_index + 1)
                if re.search(r"\w", tokens[index - 1].text, flags=re.UNICODE)
            }
            if not indices:
                continue
            blocked.update(indices)
            if decision == "EVENT_TRANSITION":
                # The separate transition-normalization pass owns START/STOP/etc.
                # This scope decision merely prevents the operator source from also
                # becoming an ordinary actant.
                self._transition_cue_token_indices.update(indices)
            elif decision == "DISCOURSE_OPERATOR":
                evidence = span.evidence
                if evidence not in self._runtime_discourse_operator_spans:
                    self._runtime_discourse_operator_spans.append(evidence)
        return blocked

    def _role_cue_probe(self, *args, **kwargs):
        # Once the dedicated scope probe has established EVENT_RELATION, the same
        # span must not be allowed to reverse that decision by selecting
        # TRANSITION_OPERATOR inside the generic role inventory.
        span = kwargs.get("span")
        if span is not None:
            decision = self._runtime_adverbial_scope.get(self._span_key(span))
            if decision == "EVENT_RELATION":
                kwargs["allow_transition_operator"] = False
        return super()._role_cue_probe(*args, **kwargs)

    def _extract_actants(
        self,
        text,
        tokens,
        predicate_span,
        predicate,
        *,
        act_type,
        requested_roles,
        requested_spans,
        role_whitelist=None,
    ):
        temporal_span = self._temporal_source_span(
            text,
            tokens,
            predicate_span,
            requested_spans,
            requested_roles=requested_roles,
            role_whitelist=role_whitelist,
        )
        blocked = self._preconsume_source_semantics(
            text,
            tokens,
            predicate_span,
            predicate,
            requested_spans,
            temporal_span,
        )
        if temporal_span is not None:
            blocked.update(
                range(temporal_span.start_index, temporal_span.end_index + 1)
            )

        previous_blocked = set(
            getattr(self, "_runtime_blocked_token_indices", set())
        )
        self._runtime_blocked_token_indices = previous_blocked | blocked
        try:
            actants, spans = super()._extract_actants(
                text,
                tokens,
                predicate_span,
                predicate,
                act_type=act_type,
                requested_roles=requested_roles,
                requested_spans=requested_spans,
                role_whitelist=role_whitelist,
            )
        finally:
            self._runtime_blocked_token_indices = previous_blocked

        if temporal_span is None:
            return actants, spans
        if any(item.role is ActantRole.TIME for item in actants):
            raise AdaptiveParseError(
                "TIME source was consumed twice by runtime perception",
                tuple(self._traces),
            )
        temporal_actant = self._make_actant(ActantRole.TIME, temporal_span)
        self._trace_deterministic_actant(
            text,
            tokens,
            predicate_span,
            temporal_span,
            ActantRole.TIME,
        )
        return actants + (temporal_actant,), spans + (temporal_span,)

    def parse(self, text: str, *, structural_resolution: str | None = None):
        self._runtime_adverbial_scope = {}
        self._runtime_discourse_operator_spans = []
        parsed = super().parse(text, structural_resolution=structural_resolution)
        if not self._runtime_discourse_operator_spans:
            return parsed

        queries = []
        changed = False
        for query in parsed.perception.queries:
            if not isinstance(query, EventSetQueryCandidate):
                queries.append(query)
                continue
            evidence = list(query.query_operator_evidence)
            for item in self._runtime_discourse_operator_spans:
                if item not in evidence:
                    evidence.append(item)
            if tuple(evidence) != query.query_operator_evidence:
                query = replace(query, query_operator_evidence=tuple(evidence))
                changed = True
            queries.append(query)
        if not changed:
            return parsed
        return replace(
            parsed,
            perception=replace(parsed.perception, queries=tuple(queries)),
        )


class RuntimeSemanticLLMPerceptionService(GeneralizedNamingLLMPerceptionService):
    """Public production perception service with source-operator preconsumption."""

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
        parser = RuntimeSemanticAdaptiveParser(
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
