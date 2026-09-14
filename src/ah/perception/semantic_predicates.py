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

    This layer contains no phrase inventory. It supplies source-structural staging
    for zero-copula identity questions, normalizes possession paraphrases to one
    semantic predicate, and can promote a genuinely generic possession question to
    the existing typed FORALL-query contract. Canonical AH UIDs are unavailable.
    """

    _POSSESSION_CANONICAL_PREDICATE = "иметь"

    @staticmethod
    def _clause_source_text(source_text: str, clause) -> str:
        evidence = clause.span.evidence
        start = getattr(evidence, "start", None)
        end = getattr(evidence, "end", None)
        if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(source_text):
            value = source_text[start:end].strip()
            if value:
                return value
        return str(clause.span.text or "").strip()

    def _resolve_relative_adverb_clause_modes(self, builder, graph):
        """Resolve relative-adverb ambiguity from the local clause pair only.

        Whole-document ingestion can pass thousands of characters through one
        perception call. Feeding that complete chunk to a tiny RELATIVE/SUBORDINATE
        probe makes repeated connectors such as ``где``/``когда`` indistinguishable
        to the model. The structural graph has already isolated the child clause and
        its parent, so expose exactly that bounded evidence instead of unrelated
        neighbouring diary entries. The decision remains fail-closed and uses the
        same labels and graph rewrite as the base parser.
        """
        ambiguous = [
            clause
            for clause in graph.clauses
            if clause.relative
            and (clause.marker or "").casefold() in {"где", "куда", "откуда", "когда"}
        ]
        if not ambiguous:
            return graph

        clauses = list(graph.clauses)
        changed = False
        for clause in ambiguous:
            parent = next(
                (
                    item
                    for item in graph.clauses
                    if item.clause_id == clause.parent_clause_id
                ),
                None,
            )
            child_text = self._clause_source_text(graph.text, clause)
            parent_text = (
                self._clause_source_text(graph.text, parent)
                if parent is not None
                else "[no explicit parent clause]"
            )
            prompt = (
                f"PARENT CLAUSE:\n{parent_text}\n"
                f"TARGET CLAUSE:\n{child_text}\n"
                f"CONNECTOR:\n{clause.marker}\n"
                "Decision criterion:\nDoes this connector introduce a relative clause that modifies a nominal "
                "anchor in PARENT CLAUSE, or an independent subordinate situation relation?\n"
                "Candidate labels:\nRELATIVE\nSUBORDINATE"
            )
            decision, _ = self._exact_choice_probe(
                "relative_clause_mode",
                prompt,
                ("RELATIVE", "SUBORDINATE", "UNCLEAR"),
            )
            if decision == "UNCLEAR":
                raise AdaptiveParseError(
                    "relative/subordinate clause mode remains unresolved"
                )
            if decision == "RELATIVE":
                continue
            index = next(
                i
                for i, item in enumerate(clauses)
                if item.clause_id == clause.clause_id
            )
            clauses[index] = replace(clause, relative=False)
            changed = True

        if not changed:
            return graph
        clause_tuple = tuple(clauses)
        frame_graph = builder._frame_graph(
            graph.tokens,
            clause_tuple,
            graph.predicates,
            graph.frame_graph.coordinations,
        )
        return replace(graph, clauses=clause_tuple, frame_graph=frame_graph)

    def _explicit_question_words(self, tokens, predicate_span=None):
        """Keep WH material as an actant inside a zero-copula nominal question.

        In ``Кто Илья?`` there is no written predicate. Treating ``Кто`` as a role
        gap removes it before the identity layer can see the complete nominal shell.
        When no predicate span exists and the same clause also contains ordinary
        nominal material, the interrogative remains source material of the implicit
        copula. Clause force is still QUERY because ``_question_form`` is unchanged.
        """
        result = super()._explicit_question_words(tokens, predicate_span)
        if predicate_span is not None or not result:
            return result
        graph = self._candidate_graph
        if graph is None:
            return result
        question_indices = {token.index for token in result}
        has_non_question_nominal = any(
            token.index not in question_indices
            and self._structural_nominal_infos(token)
            for token in tokens
        )
        return () if has_non_question_nominal else result

    def _deterministic_role_candidates(
        self,
        tokens,
        predicate_span,
        predicate,
        span,
    ):
        # Provisional roles for an implicit nominal question. They only let the
        # base parser finish; IdentityQueryAdaptiveParser subsequently decides
        # identity-vs-ordinary predication from the whole source.
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
