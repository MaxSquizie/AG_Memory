from __future__ import annotations

from dataclasses import replace
import re

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
    provisional role assignment. This layer deliberately does not build a second
    complete parse. It revisits only decisions whose meaning depends on a larger
    semantic unit than the local role classifier can see:

    * a binary relation can constrain/correct provisional endpoint roles;
    * a structurally coordinated group can remain an endpoint set while a
      higher-order relation query is being recognized, instead of being forced into
      an ordinary local role first;
    * an unresolved WH span can denote a higher-order relation description rather
      than an ordinary missing predicate argument.

    Every semantic decision is bounded over already source-grounded alternatives.
    There is no inventory of surface phrases, prepositions or predicate exceptions.
    """

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
        OBJECT already meant possessed. That made the higher semantic decision
        depend on lower roles being correct first. Russian existential possession is
        a representative failure mode: a locally plausible prepositional role can
        prevent possession semantics from ever being considered.

        Here the model receives exactly two source-grounded candidates and chooses
        among four meanings. It never emits canonical roles, UIDs or a parse tree.
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

    @staticmethod
    def _forbidden_roles(value) -> set[ActantRole]:
        if value is None:
            return set()
        if isinstance(value, ActantRole):
            return {value}
        return set(value)

    def _relation_endpoint_coordination(self, text: str, span):
        """Return one source-grounded binary coordination carried by ``span``.

        The coordination graph is lower-level structure, not a semantic guess. A
        wider span is accepted only when every source word outside the coordinated
        members is functional morphology (preposition/conjunction/particle). Thus a
        governor can wrap ``A and B`` without forcing that whole phrase into a
        canonical actant role before the utterance-level operation is known.
        """
        graph = self._candidate_graph
        if graph is None:
            return None
        matches = [
            item
            for item in graph.coordinations
            if span.start_index <= item.span.start_index
            and item.span.end_index <= span.end_index
            and len(item.member_spans) == 2
        ]
        if len(matches) != 1:
            return None
        group = matches[0]

        source_tokens = self._source_tokens(text)
        outside = [
            token
            for token in source_tokens
            if span.start_index <= token.index <= span.end_index
            and not (group.span.start_index <= token.index <= group.span.end_index)
            and re.search(r"\w", token.text)
        ]
        if any(
            not self._has_morph(token, poses={"PREP", "CONJ", "PRCL"})
            for token in outside
        ):
            return None

        clause = graph.clause_for_token(span.start_index)
        if clause is None:
            return None
        question_tokens = self._explicit_question_words(source_tokens, None)
        if not any(
            clause.span.start_index <= token.index <= clause.span.end_index
            for token in question_tokens
        ):
            return None
        return group

    def _recover_relation_endpoint_role(
        self,
        *,
        text: str,
        predicate,
        span,
        used_roles: set[ActantRole],
        forbidden_role,
        allowed_roles: set[ActantRole] | None,
    ) -> ActantRole | None:
        """Preserve a binary endpoint set until the higher semantic operation settles.

        AUXILLIARY is used only as the existing runtime carrier role. The two member
        identities stay explicit in ``ActantCompositionCandidate`` and association
        endpoint selection addresses them by member index. No AUXILLIARY fact is
        asserted: queries are compiled into runtime goals before ordinary query
        inference.
        """
        carrier = ActantRole.AUXILLIARY
        if (
            carrier in used_roles
            or carrier in self._forbidden_roles(forbidden_role)
            or (allowed_roles is not None and carrier not in allowed_roles)
        ):
            return None
        group = self._relation_endpoint_coordination(text, span)
        if group is None:
            return None

        source_tokens = self._source_tokens(text)
        members = tuple(
            self._resolve_span(
                text,
                source_tokens,
                member.start_index,
                member.end_index,
            )
            for member in group.member_spans
        )
        member_rows = "\n".join(
            f"E{index}={member.text}" for index, member in enumerate(members, start=1)
        )
        prompt = (
            f"TEXT:\n{text}\n"
            f"PARSED PREDICATE:\n{predicate.surface}\n"
            f"LOCALLY UNRESOLVED GROUP:\n{span.text}\n"
            f"STRUCTURAL MEMBERS:\n{member_rows}\n"
            "Decision criterion:\n"
            "At the level of the complete question, is this binary coordinated "
            "group the set of two endpoints whose relation/property/schema is being "
            "requested, or is the group an ordinary participant/circumstance of the "
            "parsed predicate? The source coordination is already established; "
            "decide only its semantic level."
        )
        decision, _ = self._deep_semantic_choice_probe(
            "query_endpoint_level",
            prompt,
            ("RELATION_ENDPOINT_SET", "ORDINARY_ARGUMENT", "UNCLEAR"),
        )
        if decision != "RELATION_ENDPOINT_SET":
            return None

        # Make the wider governed span a runtime composition so the ordinary
        # ActantCandidate constructor preserves both members. This is parser-local
        # state only and disappears after Perception.
        self._runtime_compositions[(span.start_index, span.end_index)] = (
            group.operator,
            members,
        )
        self._deterministic_trace(
            "query_endpoint_level_commitment",
            prompt,
            "RELATION_ENDPOINT_SET->AUXILLIARY_COMPOSITION",
        )
        return carrier

    def _classify_role(
        self,
        text,
        predicate,
        span,
        used_roles,
        forbidden_role,
        *,
        requested,
        allowed_roles=None,
        allow_none=False,
    ):
        """Allow higher query structure to postpone one failed local role choice."""
        try:
            return super()._classify_role(
                text,
                predicate,
                span,
                used_roles,
                forbidden_role,
                requested=requested,
                allowed_roles=allowed_roles,
                allow_none=allow_none,
            )
        except AdaptiveParseError as original:
            # Requested WH material has a separate late-commit path below. This
            # branch is only for an explicit source phrase whose local role probe
            # returned UNCLEAR before the query operation itself could be built.
            if requested or str(original) != "target semantic role remains unresolved":
                raise
            recovered = self._recover_relation_endpoint_role(
                text=text,
                predicate=predicate,
                span=span,
                used_roles=set(used_roles),
                forbidden_role=forbidden_role,
                allowed_roles=(None if allowed_roles is None else set(allowed_roles)),
            )
            if recovered is None:
                raise original
            return recovered

    def _requested_query_roles(self, *args, **kwargs):
        try:
            return super()._requested_query_roles(*args, **kwargs)
        except AdaptiveParseError as original:
            message = str(original)
            if (
                "requested role unresolved" not in message
                and message != "target semantic role remains unresolved"
            ):
                raise

            if len(args) < 3:
                raise
            text = args[0]
            tokens = args[1]
            predicate = args[2]
            predicate_span = args[3] if len(args) > 3 else kwargs.get("predicate_span")
            used_roles = set(kwargs.get("used_roles") or ())
            requested_spans = kwargs.get("requested_spans")
            spans = (
                tuple(requested_spans)
                if requested_spans is not None
                else self._requested_query_spans(text, tokens, predicate_span)
            )
            if len(spans) != 1:
                # Multiple unresolved holes need an explicit compositional contract;
                # do not collapse them into one relation request by guess.
                raise original

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
            # description, not a claim that STATE is a filled world fact. The
            # association semantic overlay removes relation-description material
            # from endpoint selection and compiles the query into a runtime goal.
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
