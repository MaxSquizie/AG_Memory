from __future__ import annotations

"""Final source-semantic invariants for the production perception path.

The adaptive parser performs several deterministic structural passes after initial
actant extraction (ellipsis/coreference/logical/modal/event normalization).  Source
material whose semantic class is already deterministic must survive those passes.
This module enforces that contract at the public Perception boundary rather than
letting a later transformation silently erase an explicit TIME filler.

This is not a lexical repair layer: temporal candidates are accepted only by the
canonical ``TemporalNormalizer`` over exact source spans.  When source scope is not
unique, the parser fails closed instead of guessing which event receives the time.
"""

from dataclasses import replace

from ah.model import ActantRole
from ah.temporal import TemporalAnchorContext, TemporalNormalizer

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .contracts import AssertionCandidate, PerceptionResult
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)
from .runtime_semantics import (
    RuntimeSemanticAdaptiveParser as _RuntimeSemanticAdaptiveParser,
    RuntimeSemanticLLMPerceptionService as _RuntimeSemanticLLMPerceptionService,
)
from .temporal_mode_formalization import (
    TemporalModeFormalizationError,
    TemporalModeFormalizer,
)


class RuntimeSemanticAdaptiveParser(_RuntimeSemanticAdaptiveParser):
    """Production parser with a final deterministic source-time invariant.

    Initial source preconsumption remains the primary path.  This final boundary is
    intentionally independent from intermediate frame rewrites: if an explicit,
    deterministically recognized temporal source span belongs to one unambiguous
    final act, that act cannot leave Perception without a TIME role.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._final_temporal_normalizer = TemporalNormalizer()

    def _predicate_source_span(self, predicate):
        graph = self._candidate_graph
        evidence = predicate.evidence
        if (
            graph is None
            or evidence is None
            or evidence.start is None
            or evidence.end is None
        ):
            return None
        tokens = self._source_tokens_from_graph(graph)
        indices = [
            token.index
            for token in graph.tokens
            if evidence.start <= token.start and token.end <= evidence.end
        ]
        if not indices:
            return None
        return self._resolve_span_from_source(tokens, min(indices), max(indices))

    def _merge_temporal_spans(self, tokens, spans):
        if not spans:
            return None
        if len(spans) == 1:
            return spans[0]
        ordered = sorted(spans, key=lambda item: item.start_index)
        merged = self._resolve_span_from_source(
            tokens,
            ordered[0].start_index,
            ordered[-1].end_index,
        )
        candidate = self._final_temporal_normalizer.normalize(
            self._semantic_span(merged).text,
            TemporalAnchorContext(),
        )
        if candidate is not None:
            return merged
        raise AdaptiveParseError(
            "final source-time invariant found multiple independent temporal spans",
            tuple(self._traces),
        )

    def _final_temporal_span_for_act(self, text: str, act, *, act_count: int):
        graph = self._candidate_graph
        if graph is None:
            return None
        predicate_span = self._predicate_source_span(act.predicate)
        if predicate_span is None:
            return None
        tokens = self._source_tokens_from_graph(graph)
        candidates = list(
            self._temporal_candidate_spans(
                text,
                tokens,
                predicate_span,
                (),
            )
        )
        if not candidates:
            return None

        if act_count > 1:
            # For several semantic acts, never spread one temporal expression by
            # source proximity alone.  Keep only values inside this predicate's
            # deterministic argument window; shared/coordinated scope must already
            # have been established by the normal structural pipeline.
            lower, upper = self._predicate_argument_bounds(predicate_span, tokens)
            candidates = [
                span
                for span in candidates
                if lower <= span.start_index and span.end_index <= upper
            ]
            if not candidates:
                return None

        return self._merge_temporal_spans(tokens, candidates)

    @staticmethod
    def _single_time_actant(act):
        values = tuple(
            item for item in act.actants if item.role is ActantRole.TIME
        )
        if len(values) > 1:
            raise AdaptiveParseError("one predicate frame contains more than one TIME role")
        return values[0] if values else None

    def _attach_time_to_assertion_alternatives(self, assertion, time_actant):
        if not assertion.alternatives:
            return assertion
        alternatives = []
        changed = False
        for alternative in assertion.alternatives:
            existing = self._single_time_actant(alternative)
            if existing is None:
                alternative = replace(
                    alternative,
                    actants=alternative.actants + (time_actant,),
                )
                changed = True
            alternatives.append(alternative)
        return (
            replace(assertion, alternatives=tuple(alternatives))
            if changed
            else assertion
        )

    def _enforce_final_source_time(self, result: PerceptionResult) -> PerceptionResult:
        acts = (*result.assertions, *result.queries, *result.commands)
        if not acts:
            return result

        changed_assertion = False
        changed_any = False
        assertions = []
        queries = []
        commands = []

        for assertion in result.assertions:
            existing = self._single_time_actant(assertion)
            if existing is None:
                span = self._final_temporal_span_for_act(
                    result.source_text,
                    assertion,
                    act_count=len(acts),
                )
                if span is not None:
                    existing = self._make_actant(ActantRole.TIME, span)
                    assertion = replace(
                        assertion,
                        actants=assertion.actants + (existing,),
                    )
                    predicate_span = self._predicate_source_span(assertion.predicate)
                    self._trace_deterministic_actant(
                        result.source_text,
                        self._source_tokens_from_graph(self._candidate_graph),
                        predicate_span,
                        span,
                        ActantRole.TIME,
                    )
                    changed_assertion = True
                    changed_any = True
            if existing is not None:
                synchronized = self._attach_time_to_assertion_alternatives(
                    assertion, existing
                )
                if synchronized is not assertion:
                    assertion = synchronized
                    changed_assertion = True
                    changed_any = True
            assertions.append(assertion)

        for collection, output in (
            (result.queries, queries),
            (result.commands, commands),
        ):
            for act in collection:
                existing = self._single_time_actant(act)
                if existing is None:
                    span = self._final_temporal_span_for_act(
                        result.source_text,
                        act,
                        act_count=len(acts),
                    )
                    if span is not None:
                        time_actant = self._make_actant(ActantRole.TIME, span)
                        act = replace(act, actants=act.actants + (time_actant,))
                        predicate_span = self._predicate_source_span(act.predicate)
                        self._trace_deterministic_actant(
                            result.source_text,
                            self._source_tokens_from_graph(self._candidate_graph),
                            predicate_span,
                            span,
                            ActantRole.TIME,
                        )
                        changed_any = True
                output.append(act)

        if not changed_any:
            return result

        result = replace(
            result,
            assertions=tuple(assertions),
            queries=tuple(queries),
            commands=tuple(commands),
            diagnostics=(
                *result.diagnostics,
                "source-time-invariant: explicit deterministic TIME preserved",
            ),
        )

        # The base parser classifies temporal mode before this final boundary.  If
        # an intermediate transformation erased TIME, that assertion legitimately
        # had no observable temporal frame at the first pass.  Re-run the existing
        # idempotent typed classifier only for the now-observable final assertion;
        # already classified assertions return unchanged.
        if changed_assertion:
            try:
                result = TemporalModeFormalizer(self.morphology).formalize(
                    result,
                    resolver=self._resolve_temporal_mode_candidate,
                )
            except TemporalModeFormalizationError as exc:
                raise AdaptiveParseError(str(exc), tuple(self._traces)) from exc
        return result

    def parse(self, text: str, *, structural_resolution: str | None = None):
        parsed = super().parse(text, structural_resolution=structural_resolution)
        perception = self._enforce_final_source_time(parsed.perception)
        if perception is parsed.perception:
            return parsed
        return replace(parsed, perception=perception, traces=tuple(self._traces))


class RuntimeSemanticLLMPerceptionService(_RuntimeSemanticLLMPerceptionService):
    """Public runtime service using the source-invariant parser."""

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
