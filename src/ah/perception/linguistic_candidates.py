from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re

from .contracts import EvidenceSpan
from .morphology import MorphInfo, Morphology


class CoordinationKind(str, Enum):
    AND = "AND"
    OR = "OR"


@dataclass(frozen=True, slots=True)
class SourceToken:
    index: int
    text: str
    start: int
    end: int
    analyses: tuple[MorphInfo, ...] = ()

    def has_pos(self, *poses: str) -> bool:
        wanted = set(poses)
        return any(item.pos in wanted for item in self.analyses)

    def has_case(self, case: str, *, poses: set[str] | None = None) -> bool:
        return any(
            item.case == case and (poses is None or item.pos in poses)
            for item in self.analyses
        )


@dataclass(frozen=True, slots=True)
class CandidateSpan:
    start_index: int
    end_index: int
    text: str
    evidence: EvidenceSpan

    def overlaps(self, other: "CandidateSpan") -> bool:
        return not (self.end_index < other.start_index or other.end_index < self.start_index)


@dataclass(frozen=True, slots=True)
class PredicateHeadCandidate:
    token_index: int
    strength: int
    finite: bool
    lemma_candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClauseCandidate:
    clause_id: str
    sentence_id: int
    span: CandidateSpan
    predicate_heads: tuple[PredicateHeadCandidate, ...]
    marker: str | None = None
    parent_clause_id: str | None = None
    parent_role_hint: str | None = None
    connector_span: CandidateSpan | None = None
    relative: bool = False


@dataclass(frozen=True, slots=True)
class CoordinationCandidate:
    operator: CoordinationKind
    span: CandidateSpan
    member_spans: tuple[CandidateSpan, ...]


@dataclass(frozen=True, slots=True)
class LinguisticCandidateGraph:
    text: str
    tokens: tuple[SourceToken, ...]
    clauses: tuple[ClauseCandidate, ...]
    predicates: tuple[PredicateHeadCandidate, ...]
    coordinations: tuple[CoordinationCandidate, ...]

    def token(self, index: int) -> SourceToken:
        return self.tokens[index - 1]

    def clause_for_token(self, index: int) -> ClauseCandidate | None:
        for clause in self.clauses:
            if clause.span.start_index <= index <= clause.span.end_index:
                return clause
        return None


_STRONG_PREDICATE_POS = {"VERB", "PRED"}
_SECONDARY_PREDICATE_POS = {"INFN", "GRND", "ADJS", "PRTS"}
_SUBORDINATORS: dict[str, str | None] = {
    "что": None,
    "чтобы": "PURPOSE",
    "потому": "CAUSE",
    "поскольку": "CAUSE",
    "если": "CONDITION",
    "когда": "TIME",
    "где": "LOCATION",
    "куда": "LOCATION",
    "откуда": "SOURCE",
}

# Multi-word Russian clause connectives.  These are linguistic operators, not
# semantic actants.  The whole surface span is kept on the child clause so the
# parser can exclude it from entity candidates and attach the child situation to
# the parent with a finite canonical role.
_COMPOUND_SUBORDINATORS: dict[tuple[str, ...], str | None] = {
    ("после", "того", "как"): "TIME",
    ("до", "того", "как"): "TIME",
    ("перед", "тем", "как"): "TIME",
    ("с", "тех", "пор", "как"): "TIME",
    ("потому", "что"): "CAUSE",
    ("так", "как"): "CAUSE",
    ("для", "того", "чтобы"): "PURPOSE",
}
_RELATIVE_PREFIXES = ("котор",)
_CLAUSE_COORDINATORS = {"а", "но", "однако"}
_COORD_AND = {"и", "да"}
_COORD_OR = {"или", "либо"}
_HARD_BOUNDARY = {".", "!", "?", ";"}


class LinguisticCandidateBuilder:
    """Deterministic preprocessing for the adaptive parser.

    It deliberately does not decide semantic truth or canonical AH structure. It
    produces a conservative candidate graph: all plausible morphology analyses,
    predicate heads, clause windows and simple coordination groups. LLM probes are
    only needed when this graph leaves more than one semantically valid choice.
    """

    def __init__(self, morphology: Morphology) -> None:
        self.morphology = morphology

    def build(self, text: str) -> LinguisticCandidateGraph:
        tokens = self._tokens(text)
        predicates = self._predicate_heads(tokens)
        clauses = self._clauses(text, tokens, predicates)
        coordinations = self._coordinations(text, tokens, predicates)
        return LinguisticCandidateGraph(text, tokens, clauses, predicates, coordinations)

    def _tokens(self, text: str) -> tuple[SourceToken, ...]:
        result: list[SourceToken] = []
        for i, match in enumerate(re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE), start=1):
            word = match.group(0)
            try:
                analyses = self.morphology.analyze_all(word)
            except AttributeError:
                single = self.morphology.analyze(word)
                analyses = (() if single is None else (single,))
            result.append(SourceToken(i, word, match.start(), match.end(), analyses))
        return tuple(result)

    @staticmethod
    def _material_analyses(token: SourceToken) -> tuple[MorphInfo, ...]:
        """Morphology readings strong enough to drive structural candidates.

        Rare dictionary parses remain stored on SourceToken for later ambiguity
        handling, but they must not create a predicate/clause structure by
        themselves. With scored morphology, keep readings competitive with the
        best analysis; scoreless test morphologies preserve all readings.
        """
        if not token.analyses:
            return ()
        top = max((item.score for item in token.analyses), default=0.0)
        if top <= 0.0:
            return token.analyses
        floor = top * 0.30
        return tuple(item for item in token.analyses if item.score >= floor)

    @classmethod
    def _lemma_candidates(cls, token: SourceToken, poses: set[str]) -> tuple[str, ...]:
        values: list[str] = []
        for analysis in cls._material_analyses(token):
            if analysis.pos not in poses:
                continue
            if analysis.normal_form not in values:
                values.append(analysis.normal_form)
        return tuple(values)

    def _predicate_heads(self, tokens: tuple[SourceToken, ...]) -> tuple[PredicateHeadCandidate, ...]:
        result: list[PredicateHeadCandidate] = []
        for token in tokens:
            strong = self._lemma_candidates(token, _STRONG_PREDICATE_POS)
            secondary = self._lemma_candidates(token, _SECONDARY_PREDICATE_POS)
            if strong:
                result.append(PredicateHeadCandidate(token.index, 2, True, strong))
            elif secondary:
                finite = any(a.pos in {"ADJS", "PRTS"} for a in token.analyses)
                result.append(PredicateHeadCandidate(token.index, 1, finite, secondary))
        return tuple(result)

    @staticmethod
    def _span(text: str, tokens: tuple[SourceToken, ...], start: int, end: int) -> CandidateSpan:
        first = tokens[start - 1]
        last = tokens[end - 1]
        value = text[first.start:last.end]
        return CandidateSpan(start, end, value, EvidenceSpan(value, first.start, last.end))

    def _clauses(
        self,
        text: str,
        tokens: tuple[SourceToken, ...],
        predicates: tuple[PredicateHeadCandidate, ...],
    ) -> tuple[ClauseCandidate, ...]:
        if not tokens:
            return ()
        pred_positions = {p.token_index for p in predicates}
        finite_positions = {p.token_index for p in predicates if p.finite}
        boundaries = {1, len(tokens) + 1}

        def sentence_window(index: int) -> tuple[int, int]:
            left = 1
            right = len(tokens)
            for token in tokens:
                if token.index < index and token.text in {".", "!", "?", ";"}:
                    left = token.index + 1
                elif token.index > index and token.text in {".", "!", "?", ";"}:
                    right = token.index - 1
                    break
            return left, right

        def local_positions(index: int, positions: set[int]) -> tuple[int, ...]:
            left, right = sentence_window(index)
            return tuple(p for p in positions if left <= p <= right)

        def explicit_subject_before_right_predicate(index: int, right_predicate: int) -> bool:
            for i in range(index + 1, right_predicate):
                token = tokens[i - 1]
                if any(
                    item.case == "nomn" and item.pos in {"NOUN", "NPRO"}
                    for item in self._material_analyses(token)
                ):
                    return True
            return False

        # Find multi-word connectives over the word-token stream while allowing
        # punctuation inside the surface form ("после того, как").
        word_tokens = [t for t in tokens if re.search(r"\w", t.text)]
        compound_by_start: dict[int, tuple[int, str, str | None]] = {}
        compound_ranges: list[tuple[int, int]] = []
        for pattern, role_hint in _COMPOUND_SUBORDINATORS.items():
            width = len(pattern)
            for offset in range(0, len(word_tokens) - width + 1):
                window = word_tokens[offset:offset + width]
                if tuple(t.text.casefold() for t in window) != pattern:
                    continue
                first = window[0].index
                last = window[-1].index
                left, right = sentence_window(first)
                if not (left <= first <= last <= right):
                    continue
                # It is a clause connective only if it participates in a sentence
                # with at least two predicate frames.  Postposed connectives have a
                # predicate on both sides; fronted connectives ("После того как
                # A, B") have both predicates to the right and are licensed by the
                # comma that closes the subordinate clause.
                left_preds = [p for p in pred_positions if left <= p < first]
                right_preds = [p for p in pred_positions if last < p <= right]
                if left_preds:
                    if not right_preds:
                        continue
                else:
                    if first != left or len(right_preds) < 2:
                        continue
                    if not any(
                        token.text == "," and last < token.index < right
                        for token in tokens
                    ):
                        continue
                marker = "_".join(pattern)
                existing = compound_by_start.get(first)
                if existing is None or last > existing[0]:
                    compound_by_start[first] = (last, marker, role_hint)
                compound_ranges.append((first, last))
                boundaries.add(first)

        def inside_compound(index: int) -> bool:
            return any(start <= index <= end for start, end in compound_ranges)

        for token in tokens:
            if token.text in _HARD_BOUNDARY:
                boundaries.add(token.index + 1)
                continue

            # Punctuation and internal words belonging to a recognized compound
            # connective must not split that connective into a fake clause.
            if inside_compound(token.index):
                if token.index in compound_by_start:
                    continue
                # The connector's start boundary was already registered above.
                continue

            local_preds = local_positions(token.index, pred_positions)
            local_finite = local_positions(token.index, finite_positions)
            left_has = any(p < token.index for p in local_preds)
            right_has = any(p > token.index for p in local_preds)

            if token.text == ",":
                if left_has and right_has:
                    boundaries.add(token.index + 1)
                continue

            low = token.text.casefold()
            if low in _CLAUSE_COORDINATORS:
                if left_has and right_has:
                    boundaries.add(token.index)
                continue

            if low in _COORD_AND or low in _COORD_OR:
                left_finite = [p for p in local_finite if p < token.index]
                right_finite = [p for p in local_finite if p > token.index]
                if left_finite and right_finite:
                    right_predicate = min(right_finite)
                    if explicit_subject_before_right_predicate(token.index, right_predicate):
                        boundaries.add(token.index)
                continue

            if low in _SUBORDINATORS and any(p >= token.index for p in local_preds):
                if token.index > 1:
                    boundaries.add(token.index)
            elif low.startswith(_RELATIVE_PREFIXES) and any(p > token.index for p in local_preds):
                if token.index > 1:
                    boundaries.add(token.index)

        ordered = sorted(b for b in boundaries if 1 <= b <= len(tokens) + 1)
        spans: list[tuple[int, int]] = []
        for left, right in zip(ordered, ordered[1:]):
            start = left
            end = right - 1
            while start <= end and tokens[start - 1].text in {",", ";"}:
                start += 1
            while end >= start and tokens[end - 1].text in _HARD_BOUNDARY | {","}:
                end -= 1
            if start <= end:
                spans.append((start, end))
        if not spans:
            spans = [(1, len(tokens))]

        clauses: list[ClauseCandidate] = []
        for idx, (start, end) in enumerate(spans, start=1):
            heads = tuple(p for p in predicates if start <= p.token_index <= end)
            first_word_token = next(
                (tokens[i - 1] for i in range(start, end + 1) if re.search(r"\w", tokens[i - 1].text)),
                None,
            )
            first_word = first_word_token.text.casefold() if first_word_token is not None else ""
            marker = first_word or None
            role_hint = None
            parent = None
            connector_span = None
            relative = False

            compound = compound_by_start.get(start)
            if compound is not None:
                connector_end, marker, role_hint = compound
                connector_span = self._span(text, tokens, start, connector_end)
                if clauses:
                    parent = clauses[-1].clause_id
            elif first_word in _SUBORDINATORS:
                role_hint = _SUBORDINATORS.get(first_word)
                if clauses:
                    parent = clauses[-1].clause_id
                if first_word_token is not None:
                    connector_span = self._span(text, tokens, first_word_token.index, first_word_token.index)
            elif first_word.startswith(_RELATIVE_PREFIXES):
                relative = True
                if clauses:
                    parent = clauses[-1].clause_id
                if first_word_token is not None:
                    connector_span = self._span(text, tokens, first_word_token.index, first_word_token.index)

            clauses.append(
                ClauseCandidate(
                    clause_id=f"CL{idx}",
                    sentence_id=1 + sum(
                        1 for t in tokens if t.index < start and t.text in {".", "!", "?"}
                    ),
                    span=self._span(text, tokens, start, end),
                    predicate_heads=heads,
                    marker=marker,
                    parent_clause_id=parent,
                    parent_role_hint=role_hint,
                    connector_span=connector_span,
                    relative=relative,
                )
            )

        # A subordinate clause can precede its matrix clause: "если A, B",
        # "когда A, B", "поскольку A, B".  During the left-to-right pass there
        # is no previous clause to use as parent, so attach such a fronted child to
        # the immediately following clause in the same sentence.  This is a generic
        # clause-order correction driven by the already recognized semantic role,
        # not by a predicate-specific phrase rule.
        for index, clause in enumerate(tuple(clauses)):
            if (
                clause.parent_clause_id is not None
                or clause.parent_role_hint is None
                or clause.relative
                or index + 1 >= len(clauses)
            ):
                continue

            # For a fronted subordinate clause, attach to the first clause after
            # the comma that closes the subordinate region.  This matters when the
            # subordinate itself contains coordinated clauses: "Если A и B, C"
            # must attach CONDITION to C, not to B.
            closing_comma = next(
                (token.index for token in tokens
                 if clause.span.end_index < token.index
                 and token.text == ","
                 and sentence_window(token.index)[0] <= clause.span.start_index),
                None,
            )
            following = None
            for candidate in clauses[index + 1:]:
                if candidate.sentence_id != clause.sentence_id:
                    break
                if closing_comma is None or candidate.span.start_index > closing_comma:
                    following = candidate
                    break
            if following is None:
                following = clauses[index + 1]
                if following.sentence_id != clause.sentence_id:
                    continue
            clauses[index] = replace(clause, parent_clause_id=following.clause_id)

        return tuple(clauses)

    def _coordinations(
        self,
        text: str,
        tokens: tuple[SourceToken, ...],
        predicates: tuple[PredicateHeadCandidate, ...],
    ) -> tuple[CoordinationCandidate, ...]:
        raw: list[CoordinationCandidate] = []
        predicate_positions = {item.token_index for item in predicates}
        for token in tokens:
            low = token.text.casefold()
            if low not in _COORD_AND and low not in _COORD_OR:
                continue
            left = self._nearest_word(tokens, token.index, -1)
            right = self._nearest_word(tokens, token.index, +1)
            if left is None or right is None:
                continue

            # Actant coordination and predicate coordination are different
            # structures.  A weak morphological analyser can expose secondary POS
            # readings for a finite verb, which used to make spans such as
            # ``document and write`` look like a nominal coordination.  Never build
            # an actant CoordinationCandidate across a predicate head.  Predicate
            # coordination is handled at frame level by the parser.
            if left.index in predicate_positions or right.index in predicate_positions:
                continue
            if not self._morph_compatible(left, right):
                continue
            members: list[SourceToken] = [left, right]
            # Include comma-separated compatible members immediately before the
            # explicit coordinator: A, B and C / A, B or C.
            cursor = left.index - 1
            while cursor >= 2 and tokens[cursor - 1].text == ",":
                previous = self._nearest_word(tokens, cursor, -1)
                if previous is None or not self._morph_compatible(left, previous):
                    break
                members.insert(0, previous)
                cursor = previous.index - 1
            operator = CoordinationKind.AND if low in _COORD_AND else CoordinationKind.OR
            member_spans = tuple(self._span(text, tokens, m.index, m.index) for m in members)
            raw.append(
                CoordinationCandidate(
                    operator,
                    self._span(text, tokens, members[0].index, members[-1].index),
                    member_spans,
                )
            )

        # Merge overlapping chains with the same operator: A or B or C becomes one
        # OR candidate with three ordered members instead of two competing pairs.
        merged: list[CoordinationCandidate] = []
        for item in sorted(raw, key=lambda x: (x.span.start_index, x.span.end_index)):
            if merged and merged[-1].operator == item.operator and item.span.start_index <= merged[-1].span.end_index:
                previous = merged.pop()
                members = list(previous.member_spans)
                seen = {(m.start_index, m.end_index) for m in members}
                for member in item.member_spans:
                    key = (member.start_index, member.end_index)
                    if key not in seen:
                        seen.add(key)
                        members.append(member)
                members.sort(key=lambda m: m.start_index)
                merged.append(
                    CoordinationCandidate(
                        item.operator,
                        self._span(text, tokens, members[0].start_index, members[-1].end_index),
                        tuple(members),
                    )
                )
            else:
                merged.append(item)
        return tuple(merged)

    @staticmethod
    def _nearest_word(tokens: tuple[SourceToken, ...], index: int, direction: int) -> SourceToken | None:
        cursor = index + direction
        while 1 <= cursor <= len(tokens):
            token = tokens[cursor - 1]
            if re.search(r"\w", token.text):
                return token
            if token.text in _HARD_BOUNDARY | {","}:
                return None
            cursor += direction
        return None

    @staticmethod
    def _morph_compatible(left: SourceToken, right: SourceToken) -> bool:
        left_pos = {a.pos for a in left.analyses if a.pos}
        right_pos = {a.pos for a in right.analyses if a.pos}
        return bool(left_pos & right_pos)
