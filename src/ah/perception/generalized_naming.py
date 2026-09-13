from __future__ import annotations

from dataclasses import replace

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .contracts import ActantCandidate, AssertionStatus, EvidenceSpan
from .correlated_alternatives import CorrelatedAlternativeLLMPerceptionService
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)
from .naming_semantics import NamingAssertionCandidate
from .query_semantics import EventSetQueryCandidate
from .structural_speech_act import StructuralSpeechActAdaptiveParser
from ah.model import ActantRole


class GeneralizedNamingAdaptiveParser(StructuralSpeechActAdaptiveParser):
    """Extend source-grounded speech semantics without phrase dictionaries.

    Naming is treated as one semantic relation over source-grounded candidates,
    never as a list of lexical templates.  The parser now covers three structural
    realizations through the same bounded decision:

    * possessed nominal shells such as ``Моё имя — Илья`` (owned by the parent);
    * verbal naming such as ``Меня зовут Илья``;
    * deictic predication such as ``Я — Илья``, ``Илья — это я`` and explicit
      subject/state predication such as ``Я являюсь Ильёй``.

    For the last two families Python only identifies a deictic REFERENT and one or
    more source-grounded PREDICATIVE VALUE candidates.  A bounded semantic probe
    chooses exactly one name value, OTHER_PREDICATION, or UNCLEAR.  Consequently
    the same structure with a class/property value (``Я инженер`` / ``Я являюсь
    инженером``) remains an ordinary world predication and never becomes an alias.

    The same layer also preserves interrogative source evidence for the typed
    open-event query that the parent parser has already decided structurally. It
    does not infer question semantics a second time.
    """

    _NAME_VALUE_ROLES = frozenset(
        {
            ActantRole.SUBJECT,
            ActantRole.OBJECT,
            ActantRole.STATE,
            ActantRole.AUXILLIARY,
            ActantRole.RECIPIENT,
        }
    )

    @staticmethod
    def _span_contains(evidence: EvidenceSpan | None, token) -> bool:
        return (
            evidence is not None
            and evidence.start is not None
            and evidence.end is not None
            and evidence.start <= token.start
            and token.end <= evidence.end
        )

    @staticmethod
    def _spans_overlap(
        left: EvidenceSpan | None,
        right: EvidenceSpan | None,
    ) -> bool:
        if (
            left is None
            or right is None
            or left.start is None
            or left.end is None
            or right.start is None
            or right.end is None
        ):
            return False
        return left.start < right.end and right.start < left.end

    def _event_query_operator_evidence(
        self,
        query: EventSetQueryCandidate,
    ) -> tuple[EvidenceSpan, ...]:
        """Reuse the structural WH decision and preserve its exact source spans."""
        graph = self._candidate_graph
        predicate_evidence = query.predicate.evidence
        if (
            graph is None
            or predicate_evidence is None
            or predicate_evidence.start is None
            or predicate_evidence.end is None
        ):
            return ()
        predicate_tokens = [
            token
            for token in graph.tokens
            if token.start == predicate_evidence.start
            and token.end == predicate_evidence.end
        ]
        if len(predicate_tokens) != 1:
            return ()
        source_tokens = self._source_tokens_from_graph(graph)
        predicate_token = predicate_tokens[0]
        predicate_span = self._resolve_span_from_source(
            source_tokens,
            predicate_token.index,
            predicate_token.index,
        )
        words = self._explicit_question_words(source_tokens, predicate_span)
        return tuple(
            EvidenceSpan(word.text, word.start, word.end)
            for word in words
        )

    def _rewrite_open_event_queries(self, source_text: str, queries):
        rewritten, changed = super()._rewrite_open_event_queries(source_text, queries)
        enriched = []
        for query in rewritten:
            if (
                isinstance(query, EventSetQueryCandidate)
                and not query.query_operator_evidence
            ):
                evidence = self._event_query_operator_evidence(query)
                if evidence:
                    query = replace(query, query_operator_evidence=evidence)
                    changed = True
            enriched.append(query)
        return tuple(enriched), changed

    def _personal_deictic_tokens(
        self,
        evidence: EvidenceSpan | None,
        *,
        nominative_only: bool,
    ):
        """Return source tokens that are grammatical first/second-person pronouns."""
        graph = self._candidate_graph
        if graph is None or evidence is None:
            return ()
        out = []
        for token in graph.tokens:
            if not self._span_contains(evidence, token):
                continue
            personal = tuple(
                info
                for info in self._material_morph_analyses(token)
                if info.pos == "NPRO"
                and ({"1per", "2per"} & set(info.grammemes))
            )
            if not personal:
                continue
            cases = {info.case for info in personal if info.case}
            if nominative_only and cases != {"nomn"}:
                continue
            if not nominative_only and (not cases or "nomn" in cases):
                continue
            out.append(token)
        return tuple(out)

    @staticmethod
    def _owner_candidate(token) -> ActantCandidate:
        return ActantCandidate(
            ActantRole.SUBJECT,
            mention=token.text,
            evidence=EvidenceSpan(token.text, token.start, token.end),
        )

    def _verbal_deictic_owner(self, assertion) -> ActantCandidate | None:
        """Find one grammatical 1st/2nd-person oblique participant.

        Person/case are closed morphology features. They are used only to stage a
        possible naming relation; Integration's DeixisResolver still owns canonical
        USER/SELF identity resolution.
        """
        matches = []
        for actant in assertion.actants:
            for token in self._personal_deictic_tokens(
                actant.evidence,
                nominative_only=False,
            ):
                matches.append((token.start, token.end, token))

        unique = {(start, end): token for start, end, token in matches}
        if len(unique) != 1:
            return None
        return self._owner_candidate(next(iter(unique.values())))

    def _verbal_name_values(
        self,
        assertion,
        owner: ActantCandidate,
    ) -> tuple[ActantCandidate, ...]:
        """Return source-grounded nominal value candidates, never inferred names."""
        graph = self._candidate_graph
        if graph is None:
            return ()

        owner_evidence = owner.evidence
        values: list[ActantCandidate] = []
        seen: set[tuple[int | None, int | None, str]] = set()

        for actant in assertion.actants:
            if actant.role not in self._NAME_VALUE_ROLES:
                continue
            if (
                actant.candidate_ref is not None
                or actant.composition is not None
                or actant.proposition is not None
            ):
                continue
            evidence = actant.evidence
            source_text = (actant.mention or actant.normalized_hint or "").strip()
            if not source_text or evidence is None:
                continue
            if self._spans_overlap(owner_evidence, evidence):
                continue

            covered = [
                token
                for token in graph.tokens
                if self._span_contains(evidence, token)
            ]
            if not any(
                info.pos in {"NOUN", "NPRO", "ADJF", "PRTF"}
                for token in covered
                for info in self._material_morph_analyses(token)
            ):
                continue

            key = (evidence.start, evidence.end, source_text.casefold())
            if key in seen:
                continue
            seen.add(key)
            values.append(actant)

        return tuple(values)

    def _nominal_deictic_predication(
        self,
        assertion,
    ) -> tuple[ActantCandidate, tuple[ActantCandidate, ...]] | None:
        """Stage implicit-copula identity/classification without lexical markers.

        ``NOMINAL_PREDICATION`` already tells us that the source relates two nominal
        expressions.  This method only identifies which side is the deictic USER /
        SELF referent.  It works in both directions, so ``Я — Илья`` and
        ``Илья — это я`` reach the same semantic decision.  Whether the other side
        is a *name* or an ordinary class/property is deliberately left to the one
        bounded naming probe.
        """
        if (assertion.predicate.sense_hint or "").upper() != "NOMINAL_PREDICATION":
            return None

        sources: list[tuple[str, int | None, object]] = []
        for token in self._personal_deictic_tokens(
            assertion.predicate.evidence,
            nominative_only=True,
        ):
            sources.append(("predicate", None, token))
        for index, actant in enumerate(assertion.actants):
            for token in self._personal_deictic_tokens(
                actant.evidence,
                nominative_only=True,
            ):
                sources.append(("actant", index, token))

        unique_tokens = {
            (item[2].start, item[2].end): item[2]
            for item in sources
        }
        if len(unique_tokens) != 1:
            return None
        token = next(iter(unique_tokens.values()))
        owner = self._owner_candidate(token)

        owner_in_predicate = any(
            kind == "predicate" and source_token.start == token.start
            and source_token.end == token.end
            for kind, _index, source_token in sources
        )
        owner_actant_indices = {
            index
            for kind, index, source_token in sources
            if kind == "actant"
            and index is not None
            and source_token.start == token.start
            and source_token.end == token.end
        }

        values: list[ActantCandidate] = []
        if owner_in_predicate:
            for index, actant in enumerate(assertion.actants):
                if index in owner_actant_indices:
                    continue
                if actant.role not in self._NAME_VALUE_ROLES:
                    continue
                if not (actant.mention or actant.normalized_hint):
                    continue
                if self._spans_overlap(owner.evidence, actant.evidence):
                    continue
                values.append(actant)
        else:
            predicate = assertion.predicate
            if (
                predicate.surface.strip()
                and predicate.evidence is not None
                and not self._spans_overlap(owner.evidence, predicate.evidence)
            ):
                values.append(
                    ActantCandidate(
                        ActantRole.STATE,
                        mention=predicate.surface,
                        normalized_hint=predicate.normalized_hint,
                        evidence=predicate.evidence,
                    )
                )

        return (owner, tuple(values)) if values else None

    def _state_deictic_predication(
        self,
        assertion,
    ) -> tuple[ActantCandidate, tuple[ActantCandidate, ...]] | None:
        """Stage explicit subject/state copular-like predication.

        This covers inflected realizations such as ``Я являюсь Ильёй`` and
        ``Я являюсь инженером`` without knowing the governing verb.  The necessary
        structural evidence is already present: one grammatical deictic SUBJECT and
        one or more STATE values.  Ordinary transitive events with ``я`` therefore
        do not trigger this ambiguity probe merely because they contain another noun.
        """
        if (assertion.predicate.sense_hint or "").upper() == "NOMINAL_PREDICATION":
            return None

        subject_tokens = []
        for actant in assertion.actants:
            if actant.role is not ActantRole.SUBJECT:
                continue
            subject_tokens.extend(
                self._personal_deictic_tokens(
                    actant.evidence,
                    nominative_only=True,
                )
            )
        unique = {(token.start, token.end): token for token in subject_tokens}
        if len(unique) != 1:
            return None
        states = tuple(
            actant
            for actant in assertion.actants
            if actant.role is ActantRole.STATE
            and (actant.mention or actant.normalized_hint)
            and actant.candidate_ref is None
            and actant.composition is None
            and actant.proposition is None
        )
        if not states:
            return None
        return self._owner_candidate(next(iter(unique.values()))), states

    def _verbal_naming_choice(
        self,
        source_text: str,
        assertion,
        owner: ActantCandidate,
        values: tuple[ActantCandidate, ...],
    ) -> str:
        """Choose NAME vs ordinary predication over fixed source candidates only."""
        labels = tuple(f"VALUE_{index}" for index in range(1, len(values) + 1))
        rows = "\n".join(
            f"{label}: {(value.mention or value.lookup_text or '').strip()}"
            for label, value in zip(labels, values)
        )
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE:\n{assertion.predicate.surface}\n"
            f"ENTITY CANDIDATE:\n{owner.mention or owner.lookup_text or ''}\n"
            f"PREDICATIVE VALUE CANDIDATES:\n{rows}\n"
            "Decision criterion:\nDoes this source explicitly assign one PREDICATIVE VALUE "
            "CANDIDATE as the conventional personal/entity name or identifying "
            "label of ENTITY CANDIDATE? Select that value only for naming/identity. "
            "A profession, class, property, role, condition, appointment, action, "
            "description, or encounter is OTHER_PREDICATION.\n"
            "Candidate labels:\n"
            + "\n".join((*labels, "OTHER_PREDICATION", "UNCLEAR"))
        )
        decision, _ = self._deep_semantic_choice_probe(
            "naming_relation",
            prompt,
            (*labels, "OTHER_PREDICATION", "UNCLEAR"),
        )
        assert decision is not None
        return decision

    @staticmethod
    def _naming_candidate(assertion, owner, selected) -> NamingAssertionCandidate:
        # Preserve the source form for diagnostics/M1, but keep the morphology
        # normal form separately so Integration can index an inflected name under
        # its canonical lookup form (Ильёй -> Илья).
        source_value = (selected.mention or selected.lookup_text or "").strip()
        return NamingAssertionCandidate(
            local_id=assertion.local_id,
            predicate=assertion.predicate,
            actants=assertion.actants,
            evidence=assertion.evidence,
            alternatives=assertion.alternatives,
            negated=assertion.negated,
            status=assertion.status,
            temporal_mode=assertion.temporal_mode,
            transition_operator=assertion.transition_operator,
            temporal_scope=assertion.temporal_scope,
            quoted=assertion.quoted,
            owner=owner,
            name_value=source_value,
            name_normalized_hint=selected.normalized_hint,
        )

    def _rewrite_naming_assertions(self, source_text: str, assertions):
        # First preserve the mature possessed-nominal path (``Моё имя — Илья``)
        # and the existing oblique verbal path (``Меня зовут Илья``).
        base_rewritten, base_changed = super()._rewrite_naming_assertions(
            source_text, assertions
        )

        rewritten = []
        changed = base_changed
        for assertion in base_rewritten:
            if isinstance(assertion, NamingAssertionCandidate):
                rewritten.append(assertion)
                continue
            if (
                assertion.status is not AssertionStatus.ASSERTED
                or assertion.negated
                or assertion.quoted
            ):
                rewritten.append(assertion)
                continue

            staged = self._nominal_deictic_predication(assertion)
            if staged is None:
                staged = self._state_deictic_predication(assertion)
            if staged is None:
                # The historical verbal case uses an oblique deictic participant
                # and does not require a SUBJECT/STATE shell.
                owner = self._verbal_deictic_owner(assertion)
                values = () if owner is None else self._verbal_name_values(assertion, owner)
                staged = None if owner is None or not values else (owner, values)
            if staged is None:
                rewritten.append(assertion)
                continue

            owner, values = staged
            decision = self._verbal_naming_choice(
                source_text,
                assertion,
                owner,
                values,
            )
            if decision == "OTHER_PREDICATION":
                rewritten.append(assertion)
                continue
            if decision == "UNCLEAR":
                raise AdaptiveParseError(
                    "predication is ambiguous between entity naming and ordinary predication",
                    tuple(self._traces),
                )

            try:
                selected_index = int(decision.removeprefix("VALUE_")) - 1
                selected = values[selected_index]
            except (ValueError, IndexError) as exc:
                raise AdaptiveParseError(
                    f"invalid naming value decision: {decision}",
                    tuple(self._traces),
                ) from exc

            rewritten.append(self._naming_candidate(assertion, owner, selected))
            changed = True

        return tuple(rewritten), changed


class GeneralizedNamingLLMPerceptionService(
    CorrelatedAlternativeLLMPerceptionService
):
    """Production perception service using the generalized naming parser."""

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
        parser = GeneralizedNamingAdaptiveParser(
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
