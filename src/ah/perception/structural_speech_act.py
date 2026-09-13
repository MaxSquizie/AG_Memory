from __future__ import annotations

from dataclasses import replace

from ah.model import ActantRole
from ah.temporal import TemporalAnchorContext, TemporalNormalizer

from .adaptive_parser import AdaptiveParseError, AdaptivePerceptionParser
from .contracts import QueryMode
from .query_semantics import EventSetQueryCandidate


class StructuralSpeechActAdaptiveParser(AdaptivePerceptionParser):
    """Adaptive parser extensions for grammatical force and typed query targets.

    ``?`` is useful orthographic evidence, but it is not the definition of a
    question. Russian morphology explicitly marks interrogative pronouns/adverbs/
    determiners with the ``Ques`` grammeme. When such a form belongs to the
    independent clause, the clause is a QUERY even if terminal punctuation is
    omitted.

    The same layer also closes two source-structural gaps without surface phrase
    dictionaries:

    * a phrase already recognized by the canonical ``TemporalNormalizer`` is a
      TIME actant before free semantic role classification; the normalizer may
      leave its value unresolved until Integration receives the legal turn/source
      timestamp anchor;
    * after ordinary WH parsing has produced a role-gap reading, one bounded
      UID-free semantic choice distinguishes a missing role of a fixed predicate
      from a request for the event/action itself. The latter becomes an explicit
      ``EventSetQueryCandidate`` and is compiled by inference without pretending
      the source verb is the answer predicate.

    No canonical UID or AH state is visible here and no source-word list selects
    either behavior.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._source_temporal_normalizer = TemporalNormalizer()

    def _question_form(self, token) -> bool:
        """Recognize the closed interrogative grammatical class, not word forms."""
        # Keep every dictionary reading for this one closed-class check instead of
        # applying the generic open-class probability floor: a frequent
        # complementizer reading of the same surface form must not erase a valid
        # interrogative-pronoun reading before clause structure has established
        # where the token occurs.
        return any("Ques" in info.grammemes for info in self._morph_all(token))

    def _deterministic_role_candidates(
        self,
        tokens,
        predicate_span,
        predicate,
        span,
    ):
        """Promote formally recognized temporal source spans to canonical TIME.

        Relative expressions deliberately do not need an anchor here. A returned
        unresolved ``TemporalCandidate`` is already sufficient evidence that the
        source phrase is temporal; Integration later resolves its value against the
        authoritative source/experience timestamp. Unknown adverbs still fall
        through to the ordinary bounded role classifier.
        """
        semantic_span = self._semantic_span(span)
        temporal = self._source_temporal_normalizer.normalize(
            semantic_span.text,
            TemporalAnchorContext(),
        )
        if temporal is not None:
            return (ActantRole.TIME,)
        return super()._deterministic_role_candidates(
            tokens,
            predicate_span,
            predicate,
            span,
        )

    def _explicit_question_words(
        self,
        tokens,
        predicate_span=None,
    ):
        """Return clause-local WH placeholders from morphology + clause structure."""
        connector_indices: set[int] = set()
        if self._candidate_graph is not None:
            for clause in self._candidate_graph.clauses:
                if clause.connector_span is not None:
                    connector_indices.update(
                        range(
                            clause.connector_span.start_index,
                            clause.connector_span.end_index + 1,
                        )
                    )
        first_predicate = None
        if self._candidate_graph is not None and self._candidate_graph.predicates:
            first_predicate = min(
                item.token_index for item in self._candidate_graph.predicates
            )
        clause_start, clause_end = self._clause_bounds(predicate_span, tokens)
        result = []
        for token in tokens:
            if token.index < clause_start or token.index > clause_end:
                continue
            if not self._question_form(token):
                continue
            # The same grammatical form may head an embedded interrogative clause.
            # A connector-owned token is a top-level query placeholder only when it
            # precedes the first predicate of the current independent utterance.
            if token.index in connector_indices and not (
                first_predicate is not None and token.index < first_predicate
            ):
                continue
            result.append(token)
        return tuple(result)

    def _deterministic_act_type(
        self,
        tokens,
        predicate_candidates,
        clause_id,
    ) -> str | None:
        base = super()._deterministic_act_type(
            tokens, predicate_candidates, clause_id
        )
        # Preserve stronger force already established by ordinary syntax:
        # imperative COMMAND and punctuation/quoted QUERY both win immediately.
        if base != "ASSERTION":
            return base

        graph = self._candidate_graph
        clause = None
        if graph is not None and clause_id is not None:
            clause = next(
                (item for item in graph.clauses if item.clause_id == clause_id),
                None,
            )

        if clause is not None:
            start, end = clause.span.start_index, clause.span.end_index
            focus_index = predicate_candidates[0] if predicate_candidates else start
        elif predicate_candidates:
            focus_index = predicate_candidates[0]
            start, end = self._clause_bounds(
                self._resolve_span_from_source(tokens, focus_index, focus_index),
                tokens,
            )
        else:
            start, end = 1, len(tokens)
            focus_index = start

        embedded = False
        quoted = bool(clause.quoted) if clause is not None else False
        if graph is not None and predicate_candidates:
            embedded = graph.frame_graph.is_embedded(focus_index)
        elif clause is not None and clause.parent_clause_id is not None:
            embedded = True
        # An indirect question is proposition content, not the force of the whole
        # user turn. Quoted clauses retain their own independent force.
        if embedded and not quoted:
            return base

        def is_descendant(candidate) -> bool:
            """Whether candidate is nested below the current independent clause."""
            if graph is None or clause is None or candidate.clause_id == clause.clause_id:
                return False
            parent = candidate.parent_clause_id
            visited: set[str] = set()
            while parent is not None and parent not in visited:
                if parent == clause.clause_id:
                    return True
                visited.add(parent)
                owner = next(
                    (item for item in graph.clauses if item.clause_id == parent),
                    None,
                )
                parent = None if owner is None else owner.parent_clause_id
            return False

        nested_ranges = tuple(
            (item.span.start_index, item.span.end_index)
            for item in (() if graph is None else graph.clauses)
            if is_descendant(item) and not item.quoted
        )

        for token in tokens:
            if token.index < start or token.index > end:
                continue
            if any(left <= token.index <= right for left, right in nested_ranges):
                continue
            if self._question_form(token):
                return "QUERY"
        return base

    def _query_target_kind(self, source_text: str, query) -> str:
        known = "\n".join(
            f"{actant.role.value}={actant.lookup_text or '[structured value]'}"
            for actant in query.actants
        ) or "NONE"
        requested = ", ".join(role.value for role in query.requested_roles) or "NONE"
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"SOURCE PREDICATE:\n{query.predicate.surface}\n"
            f"KNOWN EVENT ROLES:\n{known}\n"
            f"CURRENT WH ROLE READING:\n{requested}\n"
            "QUESTION:\nDoes the interrogative ask for a missing value inside the "
            "stated predicate, or does it ask which event/action/state itself "
            "occurred under the known constraints?\n"
            "CHOICES:\nROLE_FILL\nEVENT_SET\nUNCLEAR"
        )
        decision, _ = self._deep_semantic_choice_probe(
            "query_target",
            prompt,
            ("ROLE_FILL", "EVENT_SET", "UNCLEAR"),
        )
        assert decision is not None
        return decision

    def parse(self, text: str, *, structural_resolution: str | None = None):
        parsed = super().parse(text, structural_resolution=structural_resolution)
        rewritten = []
        changed = False
        for query in parsed.perception.queries:
            # Quantified and proposition-valued queries already own richer typed
            # semantics and must not be reinterpreted by this ordinary WH layer.
            if (
                query.query_mode is not QueryMode.FILL_ROLE
                or query.quantified is not None
                or any(
                    actant.proposition is not None or actant.candidate_ref is not None
                    for actant in query.actants
                )
            ):
                rewritten.append(query)
                continue
            target = self._query_target_kind(text, query)
            if target == "ROLE_FILL":
                rewritten.append(query)
                continue
            if target == "UNCLEAR":
                raise AdaptiveParseError(
                    "query target is ambiguous between role filling and event retrieval",
                    tuple(self._traces),
                )
            rewritten.append(
                EventSetQueryCandidate(
                    predicate=query.predicate,
                    actants=query.actants,
                    requested_role=None,
                    requested_roles=(),
                    query_mode=QueryMode.EXISTS,
                    local_id=query.local_id,
                    quoted=query.quoted,
                    quantified=None,
                    scope_operators=(),
                )
            )
            changed = True

        if not changed:
            return parsed
        perception = replace(parsed.perception, queries=tuple(rewritten))
        return replace(parsed, perception=perception)
