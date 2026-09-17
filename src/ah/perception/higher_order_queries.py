from __future__ import annotations

from dataclasses import replace

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
    """Coarse-to-fine semantic commitment on top of source-grounded structure.

    The lower parser still owns tokenization, clause structure, source spans and a
    provisional role assignment.  This layer deliberately does not build a second
    complete parse.  It revisits only decisions whose meaning depends on a larger
    semantic unit than the local role classifier can see:

    * a binary relation can constrain/correct the provisional endpoint roles;
    * an unresolved WH span can denote a higher-order relation description rather
      than an ordinary missing predicate argument.

    Both operations use bounded choices over already source-grounded candidates.
    There is no inventory of surface phrases, prepositions or predicate exceptions.
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

    @staticmethod
    def _plain_binary_actants(item):
        """Return two source-level entity candidates or an empty tuple.

        Rich proposition/composition/quantifier structure already has its own
        formalization contract and must not be flattened by a binary frame decision.
        """
        if len(item.actants) != 2:
            return ()
        for actant in item.actants:
            if (
                actant.candidate_ref is not None
                or actant.entity_ref is not None
                or actant.composition is not None
                or actant.proposition is not None
                or actant.quantifier is not None
                or not (actant.lookup_text or actant.mention)
            ):
                return ()
        return tuple(item.actants)

    def _normalize_predicate_semantics(self, source_text: str, item):
        """Let a whole binary semantic frame constrain provisional local roles.

        The previous production path asked whether SUBJECT already meant holder and
        OBJECT already meant possessed.  That made the higher semantic decision
        depend on lower roles being correct first.  Russian existential possession
        is a representative failure mode: a locally plausible prepositional role can
        prevent possession semantics from ever being considered.

        Here the model receives exactly two source-grounded candidates and chooses
        among four meanings.  It never emits canonical roles, UIDs or a parse tree.
        Python deterministically maps a possession orientation to SUBJECT/OBJECT and
        to the existing canonical possession predicate.
        """
        pair = self._plain_binary_actants(item)
        if not pair:
            return super()._normalize_predicate_semantics(source_text, item)

        first, second = pair
        rows = (
            f"E1: provisional_role={first.role.value}; text={first.lookup_text or first.mention}\n"
            f"E2: provisional_role={second.role.value}; text={second.lookup_text or second.mention}"
        )
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE SURFACE:\n{item.predicate.surface}\n"
            f"SOURCE-GROUNDED PARTICIPANTS:\n{rows}\n"
            "The provisional roles are lower-level evidence, not a constraint.\n"
            "Decision criterion:\n"
            "Does the complete binary proposition express possession/availability "
            "between E1 and E2? If yes, which entity is the holder/possessor and "
            "which is the possessed/available entity? Otherwise choose OTHER_RELATION."
        )
        decision, _ = self._deep_semantic_choice_probe(
            "binary_relation_frame",
            prompt,
            (
                "E1_HAS_E2",
                "E2_HAS_E1",
                "OTHER_RELATION",
                "UNCLEAR",
            ),
        )
        if decision == "OTHER_RELATION":
            return item, False
        if decision in {None, "UNCLEAR"}:
            raise AdaptiveParseError(
                "binary relation frame remains semantically unresolved",
                tuple(self._traces),
            )

        if decision == "E1_HAS_E2":
            holder, possessed = first, second
        elif decision == "E2_HAS_E1":
            holder, possessed = second, first
        else:
            raise AdaptiveParseError(
                f"invalid binary relation frame decision: {decision}",
                tuple(self._traces),
            )

        rewritten_holder = replace(holder, role=ActantRole.SUBJECT)
        rewritten_possessed = replace(possessed, role=ActantRole.OBJECT)
        rewritten_by_id = {
            id(holder): rewritten_holder,
            id(possessed): rewritten_possessed,
        }
        actants = tuple(rewritten_by_id[id(actant)] for actant in item.actants)

        predicate = item.predicate
        canonical = self._POSSESSION_CANONICAL_PREDICATE
        same_lookup = predicate.lookup_form.casefold().replace("ё", "е") == canonical
        rewritten_predicate = replace(
            predicate,
            normalized_hint=canonical,
            sense_hint="POSSESSION",
            template_selection=(predicate.template_selection if same_lookup else None),
        )
        rewritten = replace(
            item,
            predicate=rewritten_predicate,
            actants=actants,
        )
        return rewritten, rewritten != item

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

            # A higher-order relation request must already have two independently
            # filled participant slots.  This structural guard keeps ordinary
            # single-gap WH questions on the mature role-resolution path and avoids
            # an extra semantic probe for them.
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
    """Production perception service with coarse-to-fine semantic commitment."""

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
