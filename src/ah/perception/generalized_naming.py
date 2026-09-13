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
from .structural_speech_act import StructuralSpeechActAdaptiveParser
from ah.model import ActantRole


class GeneralizedNamingAdaptiveParser(StructuralSpeechActAdaptiveParser):
    """Extend naming semantics to verbal source structures without phrase lists.

    The existing structural parser already handles nominal naming shells such as
    ``Моё имя — Илья``. Russian also expresses the same semantic relation through
    an ordinary finite predicate (``Меня зовут Илья``). No lexical verb is treated
    as a naming marker here. Instead Python supplies only source-grounded
    candidates:

    * one first/second-person non-nominative pronoun is a possible named entity;
    * ordinary participant/state nominal spans are possible name values;
    * a bounded semantic probe may select exactly one value, reject naming, or
      return UNCLEAR.

    Thus the model never constructs roles/UIDs and ordinary sentences such as
    ``Меня встретила Мария`` remain ordinary predication when the probe rejects
    the naming interpretation.
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

    def _verbal_deictic_owner(self, assertion) -> ActantCandidate | None:
        """Find one grammatical 1st/2nd-person oblique participant.

        Person/case are closed morphology features. They are used only to stage a
        possible naming relation; Integration's DeixisResolver still owns canonical
        USER/SELF identity resolution.
        """
        graph = self._candidate_graph
        if graph is None:
            return None

        matches = []
        for actant in assertion.actants:
            evidence = actant.evidence
            if evidence is None:
                continue
            for token in graph.tokens:
                if not self._span_contains(evidence, token):
                    continue
                analyses = tuple(self._material_morph_analyses(token))
                personal = tuple(
                    info
                    for info in analyses
                    if info.pos == "NPRO"
                    and ({"1per", "2per"} & set(info.grammemes))
                )
                if not personal:
                    continue
                cases = {info.case for info in personal if info.case}
                if not cases or "nomn" in cases:
                    continue
                matches.append((token.start, token.end, token))

        unique = {(start, end): token for start, end, token in matches}
        if len(unique) != 1:
            return None
        token = next(iter(unique.values()))
        return ActantCandidate(
            ActantRole.SUBJECT,
            mention=token.text,
            evidence=EvidenceSpan(token.text, token.start, token.end),
        )

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
                or actant.entity_ref is not None
                or actant.composition is not None
                or actant.proposition is not None
            ):
                continue
            evidence = actant.evidence
            text = (actant.lookup_text or "").strip()
            if not text or evidence is None:
                continue
            if (
                owner_evidence is not None
                and owner_evidence.start is not None
                and owner_evidence.end is not None
                and evidence.start is not None
                and evidence.end is not None
                and not (
                    evidence.end <= owner_evidence.start
                    or owner_evidence.end <= evidence.start
                )
            ):
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

            key = (evidence.start, evidence.end, text.casefold())
            if key in seen:
                continue
            seen.add(key)
            values.append(actant)

        return tuple(values)

    def _verbal_naming_choice(
        self,
        source_text: str,
        assertion,
        owner: ActantCandidate,
        values: tuple[ActantCandidate, ...],
    ) -> str:
        labels = tuple(f"VALUE_{index}" for index in range(1, len(values) + 1))
        rows = "\n".join(
            f"{label}: {value.lookup_text}"
            for label, value in zip(labels, values)
        )
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE:\n{assertion.predicate.surface}\n"
            f"ENTITY CANDIDATE:\n{owner.lookup_text}\n"
            f"NAME VALUE CANDIDATES:\n{rows}\n"
            "QUESTION:\nDoes this source explicitly assign one NAME VALUE "
            "CANDIDATE as the conventional name/label by which ENTITY CANDIDATE "
            "is called? Select that value only when the source itself expresses "
            "a naming relation. Ordinary actions, classifications, appointments, "
            "descriptions and encounters are OTHER_PREDICATION.\n"
            "CHOICES:\n"
            + "\n".join((*labels, "OTHER_PREDICATION", "UNCLEAR"))
        )
        decision, _ = self._deep_semantic_choice_probe(
            "naming_relation",
            prompt,
            (*labels, "OTHER_PREDICATION", "UNCLEAR"),
        )
        assert decision is not None
        return decision

    def _rewrite_naming_assertions(self, source_text: str, assertions):
        # Keep the mature nominal-predication path (e.g. ``Моё имя — Илья``).
        nominal_rewritten, nominal_changed = super()._rewrite_naming_assertions(
            source_text, assertions
        )

        rewritten = []
        changed = nominal_changed
        for assertion in nominal_rewritten:
            if isinstance(assertion, NamingAssertionCandidate):
                rewritten.append(assertion)
                continue
            if (
                assertion.status is not AssertionStatus.ASSERTED
                or assertion.negated
                or assertion.quoted
                or (assertion.predicate.sense_hint or "").upper()
                == "NOMINAL_PREDICATION"
            ):
                rewritten.append(assertion)
                continue

            owner = self._verbal_deictic_owner(assertion)
            if owner is None:
                rewritten.append(assertion)
                continue
            values = self._verbal_name_values(assertion, owner)
            if not values:
                rewritten.append(assertion)
                continue

            decision = self._verbal_naming_choice(
                source_text, assertion, owner, values
            )
            if decision == "OTHER_PREDICATION":
                rewritten.append(assertion)
                continue
            if decision == "UNCLEAR":
                raise AdaptiveParseError(
                    "verbal predication is ambiguous between entity naming and ordinary predication",
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

            rewritten.append(
                NamingAssertionCandidate(
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
                    name_value=selected.lookup_text or "",
                    name_normalized_hint=selected.normalized_hint,
                )
            )
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
