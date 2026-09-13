from __future__ import annotations

from dataclasses import replace

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .contracts import ActantCandidate, EvidenceSpan, QueryMode
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)
from .query_semantics import EntityIdentityQueryCandidate, EventSetQueryCandidate
from .runtime_invariants import (
    RuntimeSemanticAdaptiveParser,
    RuntimeSemanticLLMPerceptionService,
)


class IdentityQueryAdaptiveParser(RuntimeSemanticAdaptiveParser):
    """Recognize source-grounded questions whose unknown is entity identity.

    The deterministic gate is deliberately narrow: an already parsed EXISTS query
    must contain exactly one interrogative grammatical actant and exactly one plain
    non-interrogative entity candidate.  Only then does one bounded semantic probe
    distinguish identity/name lookup from ordinary copular/class predication.

    This avoids surface phrase rules such as ``кто пользователь`` while preventing
    action questions (normally FILL_ROLE/EVENT_SET) from entering the identity path.
    """

    _IDENTITY_CHOICES = (
        "ENTITY_IDENTITY",
        "ORDINARY_PREDICATION",
        "UNCLEAR",
    )

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

    def _identity_query_decision(
        self,
        source_text: str,
        query,
        target: ActantCandidate,
        interrogative: ActantCandidate,
    ) -> str:
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"SOURCE PREDICATE:\n{query.predicate.surface}\n"
            f"KNOWN ENTITY CANDIDATE:\n{target.lookup_text or target.mention or ''}\n"
            f"INTERROGATIVE CANDIDATE:\n"
            f"{interrogative.lookup_text or interrogative.mention or ''}\n"
            "QUESTION:\nWhat information does this question request?\n"
            "ENTITY_IDENTITY: it asks who/what the already known entity is called or "
            "which concrete identity/name denotes that entity.\n"
            "ORDINARY_PREDICATION: it asks whether/who satisfies a profession, class, "
            "property, role, state, relation, or other ordinary predicate; the known "
            "candidate is not merely an entity whose stored identity/name is requested.\n"
            "UNCLEAR: the source does not safely distinguish these readings.\n"
            "CHOICES:\n"
            + "\n".join(self._IDENTITY_CHOICES)
        )
        decision, _ = self._deep_semantic_choice_probe(
            "identity_query",
            prompt,
            self._IDENTITY_CHOICES,
        )
        assert decision is not None
        return decision

    def parse(self, text: str, *, structural_resolution: str | None = None):
        parsed = super().parse(text, structural_resolution=structural_resolution)
        rewritten = []
        changed = False

        for query in parsed.perception.queries:
            if (
                isinstance(query, (EventSetQueryCandidate, EntityIdentityQueryCandidate))
                or query.query_mode is not QueryMode.EXISTS
                or query.quantified is not None
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

            interrogative, operator_evidence = interrogative_rows[0]
            known = [
                actant for actant in query.actants
                if actant is not interrogative
            ]
            if len(known) != 1:
                rewritten.append(query)
                continue
            target = known[0]

            decision = self._identity_query_decision(
                text,
                query,
                target,
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
