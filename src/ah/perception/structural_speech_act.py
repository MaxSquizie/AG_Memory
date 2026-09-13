from __future__ import annotations

from .adaptive_parser import AdaptivePerceptionParser


class StructuralSpeechActAdaptiveParser(AdaptivePerceptionParser):
    """Adaptive parser with punctuation-independent clause force recognition.

    ``?`` is useful orthographic evidence, but it is not the definition of a
    question. Russian morphology explicitly marks interrogative pronouns/adverbs/
    determiners with the ``Ques`` grammeme.  When such a form belongs to the
    independent clause, the clause is a QUERY even if terminal punctuation is
    omitted.

    This class deliberately changes only speech-act classification and WH source
    discovery. It does not repair an already parsed result, inspect AH state, or
    maintain a surface-word list. Requested-role semantics remain owned by the
    ordinary bounded role classifier after the grammatical placeholder is found.
    """

    def _question_form(self, token) -> bool:
        """Recognize the closed interrogative grammatical class, not word forms."""
        # Keep every dictionary reading for this one closed-class check instead of
        # applying the generic open-class probability floor: a frequent
        # complementizer reading of the same surface form must not erase a valid
        # interrogative-pronoun reading before clause structure has established
        # where the token occurs.
        return any("Ques" in info.grammemes for info in self._morph_all(token))

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
