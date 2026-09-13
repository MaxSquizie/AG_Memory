from __future__ import annotations

from .adaptive_parser import AdaptivePerceptionParser


class StructuralSpeechActAdaptiveParser(AdaptivePerceptionParser):
    """Adaptive parser with punctuation-independent clause force recognition.

    ``?`` is useful orthographic evidence, but it is not the definition of a
    question. Russian morphology explicitly marks interrogative pronouns/adverbs/
    determiners with the ``Ques`` grammeme.  When such a form belongs to the
    independent clause, the clause is a QUERY even if terminal punctuation is
    omitted.

    This class deliberately changes only speech-act classification.  It does not
    repair an already parsed result, inspect AH state, or maintain a surface-word
    list.  Requested-role extraction remains owned by the ordinary adaptive parser
    after QUERY has been selected.
    """

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
            analyses = self._material_morph_analyses(token)
            if any("Ques" in info.grammemes for info in analyses):
                return "QUERY"
        return base
