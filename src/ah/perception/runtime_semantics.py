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

    Source material whose semantic class is already established must be consumed
    before generic role probing.  Two classes are especially important here:

    * expressions recognized by the canonical ``TemporalNormalizer`` become TIME
      before a weak model can skip or relabel them;
    * adverb/particle spans receive one bounded scope decision before ordinary role
      classification, so transition and discourse operators cannot also become
      ordinary actants.

    Candidate spans and morphology remain deterministic/source-grounded.  The only
    new model decision is the fixed EVENT_RELATION / EVENT_TRANSITION /
    DISCOURSE_OPERATOR / UNCLEAR scope protocol.  There is no surface-word table.
    """

    _ADVERBIAL_SCOPE_CHOICES = (
        "EVENT_RELATION",
        "EVENT_TRANSITION",
        "DISCOURSE_OPERATOR",
        "UNCLEAR",
    )
    # Absolute temporal literals may be split into several source tokens by the
    # generic tokenizer (``12 . 09 . 2026``, ``2026 - 09 - 12``, datetimes and
    # bounded intervals).  Scan a finite source window before ordinary roles so
    # punctuation never turns pieces of one date into independent actants.  This
    # is a computational bound, not a vocabulary/template list; every candidate is
    # still accepted only by the canonical deterministic TemporalNormalizer.
    _MAX_TEMPORAL_SOURCE_TOKENS = 16

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._runtime_temporal_normalizer = TemporalNormalizer()
        self._runtime_adverbial_scope: dict[tuple[int, int], str] = {}
        self._runtime_discourse_operator_spans: list[EvidenceSpan] = []

    @staticmethod
    def _span_contains(container, value) -> bool:
        """Preserve both base parser span semantics and naming evidence semantics.

        ``GeneralizedNamingAdaptiveParser`` historically introduced a helper with
        the same private name as ``AdaptivePerceptionParser._span_contains`` but a
        different signature.  The production subclass is used by every live parse,
        so make that boundary explicitly polymorphic: parser ``_Span + token index``
        calls keep the base contract, while naming ``EvidenceSpan + token`` calls
        keep their source-offset contract.
        """
        if hasattr(container, "start_index") and hasattr(container, "end_index"):
            return (
                isinstance(value, int)
                and container.start_index <= value <= container.end_index
            )
        evidence = container
        token = value
        return (
            evidence is not None
            and getattr(evidence, "start", None) is not None
            and getattr(evidence, "end", None) is not None
            and hasattr(token, "start")
            and hasattr(token, "end")
            and evidence.start <= token.start
            and token.end <= evidence.end
        )

    @staticmethod
    def _span_key(span) -> tuple[int, int]:
        return span.start_index, span.end_index

    @staticmethod
    def _overlaps_any(span, others) -> bool:
        return any(span.overlaps(other) for other in others)

    def _runtime_explicit_nominal(self, token) -> bool:
        """Whether material morphology contains an actual NOUN/NPRO reading.

        Production pymorphy output is intentionally ambiguous.  A substantive such
        as ``животное`` may also expose an adjectival reading (``животный``).  The
        copular-state detector must give the substantive reading structural priority
        inside an NP instead of turning that NP into STATE merely because *one*
        analysis is adjectival.
        """
        return any(
            item.pos in {"NOUN", "NPRO"}
            for item in self._material_morph_analyses(token)
        )

    def _runtime_substantivized_adjective(self, token) -> bool:
        return any(
            item.pos == "ADJF" and "Subx" in item.grammemes
            for item in self._material_morph_analyses(token)
        )

    def _runtime_begins_nominal_phrase(self, token_index, tokens, clause_end) -> bool:
        """Detect an adjective/determiner that belongs to a local NP.

        This is morphology-only and vocabulary-free.  A material nominal reading on
        the token itself is already a head.  Otherwise an adjective/participle/number
        sequence is followed until the first material nominal (including a
        substantivized adjective) or until the modifier chain is broken.
        """
        token = tokens[token_index - 1]
        if self._runtime_explicit_nominal(token):
            return True

        cursor = token_index + 1
        while cursor <= clause_end:
            current = tokens[cursor - 1]
            if self._runtime_explicit_nominal(current) or self._runtime_substantivized_adjective(current):
                return True
            if not self._has_structural_morph(
                current, poses={"ADJF", "PRTF", "NUMR"}
            ):
                return False
            if self._has_structural_morph(current, poses={"NPRO"}):
                return False
            cursor += 1
        return False

    def _deterministic_copular_state_span(
        self,
        text,
        tokens,
        predicate_span,
        predicate,
        selected,
        requested_spans,
    ):
        """Production-safe copular STATE recovery under morphology ambiguity.

        The base parser deliberately admits all lexical analyses.  That is correct
        for semantic probing, but it is too permissive for the *structural* decision
        that separates ``[каждое животное] [живое]``.  Here material morphology is
        used with nominal-head precedence: an attributive determiner/NP cannot become
        STATE solely because one token also has an adjectival reading.
        """
        if not self._is_copular_lookup(predicate.lookup_form):
            return None
        clause_start, clause_end = self._clause_bounds(predicate_span, tokens)
        lower_bound = (
            predicate_span.end_index + 1
            if predicate_span is not None
            else clause_start
        )
        state_poses = {"ADJF", "ADJS", "PRTS", "PRTF", "PRED"}
        starts: list[int] = []
        for token in tokens:
            if token.index < lower_bound or token.index > clause_end:
                continue
            if any(self._span_contains(span, token.index) for span in requested_spans):
                continue
            if any(
                span.start_index <= token.index <= span.end_index
                for span in selected
            ):
                continue
            if not self._has_structural_morph(token, poses=state_poses):
                continue
            if self._runtime_begins_nominal_phrase(
                token.index, tokens, clause_end
            ):
                continue
            # Do not start on the second member of an adjective coordination.
            if (
                token.index >= 3
                and tokens[token.index - 2].text.casefold()
                in {"и", "или", "либо"}
                and self._has_structural_morph(
                    tokens[token.index - 3], poses=state_poses
                )
            ):
                continue
            starts.append(token.index)

        if len(starts) != 1:
            return None
        start = starts[0]
        if self._candidate_graph is not None:
            coord_matches = [
                item
                for item in self._candidate_graph.coordinations
                if item.span.start_index == start
                and item.span.end_index <= clause_end
            ]
            if len(coord_matches) == 1:
                item = coord_matches[0]
                return self._resolve_span(
                    text, tokens, item.span.start_index, item.span.end_index
                )

        end = start
        base_poses = {
            item.pos
            for item in self._material_morph_analyses(tokens[start - 1])
            if item.pos in state_poses
        }
        cursor = start + 1
        while cursor + 1 <= clause_end:
            coordinator = tokens[cursor - 1].text.casefold()
            if coordinator not in {"и", "или", "либо"}:
                break
            next_poses = {
                item.pos
                for item in self._material_morph_analyses(tokens[cursor])
                if item.pos in state_poses
            }
            if not (base_poses & next_poses):
                break
            end = cursor + 1
            cursor += 2
        return self._resolve_span(text, tokens, start, end)

    def _deterministic_role_candidates(
        self, tokens, predicate_span, predicate, span
    ):
        candidates = super()._deterministic_role_candidates(
            tokens, predicate_span, predicate, span
        )
        # The base structural narrowing historically used "contains any ADJF" for
        # copular STATE.  With real morphology this turns an ordinary NP such as
        # ``каждое животное`` into STATE because its determiner is ADJF (and the
        # noun itself can have an adjectival homograph).  STATE is admissible only
        # when the candidate is not a phrase with an explicit substantive head.
        if (
            candidates == (ActantRole.STATE,)
            and self._is_copular_lookup(predicate.lookup_form)
            and any(
                self._runtime_explicit_nominal(tokens[index - 1])
                for index in range(span.start_index, span.end_index + 1)
            )
        ):
            return ()
        return candidates

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
            if not analyses:
                return False
            if not any(item.pos in {"ADVB", "PRCL"} for item in analyses):
                return False
            # A materially plausible nominal/verbal reading means this is not a
            # pure operator/circumstance token and must stay in the ordinary parser.
            if any(
                item.pos in {
                    "NOUN", "NPRO", "VERB", "INFN", "GRND",
                    "ADJF", "ADJS", "PRTF", "PRTS", "NUMR",
                }
                for item in analyses
            ):
                return False
        return True

    def _temporal_candidate_spans(
        self,
        text,
        tokens,
        predicate_span,
        requested_spans,
    ):
        """Return deterministic temporal spans independently of role chunking.

        Generic tokenization intentionally preserves punctuation.  Consequently an
        absolute date can arrive as five tokens and a dot inside the date may even
        look like a sentence boundary to the linguistic graph.  Temporal identity
        must be established *before* those generic boundaries are allowed to drive
        actant parsing.  We therefore combine two source-grounded candidate sets:

        1. ordinary linguistic phrase spans;
        2. bounded contiguous source-token windows, validated only by the canonical
           ``TemporalNormalizer`` over the exact original source substring.

        No date spelling/form list is maintained here.  A window that the temporal
        normalizer does not recognize simply is not a temporal candidate.
        """
        candidates = list(
            self._candidate_phrase_spans(
                text,
                tokens,
                predicate_span,
                [],
                requested_spans=requested_spans,
            )
        )

        token_count = len(tokens)
        for start in range(1, token_count + 1):
            max_end = min(
                token_count,
                start + self._MAX_TEMPORAL_SOURCE_TOKENS - 1,
            )
            for end in range(start, max_end + 1):
                # A TIME value cannot consume the lexical predicate itself.  Once
                # a growing window reaches the predicate from its left, all wider
                # windows also overlap it and can be abandoned immediately.
                if predicate_span is not None and not (
                    end < predicate_span.start_index
                    or start > predicate_span.end_index
                ):
                    if start < predicate_span.start_index <= end:
                        break
                    continue

                span = self._resolve_span_from_source(tokens, start, end)
                if self._overlaps_any(span, requested_spans):
                    continue
                if not any(
                    re.search(r"\w", tokens[index - 1].text, flags=re.UNICODE)
                    for index in range(start, end + 1)
                ):
                    continue
                semantic = self._semantic_span(span)
                if self._runtime_temporal_normalizer.normalize(
                    semantic.text,
                    TemporalAnchorContext(),
                ) is not None:
                    candidates.append(span)

        recognized = {}
        for span in candidates:
            if self._overlaps_any(span, requested_spans):
                continue
            semantic = self._semantic_span(span)
            if self._runtime_temporal_normalizer.normalize(
                semantic.text,
                TemporalAnchorContext(),
            ) is None:
                continue
            recognized[self._span_key(span)] = span

        # Prefer a wider already-recognized phrase over its recognized singleton
        # fragments.  ``2026`` is itself a YEAR, but inside ``2026-09-12`` the full
        # DAY span is the stronger exact source representation.
        ordered = sorted(
            recognized.values(),
            key=lambda item: (
                -(item.end_index - item.start_index),
                item.start_index,
            ),
        )
        maximal = []
        for span in ordered:
            if any(
                other.start_index <= span.start_index
                and span.end_index <= other.end_index
                for other in maximal
            ):
                continue
            maximal.append(span)
        return tuple(sorted(maximal, key=lambda item: item.start_index))

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

        temporal = list(
            self._temporal_candidate_spans(
                text,
                tokens,
                predicate_span,
                requested_spans,
            )
        )
        if not temporal:
            return None
        if len(temporal) == 1:
            return temporal[0]

        # Several fragments may jointly denote one temporal value, e.g. a relative
        # day plus a clock point.  Merge only if the canonical normalizer recognizes
        # the complete source interval as one value.
        ordered = sorted(temporal, key=lambda item: item.start_index)
        merged = self._resolve_span_from_source(
            tokens,
            ordered[0].start_index,
            ordered[-1].end_index,
        )
        if (
            (predicate_span is None or not merged.overlaps(predicate_span))
            and not self._overlaps_any(merged, requested_spans)
            and self._runtime_temporal_normalizer.normalize(
                self._semantic_span(merged).text,
                TemporalAnchorContext(),
            ) is not None
        ):
            return merged

        # One canonical frame has one TIME role.  Distinct temporal values require
        # explicit temporal composition; silently keeping just one would corrupt M1.
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
            "set of requested/available answers rather than the predicate event. "
            "Requesting an additional or alternative answer belongs here.\n"
            "UNCLEAR: the source does not determine the scope safely.\n"
            "Candidate labels:\n"
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
                # START/STOP/CONTINUE/AGAIN/NO_LONGER remain owned by the existing
                # transition-normalization pass.  This scope gate only prevents the
                # source cue from simultaneously becoming an ordinary actant.
                self._transition_cue_token_indices.update(indices)
            elif decision == "DISCOURSE_OPERATOR":
                evidence = span.evidence
                if evidence not in self._runtime_discourse_operator_spans:
                    self._runtime_discourse_operator_spans.append(evidence)
        return blocked

    def _role_cue_probe(self, *args, **kwargs):
        # EVENT_RELATION was already selected by a smaller, dedicated scope probe;
        # generic role classification may choose its event role but may not reverse
        # that scope decision and call it a transition operator.
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

        queries = []
        changed = False
        for query in parsed.perception.queries:
            if not isinstance(query, EventSetQueryCandidate):
                queries.append(query)
                continue

            evidence = list(query.query_operator_evidence)
            # Preserve the same structural WH evidence that created the event-set
            # query; presentation must not rediscover it from a word list.
            for item in self._event_query_operator_evidence(query):
                if item not in evidence:
                    evidence.append(item)
            # Discourse/focus operators consumed before actant extraction are also
            # query-operator provenance.  For example an additive query modifier is
            # not a transition actant and must remain visible in M1.
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
