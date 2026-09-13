from __future__ import annotations

from dataclasses import replace

from ah.model import ActantRole

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .contracts import ActantCandidate, AssertionStatus, EvidenceSpan, QueryMode
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)
from .naming_semantics import NamingAssertionCandidate
from .query_semantics import EntityIdentityQueryCandidate, EventSetQueryCandidate
from .runtime_invariants import (
    RuntimeSemanticAdaptiveParser,
    RuntimeSemanticLLMPerceptionService,
)


class IdentityQueryAdaptiveParser(RuntimeSemanticAdaptiveParser):
    """Production parser for source-grounded naming and identity questions.

    Two ambiguity classes are handled here without surface phrase dictionaries:

    * a synthetic/implicit copular assertion with one grammatical USER/SELF
      referent and nominal complements may be a naming assertion (``Я Илья``) or
      ordinary class/property predication (``Я инженер``); the existing bounded
      naming probe decides only between already source-grounded candidates;
    * an EXISTS question with one interrogative actant may ask for the identity of
      one of several source-grounded candidates (``Кто такой Илья?``).  A bounded
      finite-choice probe selects the target candidate, ordinary predication, or
      UNCLEAR.  Non-selected candidates are consumed as query-shell material only
      when the model explicitly chooses an identity target.

    Canonical UIDs are still unavailable in Perception.  Integration/Inference own
    entity resolution and all AH access.
    """

    _IDENTITY_TAIL_CHOICES = (
        "ORDINARY_PREDICATION",
        "UNCLEAR",
    )

    def _implicit_deictic_predication(
        self,
        assertion,
    ) -> tuple[ActantCandidate, tuple[ActantCandidate, ...]] | None:
        """Stage an implicit copular shell for the existing naming decision.

        ``AdaptivePerceptionParser`` marks a synthesized copula with ``IMPLICIT``
        and no predicate source span.  That is deterministic structural evidence
        that the source itself contained only nominal material.  We therefore may
        compare its nominal complement(s) with naming semantics without treating
        arbitrary transitive predicates containing ``я`` as naming candidates.
        """
        if (assertion.predicate.sense_hint or "").upper() != "IMPLICIT":
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

        owner = self._owner_candidate(next(iter(unique.values())))
        values = self._verbal_name_values(assertion, owner)
        return (owner, values) if values else None

    def _rewrite_naming_assertions(self, source_text: str, assertions):
        """Extend the mature naming layer to parser-synthesized implicit copulas."""
        base_rewritten, base_changed = super()._rewrite_naming_assertions(
            source_text,
            assertions,
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

            staged = self._implicit_deictic_predication(assertion)
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
                    "implicit predication is ambiguous between entity naming and ordinary predication",
                    tuple(self._traces),
                )

            try:
                selected_index = int(decision.removeprefix("VALUE_")) - 1
                selected = values[selected_index]
            except (ValueError, IndexError) as exc:
                raise AdaptiveParseError(
                    f"invalid implicit naming value decision: {decision}",
                    tuple(self._traces),
                ) from exc

            rewritten.append(self._naming_candidate(assertion, owner, selected))
            changed = True

        return tuple(rewritten), changed

    def _question_evidence(self, actant: ActantCandidate) -> tuple[EvidenceSpan, ...]:
        evidence = actant.evidence
        graph = self._candidate_graph
        if (
            evidence is None
            or evidence.start is None
            or evidence.end is None
            or graph is None
        ):
            return ()
        out: list[EvidenceSpan] = []
        for token in graph.tokens:
            if token.start < evidence.start or token.end > evidence.end:
                continue
            if not self._question_form(token):
                continue
            item = EvidenceSpan(token.text, token.start, token.end)
            if item not in out:
                out.append(item)
        return tuple(out)

    @staticmethod
    def _candidate_text(candidate: ActantCandidate) -> str:
        return (candidate.lookup_text or candidate.mention or "").strip()

    def _identity_query_decision(
        self,
        source_text: str,
        query,
        candidates: tuple[ActantCandidate, ...],
        interrogative: ActantCandidate,
    ) -> str:
        labels = tuple(f"TARGET_{index}" for index in range(1, len(candidates) + 1))
        rows = "\n".join(
            f"{label}: role={candidate.role.value}; text={self._candidate_text(candidate)}"
            for label, candidate in zip(labels, candidates)
        )
        choices = (*labels, *self._IDENTITY_TAIL_CHOICES)
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"SOURCE PREDICATE:\n{query.predicate.surface}\n"
            f"INTERROGATIVE:\n{self._candidate_text(interrogative)}\n"
            f"NON-INTERROGATIVE CANDIDATES:\n{rows}\n"
        )
        decision, _ = self._deep_semantic_choice_probe(
            "identity_query",
            prompt,
            choices,
        )
        assert decision is not None
        return decision

    @staticmethod
    def _append_evidence_unique(
        out: list[EvidenceSpan],
        evidence: EvidenceSpan | None,
    ) -> None:
        if evidence is None:
            return
        key = (evidence.start, evidence.end, evidence.text)
        if all((item.start, item.end, item.text) != key for item in out):
            out.append(evidence)

    def _identity_operator_evidence(
        self,
        interrogative_evidence: tuple[EvidenceSpan, ...],
        shell_candidates: tuple[ActantCandidate, ...],
    ) -> tuple[EvidenceSpan, ...]:
        """Preserve all source material explicitly consumed by identity semantics."""
        out = list(interrogative_evidence)
        for candidate in shell_candidates:
            self._append_evidence_unique(out, candidate.evidence)
        return tuple(out)

    def parse(self, text: str, *, structural_resolution: str | None = None):
        parsed = super().parse(text, structural_resolution=structural_resolution)
        rewritten = []
        changed = False

        for query in parsed.perception.queries:
            if (
                isinstance(query, (EventSetQueryCandidate, EntityIdentityQueryCandidate))
                or query.query_mode is not QueryMode.EXISTS
                or query.quantified is not None
                or query.requested_role is not None
                or query.requested_roles
                or any(
                    actant.candidate_ref is not None
                    or actant.proposition is not None
                    or actant.composition is not None
                    or actant.entity_ref is not None
                    for actant in query.actants
                )
            ):
                rewritten.append(query)
                continue

            interrogative_rows = [
                (actant, self._question_evidence(actant))
                for actant in query.actants
            ]
            interrogative_rows = [row for row in interrogative_rows if row[1]]
            if len(interrogative_rows) != 1:
                rewritten.append(query)
                continue

            interrogative, interrogative_evidence = interrogative_rows[0]
            candidates = tuple(
                actant for actant in query.actants
                if actant is not interrogative
            )
            if not candidates:
                rewritten.append(query)
                continue

            decision = self._identity_query_decision(
                text,
                query,
                candidates,
                interrogative,
            )
            if decision == "ORDINARY_PREDICATION":
                rewritten.append(query)
                continue
            if decision == "UNCLEAR":
                raise AdaptiveParseError(
                    "query is ambiguous between entity identity and ordinary predication",
                    tuple(self._traces),
                )

            try:
                selected_index = int(decision.removeprefix("TARGET_")) - 1
                target = candidates[selected_index]
            except (ValueError, IndexError) as exc:
                raise AdaptiveParseError(
                    f"invalid identity target decision: {decision}",
                    tuple(self._traces),
                ) from exc

            shell = tuple(
                candidate
                for index, candidate in enumerate(candidates)
                if index != selected_index
            )
            operator_evidence = self._identity_operator_evidence(
                interrogative_evidence,
                shell,
            )
            rewritten.append(
                EntityIdentityQueryCandidate(
                    predicate=query.predicate,
                    actants=(target,),
                    requested_role=None,
                    requested_roles=(),
                    query_mode=QueryMode.EXISTS,
                    local_id=query.local_id,
                    quoted=query.quoted,
                    quantified=None,
                    scope_operators=query.scope_operators,
                    target=target,
                    query_operator_evidence=operator_evidence,
                )
            )
            changed = True

        if not changed:
            return parsed
        return replace(
            parsed,
            perception=replace(parsed.perception, queries=tuple(rewritten)),
        )


class IdentityQueryLLMPerceptionService(RuntimeSemanticLLMPerceptionService):
    """Production perception service including typed entity-identity questions."""

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
        parser = IdentityQueryAdaptiveParser(
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
