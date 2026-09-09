from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re

from .contracts import EvidenceSpan
from .lexical_recovery import LexicalRecovery, TokenCandidate
from .morphology import MorphInfo, Morphology, stable_transitivity


class CoordinationKind(str, Enum):
    AND = "AND"
    OR = "OR"


class FrameDependencyKind(str, Enum):
    """Purely runtime orientation between proposition frames.

    The kind records why the orientation is structurally available; it is not an
    AH relation and never assigns an actant role.
    """

    SUBORDINATE = "SUBORDINATE"
    NONFINITE = "NONFINITE"
    QUOTED = "QUOTED"


class EllipsisKind(str, Enum):
    """Runtime-only reconstruction mode for an overtly incomplete peer clause.

    The label describes source syntax/discourse only.  It is never persisted as
    a canonical AH relation or used as a truth marker.
    """

    FRAME = "FRAME"
    PROPOSITION_NEGATION = "PROPOSITION_NEGATION"
    PROPOSITION_CONFIRMATION = "PROPOSITION_CONFIRMATION"


@dataclass(frozen=True, slots=True)
class SourceToken:
    index: int
    text: str
    start: int
    end: int
    analyses: tuple[MorphInfo, ...] = ()
    raw_text: str | None = None
    recovery: TokenCandidate | None = None

    @property
    def provenance_text(self) -> str:
        return self.raw_text if self.raw_text is not None else self.text

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
    # Runtime structural cue: this head is a nominal predicate licensed by a
    # copular shell (e.g. ``Москва — город``). It is not an AH type and does
    # not make arbitrary nouns predicates.
    nominal_predicative: bool = False


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
    quoted: bool = False
    implicit_copula: bool = False
    ellipsis_kind: EllipsisKind | None = None
    ellipsis_source_clause_id: str | None = None


@dataclass(frozen=True, slots=True)
class FrameDependencyCandidate:
    parent_token_index: int
    child_token_index: int
    kind: FrameDependencyKind
    parent_clause_id: str
    child_clause_id: str

    def __post_init__(self) -> None:
        if self.parent_token_index == self.child_token_index:
            raise ValueError("frame dependency cannot be self-referential")


@dataclass(frozen=True, slots=True)
class ClauseFrameGraph:
    """Dependency-oriented runtime view of predicate frames.

    Source order is intentionally absent from dependency semantics. Predicate
    coordination groups live here as structural peer sets; they do not themselves
    assert that any particular actant is shared.
    """

    dependencies: tuple[FrameDependencyCandidate, ...] = ()
    coordinations: tuple["PredicateCoordinationCandidate", ...] = ()

    def parent_of(self, token_index: int) -> int | None:
        parents = {
            edge.parent_token_index
            for edge in self.dependencies
            if edge.child_token_index == token_index
        }
        return next(iter(parents)) if len(parents) == 1 else None

    def is_embedded(self, token_index: int) -> bool:
        return any(edge.child_token_index == token_index for edge in self.dependencies)

    def roots(self, token_indices: set[int] | None = None) -> tuple[int, ...]:
        children = {edge.child_token_index for edge in self.dependencies}
        values = (
            token_indices
            if token_indices is not None
            else ({edge.parent_token_index for edge in self.dependencies} | children)
        )
        return tuple(sorted(index for index in values if index not in children))


@dataclass(frozen=True, slots=True)
class CoordinationCandidate:
    operator: CoordinationKind
    span: CandidateSpan
    member_spans: tuple[CandidateSpan, ...]


@dataclass(frozen=True, slots=True)
class PredicateCoordinationCandidate:
    """Runtime coordination group over predicate frames.

    This object records only the surface coordination skeleton.  It does not say
    that any particular actant is shared and it never assigns an AH role.  Shared
    arguments are resolved later against the already-built semantic frames.
    """

    operator: CoordinationKind
    clause_id: str
    member_token_indices: tuple[int, ...]
    coordinator_token_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.member_token_indices) < 2:
            raise ValueError("predicate coordination requires at least two members")
        if len(set(self.member_token_indices)) != len(self.member_token_indices):
            raise ValueError("predicate coordination members must be unique")
        if tuple(sorted(self.member_token_indices)) != self.member_token_indices:
            raise ValueError("predicate coordination members must be source-ordered")


@dataclass(frozen=True, slots=True)
class LinguisticCandidateGraph:
    text: str
    tokens: tuple[SourceToken, ...]
    clauses: tuple[ClauseCandidate, ...]
    predicates: tuple[PredicateHeadCandidate, ...]
    coordinations: tuple[CoordinationCandidate, ...]
    frame_graph: ClauseFrameGraph = ClauseFrameGraph()

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
    # Surface markers establish only a subordinate edge.  They do not assign an
    # AH actant role: ``чтобы`` may introduce content or purpose; ``где/когда``
    # may introduce embedded content or an adjunct.  Semantic relation is chosen
    # only after both predicate frames exist.
    "что": None,
    "чтобы": None,
    "потому": None,
    "поскольку": None,
    "если": None,
    "когда": None,
    "где": None,
    "куда": None,
    "откуда": None,
}

# Multi-word Russian clause connectives.  These are linguistic operators, not
# semantic actants.  The whole surface span is kept on the child clause so the
# parser can exclude it from entity candidates and attach the child situation to
# the parent with a finite canonical role.
_COMPOUND_SUBORDINATORS: dict[tuple[str, ...], str | None] = {
    ("после", "того", "как"): None,
    ("до", "того", "как"): None,
    ("перед", "тем", "как"): None,
    ("с", "тех", "пор", "как"): None,
    ("потому", "что"): None,
    ("так", "как"): None,
    ("для", "того", "чтобы"): None,
}
_SUBORDINATOR_MARKERS = frozenset(_SUBORDINATORS) | frozenset("_".join(parts) for parts in _COMPOUND_SUBORDINATORS)
_RELATIVE_PREFIXES = ("котор",)
_RELATIVE_ADVERBS = {"где", "куда", "откуда", "когда"}
_CLAUSE_COORDINATORS = {"а", "но", "однако"}
_COORD_AND = {"и", "да"}
_COORD_OR = {"или", "либо"}
_HARD_BOUNDARY = {".", "!", "?", ";"}
_OPEN_QUOTES = {"«", "“", "„", "\""}


class LinguisticCandidateBuilder:
    """Deterministic preprocessing for the adaptive parser.

    It deliberately does not decide semantic truth or canonical AH structure. It
    produces a conservative candidate graph: all plausible morphology analyses,
    predicate heads, clause windows and simple coordination groups. LLM probes are
    only needed when this graph leaves more than one semantically valid choice.
    """

    def __init__(
        self,
        morphology: Morphology,
        *,
        lexical_recovery: LexicalRecovery | None = None,
    ) -> None:
        self.morphology = morphology
        self.lexical_recovery = lexical_recovery

    def build(self, text: str) -> LinguisticCandidateGraph:
        tokens = self._tokens(text)
        graph = self._build_from_tokens(text, tokens)
        if self.lexical_recovery is None:
            self._emit_candidate_diagnostics(graph, lexical_pass=None)
            return graph

        # Bounded recurrent lexical recovery.  A first safe correction can expose a
        # predicate/frame that makes another OOV resolvable on the next pass. Stable
        # EXACT/CORRECTED/UNKNOWN decisions remain monotonic inside LexicalRecovery;
        # only AMBIGUOUS tokens are reconsidered.  Four passes bound runtime while
        # covering the short dependency chains expected from ordinary typing noise.
        for _pass in range(4):
            decisions = self.lexical_recovery.recover(text, tokens, graph)
            self._emit_lexical_diagnostics(decisions, lexical_pass=_pass + 1)
            by_index = {item.token_index: item for item in decisions}
            recovered: list[SourceToken] = []
            changed = False
            for token in tokens:
                decision = by_index.get(token.index)
                normalized = (
                    token.text
                    if decision is None or decision.normalized_text is None
                    else decision.normalized_text
                )
                changed = changed or normalized != token.text
                try:
                    analyses = self.morphology.analyze_all(normalized)
                except AttributeError:
                    single = self.morphology.analyze(normalized)
                    analyses = () if single is None else (single,)
                recovered.append(
                    replace(
                        token,
                        text=normalized,
                        analyses=tuple(analyses),
                        raw_text=token.provenance_text,
                        recovery=decision,
                    )
                )
            tokens = tuple(recovered)
            graph = self._build_from_tokens(text, tokens)
            if not changed:
                break
        self._emit_candidate_diagnostics(graph, lexical_pass=_pass + 1)
        return graph

    @staticmethod
    def _emit_lexical_diagnostics(decisions, *, lexical_pass: int) -> None:
        from ah.diagnostics.session_log import emit

        emit(
            "pipeline_lexical_recovery",
            pass_index=lexical_pass,
            tokens=[
                {
                    "index": item.token_index,
                    "raw": item.raw_text,
                    "normalized": item.normalized_text,
                    "status": item.status.value,
                    "alternatives": list(item.alternatives),
                    "confidence": item.confidence,
                    "reason": item.reason,
                }
                for item in decisions
            ],
        )

    @staticmethod
    def _emit_candidate_diagnostics(graph: LinguisticCandidateGraph, *, lexical_pass: int | None) -> None:
        from ah.diagnostics.session_log import emit

        emit(
            "pipeline_candidates",
            lexical_pass=lexical_pass,
            tokens=[
                {
                    "index": token.index,
                    "raw": token.provenance_text,
                    "text": token.text,
                    "recovery": None if token.recovery is None else token.recovery.status.value,
                }
                for token in graph.tokens
            ],
            predicates=[
                {
                    "token_index": item.token_index,
                    "lemma": getattr(item, "lemma", None),
                }
                for item in graph.predicates
            ],
            clauses=[
                {
                    "clause_id": item.clause_id,
                    "start": item.span.start_index,
                    "end": item.span.end_index,
                    "ellipsis": None if item.ellipsis_kind is None else item.ellipsis_kind.value,
                }
                for item in graph.clauses
            ],
            coordination_count=len(graph.coordinations),
            frame_dependency_count=len(graph.frame_graph.dependencies),
        )

    def _build_from_tokens(
        self, text: str, tokens: tuple[SourceToken, ...]
    ) -> LinguisticCandidateGraph:
        predicates = self._predicate_heads(tokens)
        clauses = self._clauses(text, tokens, predicates)
        # A proposition-level ellipsis marker such as Russian ``нет`` may have a
        # legitimate dictionary PRED reading.  Once clause analysis has proved
        # that the token belongs to ``..., а X — нет``, keep its morphology but
        # remove it from the runtime predicate work queue; otherwise the adaptive
        # parser would parse the rejection marker as an independent lexical fact
        # before ellipsis completion runs.
        # Once a coordinated tail is structurally licensed as ellipsis, *none* of
        # the lexical predicate candidates inside that tail may re-enter the main
        # predicate work queue.  This is broader than the special ``нет`` case:
        # zero-predicate tails with a dash often make the final noun look like a
        # nominal predicate to morphology (``Мария — журнал``, ``журнал — на полке``).
        # Parsing that noun first prevents frame completion from ever running and
        # produces a spurious canonical fact.  Clause analysis is the stronger
        # structural result here: the tail is a peer frame whose predicate must be
        # recovered from its antecedent, not an independent nominal predication.
        ellipsis_owned_predicate_indices = {
            item.token_index
            for clause in clauses
            if clause.ellipsis_kind is not None
            for item in predicates
            if clause.span.start_index <= item.token_index <= clause.span.end_index
        }
        if ellipsis_owned_predicate_indices:
            predicates = tuple(
                item for item in predicates
                if item.token_index not in ellipsis_owned_predicate_indices
            )
        coordinations = self._coordinations(text, tokens, predicates)
        predicate_coordinations = self._predicate_coordinations(tokens, clauses)
        frame_graph = self._frame_graph(
            tokens, clauses, predicates, predicate_coordinations
        )
        return LinguisticCandidateGraph(
            text=text,
            tokens=tokens,
            clauses=clauses,
            predicates=predicates,
            coordinations=coordinations,
            frame_graph=frame_graph,
        )

    def _tokens(self, text: str) -> tuple[SourceToken, ...]:
        result: list[SourceToken] = []
        for i, match in enumerate(re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE), start=1):
            word = match.group(0)
            try:
                analyses = self.morphology.analyze_all(word)
            except AttributeError:
                single = self.morphology.analyze(word)
                analyses = (() if single is None else (single,))
            result.append(
                SourceToken(
                    i, word, match.start(), match.end(), analyses,
                    raw_text=word,
                )
            )
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

        def governed_oblique_nominal(index: int) -> bool:
            """Return True when a weak predicate reading sits inside a PP.

            Russian dictionary morphology can expose an oblique common noun as a
            short adjective / nominative proper-name homograph.  In ``с крючков``
            that weak ADJS reading must not become a predicate head merely because
            ``крючковый`` exists in the dictionary.  The source preposition plus an
            oblique nominal reading is stronger local syntax.

            We scan left only across nominal modifiers.  Crossing punctuation, a
            coordinator, another lexical predicate, or an ordinary content word
            aborts the PP cue, so this cannot suppress an unrelated predicative
            adjective elsewhere in the clause.
            """
            token = tokens[index - 1]
            material = self._material_analyses(token)
            if not any(
                item.pos in {"NOUN", "NPRO"} and item.case not in {None, "nomn"}
                for item in material
            ):
                return False
            cursor = index - 1
            while cursor >= 1:
                left = tokens[cursor - 1]
                if left.text in _HARD_BOUNDARY or left.text.casefold() in (_COORD_AND | _COORD_OR):
                    return False
                left_material = self._material_analyses(left)
                if any(item.pos == "PREP" for item in left_material):
                    return True
                if not left_material:
                    return False
                if any(item.pos in {"ADJF", "PRTF", "NUMR"} for item in left_material):
                    cursor -= 1
                    continue
                return False
            return False

        for token in tokens:
            strong = self._lemma_candidates(token, _STRONG_PREDICATE_POS)
            secondary = self._lemma_candidates(token, _SECONDARY_PREDICATE_POS)
            if strong:
                result.append(PredicateHeadCandidate(token.index, 2, True, strong))
            elif secondary and not governed_oblique_nominal(token.index):
                finite = any(a.pos in {"ADJS", "PRTS"} for a in token.analyses)
                result.append(PredicateHeadCandidate(token.index, 1, finite, secondary))

        # Dictionary morphology may expose a surface form simultaneously as a
        # non-finite predicate and as a nominative noun.  A classic Russian case
        # is a GRND/NOUN homograph at the beginning of an ordinary finite clause.
        # Treating both readings as independent predicate heads splits one clause
        # into two propositions before any semantic probe can repair it.
        #
        # Suppress only the formally dominated reading: a weak non-finite head is
        # removed when the *same token* has a material nominative nominal reading,
        # the nearest following strong finite predicate is in the same punctuation
        # segment, and that nominal reading agrees with the finite predicate.  A
        # comma/coordinator keeps genuine gerunds/infinitives alive (e.g. a
        # detached non-finite clause).  This is morphology + clause structure, not
        # a lexical exception and not a semantic role decision.
        by_index = {head.token_index: head for head in result}
        coordinators = {"и", "или", "либо", "а", "но", "однако"}
        hard_separators = {",", ";", ".", "!", "?", ":"}

        def agreeing_nominal_with(head: PredicateHeadCandidate, token: SourceToken) -> bool:
            nominal = [
                item for item in self._material_analyses(token)
                if item.pos in {"NOUN", "NPRO"} and item.case == "nomn"
            ]
            if not nominal:
                return False
            predicate_token = tokens[head.token_index - 1]
            predicates = [
                item for item in self._material_analyses(predicate_token)
                if item.pos == "VERB"
            ]
            if not predicates:
                return False

            n_numbers = {item.number for item in nominal if item.number}
            p_numbers = {item.number for item in predicates if item.number}
            if n_numbers and p_numbers and n_numbers.isdisjoint(p_numbers):
                return False

            past_singular = [
                item for item in predicates
                if item.number == "sing" and "past" in item.grammemes and item.gender
            ]
            if past_singular:
                n_genders = {item.gender for item in nominal if item.gender}
                p_genders = {item.gender for item in past_singular if item.gender}
                if n_genders and p_genders and n_genders.isdisjoint(p_genders):
                    return False
            return True

        suppressed: set[int] = set()
        finite_heads = [head for head in result if head.finite and head.strength >= 2]
        for head in result:
            if head.finite or head.strength >= 2:
                continue
            token = tokens[head.token_index - 1]
            if not any(
                item.pos in {"NOUN", "NPRO"} and item.case == "nomn"
                for item in self._material_analyses(token)
            ):
                continue
            following = [item for item in finite_heads if item.token_index > head.token_index]
            if not following:
                continue
            finite = min(following, key=lambda item: item.token_index)
            between = tokens[head.token_index:finite.token_index - 1]
            if any(
                item.text in hard_separators or item.text.casefold() in coordinators
                for item in between
            ):
                continue
            # Another predicate candidate between the two heads means the weak
            # reading may participate in a genuine predicate chain; do not erase it.
            if any(
                index in by_index
                for index in range(head.token_index + 1, finite.token_index)
            ):
                continue
            if agreeing_nominal_with(finite, token):
                suppressed.add(head.token_index)

        return tuple(head for head in result if head.token_index not in suppressed)

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

        def clause_ends_in_nominal(clause: ClauseCandidate) -> bool:
            for index in range(clause.span.end_index, clause.span.start_index - 1, -1):
                token = tokens[index - 1]
                if not re.search(r"\w", token.text):
                    continue
                return any(
                    info.pos in {"NOUN", "NPRO"}
                    for info in self._material_analyses(token)
                )
            return False

        def looks_like_zero_copula(start: int, end: int) -> bool:
            """Detect only the structural shell of an omitted present-tense copula.

            This does not decide SUBJECT/STATE.  It merely says that a clause with
            no overt predicate has enough nominal/predicative material to license
            an implicit BE frame whose roles will be resolved later.
            """
            material = [
                token for token in tokens
                if start <= token.index <= end and re.search(r"\w", token.text)
            ]
            nominatives = [
                token for token in material
                if any(
                    info.case == "nomn" and info.pos in {"NOUN", "NPRO"}
                    for info in self._material_analyses(token)
                )
            ]
            descriptions = [
                token for token in material
                if any(
                    info.pos in {"ADJF", "ADJS", "PRTS", "PRTF", "PRED"}
                    for info in self._material_analyses(token)
                )
            ]
            # Ivan doctor / Ivan — doctor, or Ivan smart.  Two nominatives are
            # enough for the nominal-predicate shell; their semantic direction is
            # deliberately left unresolved.
            return len(nominatives) >= 2 or (len(nominatives) >= 1 and bool(descriptions))

        # Find multi-word connectives over the word-token stream while allowing
        # punctuation inside the surface form ("после того, как").
        word_tokens = [t for t in tokens if re.search(r"\w", t.text)]
        compound_by_start: dict[int, tuple[int, str, str | None]] = {}
        compound_ranges: list[tuple[int, int]] = []
        quoted_starts: set[int] = set()
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

        def ellipsis_tail_candidate(index: int, coordinator: str) -> bool:
            """Recognize a conservative coordinated zero-predicate tail.

            Punctuation is supporting evidence, not a hard permission bit.  A
            missing comma before a clause coordinator may be ordinary input noise.
            Without that comma we require stronger independent structure: an overt
            finite frame on the left, no overt predicate on the right, a nominative
            participant candidate in the tail, and at least one additional content
            item.  ``и`` remains restricted to explicit proposition confirmation so
            ordinary NP coordination is not promoted to ellipsis.
            """
            left, right = sentence_window(index)
            left_finite = [p for p in finite_positions if left <= p < index]
            right_predicates = [p for p in pred_positions if index < p <= right]
            if not left_finite or right_predicates:
                return False
            tail = [
                token for token in tokens
                if index < token.index <= right and token.text not in _HARD_BOUNDARY
            ]
            words = [token for token in tail if re.search(r"\w", token.text)]
            if not words:
                return False
            lows = {token.text.casefold() for token in words}
            if coordinator == "и" and "тоже" not in lows:
                return False
            if lows & {"нет", "тоже"}:
                return True

            content = []
            for token in words:
                analyses = self._material_analyses(token)
                poses = {item.pos for item in analyses if item.pos is not None}
                if poses and poses.issubset({"PRCL", "CONJ", "INTJ", "PREP"}):
                    continue
                content.append(token)
            if len(content) < 2:
                return False
            has_comma = index > 1 and tokens[index - 2].text == ","
            if has_comma:
                return True
            return any(
                any(
                    item.pos in {"NOUN", "NPRO"} and item.case == "nomn"
                    for item in self._material_analyses(token)
                )
                for token in content
            )

        implicit_peer_starts: set[int] = set()

        def comma_ellipsis_tail_candidate(comma_index: int) -> bool:
            """Recognize an uncoordinated comma-separated ellipsis continuation.

            Russian parallel frames often omit the coordinator after the first
            member: ``Иван купил книгу, Мария — журнал, Пётр — газету``.  The
            old splitter only saw an ellipsis tail introduced by ``а``/``и`` and
            therefore kept the whole chain inside one clause.

            This remains deliberately conservative.  A candidate must have an
            overt finite frame somewhere to the left in the same sentence, no
            overt predicate in the comma-delimited segment itself, and at least
            two content-bearing surface items.  Plain NP enumerations containing
            an internal coordinator are rejected so ``книгу, журнал и газету``
            is not silently promoted to proposition coordination.
            """
            left, right = sentence_window(comma_index)
            if not any(left <= p < comma_index for p in finite_positions):
                return False

            segment_start = comma_index + 1
            while segment_start <= right and tokens[segment_start - 1].text in {",", ";"}:
                segment_start += 1
            if segment_start > right:
                return False

            segment_end = right
            for token in tokens:
                if token.index <= comma_index:
                    continue
                if token.text == "," or token.text in _HARD_BOUNDARY:
                    segment_end = token.index - 1
                    break
            if segment_start > segment_end:
                return False

            first_word = next(
                (
                    tokens[i - 1].text.casefold()
                    for i in range(segment_start, segment_end + 1)
                    if re.search(r"\w", tokens[i - 1].text)
                ),
                "",
            )
            # Coordinator-led tails are handled by ellipsis_tail_candidate(),
            # which has stricter rules for ``и`` and proposition markers.
            if first_word in (_CLAUSE_COORDINATORS | _COORD_AND | _COORD_OR):
                return False

            segment_predicates = [p for p in pred_positions if segment_start <= p <= segment_end]
            if any(tokens[p - 1].text.casefold() != "нет" for p in segment_predicates):
                return False
            if segment_predicates and not any(
                tokens[i - 1].text in {"—", "–", "-"}
                for i in range(segment_start, segment_end + 1)
            ):
                # Bare existential "денег нет" is an independent predicate.
                # A marker reading needs the parallel dash shell as well.
                return False

            words = [
                tokens[i - 1]
                for i in range(segment_start, segment_end + 1)
                if re.search(r"\w", tokens[i - 1].text)
            ]
            if not words:
                return False
            lows = {token.text.casefold() for token in words}
            if lows & {"нет", "тоже"}:
                return len(words) >= 2

            # Do not reinterpret a plain coordinated NP tail as a new frame.
            if any(token.text.casefold() in (_COORD_AND | _COORD_OR) for token in words):
                return False

            content = []
            for token in words:
                analyses = self._material_analyses(token)
                poses = {item.pos for item in analyses if item.pos is not None}
                if poses and poses.issubset({"PRCL", "CONJ", "INTJ", "PREP"}):
                    continue
                content.append(token)
            return len(content) >= 2

        def bare_dash_nominal_predication(start: int, end: int) -> bool:
            """Whether ``X — Y`` is structurally safer as zero-copula nominal.

            A dash is not itself an ellipsis marker.  In a running ellipsis chain
            ``Мария — в Казани`` or ``Мария — журнал`` can inherit a frame, while
            ``Слава — бродяга`` introduces a new nominal predicate.  Preserve the
            latter when the post-dash material is exactly one bare nominal whose
            material morphology is nominative-only.  Ambiguous NOM/ACC nouns such
            as ``журнал`` remain eligible as object replacements.
            """
            dash = next(
                (
                    i for i in range(start, end + 1)
                    if tokens[i - 1].text in {"-", "—", "–"}
                ),
                None,
            )
            if dash is None:
                return False
            after = [
                tokens[i - 1]
                for i in range(dash + 1, end + 1)
                if re.search(r"\w", tokens[i - 1].text)
            ]
            if after and after[0].text.casefold() == "это":
                # Explicit copular linker inside the same dash shell, not a
                # replacement actant of the preceding event.
                after = after[1:]
            if len(after) != 1:
                return False
            token = after[0]
            infos = tuple(
                item for item in self._material_analyses(token)
                if item.pos in {"NOUN", "NPRO"}
            )
            if not infos:
                return False
            cases = {item.case for item in infos if item.case}
            if not cases or "nomn" not in cases:
                return False

            left, _right = sentence_window(start)
            previous_finite = [p for p in finite_positions if left <= p < start]
            source_transitivity = (
                stable_transitivity(tokens[max(previous_finite) - 1].analyses)
                if previous_finite else None
            )

            # A transitive antecedent plus an overt object/oblique realization
            # *before* the dash is the characteristic inverted peer shell
            # ``..., а на полку журнал — Ольга``.  A nominative-only word after the
            # dash is then a perfectly ordinary postposed subject, not evidence for
            # a new copula.
            before_dash = [
                tokens[i - 1]
                for i in range(start, dash)
                if re.search(r"\w", tokens[i - 1].text)
            ]
            pre_dash_non_subject = any(
                any(info.pos in {"PREP", "ADVB"} for info in self._material_analyses(item))
                or any(
                    info.pos in {"NOUN", "NPRO", "ADJF", "PRTF", "NUMR"}
                    and info.case not in {None, "nomn"}
                    for info in self._material_analyses(item)
                )
                for item in before_dash
            )
            if source_transitivity == "tran" and pre_dash_non_subject:
                return False

            if cases <= {"nomn"}:
                return True

            # NOM/ACC syncretism alone is not enough to manufacture a copula in a
            # transitive ellipsis chain: ``Мария — журнал`` is exactly the ordinary
            # surface shape of SUBJECT+OBJECT frame completion.  Conversely an
            # intransitive antecedent cannot consume a bare accusative replacement,
            # so keeping the nominal-predication reading is conservative
            # (``журнал — подарок`` after a locative/intransitive frame).
            return source_transitivity != "tran"

        for token in tokens:
            if token.text in _HARD_BOUNDARY:
                boundaries.add(token.index + 1)
                continue

            # Direct speech has its own illocutionary domain.  A quote opened after
            # a colon is therefore a structural clause boundary even though the
            # quoted sentence belongs to the same outer orthographic sentence.
            if token.text in _OPEN_QUOTES and token.index > 1:
                previous = tokens[token.index - 2]
                local_preds = local_positions(token.index, pred_positions)
                if previous.text == ":" and any(p < token.index for p in local_preds) and any(
                    p > token.index for p in local_preds
                ):
                    boundaries.add(token.index)
                    quoted_starts.add(token.index)
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
                peer_tail = comma_ellipsis_tail_candidate(token.index)
                if (left_has and right_has) or peer_tail:
                    boundaries.add(token.index + 1)
                if peer_tail:
                    # A later overt predicate may already justify this boundary;
                    # it must not erase the local zero-predicate peer evidence.
                    implicit_peer_starts.add(token.index + 1)
                continue

            low = token.text.casefold()
            if low in _CLAUSE_COORDINATORS:
                if left_has and right_has:
                    boundaries.add(token.index)
                elif ellipsis_tail_candidate(token.index, low):
                    boundaries.add(token.index)
                continue

            if low in _COORD_AND or low in _COORD_OR:
                # A finite predicate in an earlier, already separated clause
                # cannot turn NP coordination here into two predicate clauses.
                # In "..., а Мария и Пётр — нет" the left verbal head belongs
                # to the antecedent; "Мария и Пётр" is one target participant.
                current_start = max(b for b in boundaries if b <= token.index)
                left_finite = [p for p in local_finite if current_start <= p < token.index]
                next_comma = next(
                    (item.index for item in tokens
                     if item.index > token.index and item.text == ","), len(tokens) + 1,
                )
                right_finite = [p for p in local_finite if token.index < p < next_comma]
                if left_finite and right_finite:
                    right_predicate = min(right_finite)
                    if explicit_subject_before_right_predicate(token.index, right_predicate):
                        boundaries.add(token.index)
                elif low == "и":
                    # Inside an already licensed zero-predicate peer, ``и`` first
                    # coordinates nominal members: ``..., а Мария и Пётр тоже``.
                    # Starting another proposition here would split one coordinated
                    # subject into two ellipsis frames.  A comma before ``и`` creates
                    # a fresh boundary at the coordinator itself and therefore still
                    # licenses ``Мария тоже, и Пётр тоже`` below.
                    owner_start = max(b for b in boundaries if b <= token.index)
                    owner_is_open_peer = (
                        owner_start < token.index
                        and not any(owner_start <= p < token.index for p in local_finite)
                        and (
                            owner_start in implicit_peer_starts
                            or tokens[owner_start - 1].text.casefold() in _CLAUSE_COORDINATORS
                        )
                    )
                    comma_before = token.index > 1 and tokens[token.index - 2].text == ","
                    if (
                        owner_is_open_peer
                        and comma_before
                        and ellipsis_tail_candidate(token.index, low)
                    ):
                        # A comma closes the current predicate-free peer; this
                        # coordinator starts another proposition. Without that
                        # boundary the same ``и`` remains NP coordination.
                        boundaries.add(token.index)
                        implicit_peer_starts.add(token.index)
                    elif not owner_is_open_peer and ellipsis_tail_candidate(token.index, low):
                        boundaries.add(token.index)
                continue

            if low in _SUBORDINATORS and any(p >= token.index for p in local_preds):
                if token.index > 1:
                    boundaries.add(token.index)
            elif low.startswith(_RELATIVE_PREFIXES) and any(p > token.index for p in local_preds):
                if token.index > 1:
                    boundaries.add(token.index)

        # Missing punctuation between parallel zero-predicate frames is common
        # noise, but an unrestricted scan for *any* nominative reading badly
        # over-segments Russian NOM/ACC syncretism (``письмо``, ``окно``) and even
        # weak productive-name parses.  Treat the dash as a shell cue and choose at
        # most one strongly nominative start for that shell.  Existing comma/
        # coordinator peer boundaries own their whole predicate-free segment and
        # are never split again here.
        def nominative_dominance(item: SourceToken) -> float:
            nominal = tuple(
                info for info in self._material_analyses(item)
                if info.pos in {"NOUN", "NPRO"} and info.case is not None
            )
            if not nominal:
                return 0.0
            cases = {info.case for info in nominal}
            if cases <= {"nomn"}:
                return 1.0
            positive = [max(0.0, info.score) for info in nominal]
            total = sum(positive)
            if total <= 0.0:
                return sum(info.case == "nomn" for info in nominal) / len(nominal)
            return sum(
                max(0.0, info.score) for info in nominal if info.case == "nomn"
            ) / total

        def has_non_subject_realization(start: int, dash: int, end: int) -> bool:
            for index in range(start, end + 1):
                if index == start:
                    continue
                item = tokens[index - 1]
                if item.text in {"—", "–", "-", ",", ";"}:
                    continue
                low = item.text.casefold()
                if low in (_CLAUSE_COORDINATORS | _COORD_AND | _COORD_OR):
                    continue
                material = self._material_analyses(item)
                if any(info.pos in {"PREP", "ADVB"} for info in material):
                    return True
                if any(
                    info.pos in {"NOUN", "NPRO", "ADJF", "PRTF", "NUMR"}
                    and info.case not in {None, "nomn"}
                    for info in material
                ):
                    return True
            return False

        for dash_token in tokens:
            if dash_token.text not in {"—", "–", "-"}:
                continue
            dash = dash_token.index
            left, right = sentence_window(dash)
            prior_finite = [p for p in finite_positions if left <= p < dash]
            if not prior_finite:
                continue

            owner_start = max(b for b in boundaries if b <= dash)
            if owner_start > left:
                owner_first = tokens[owner_start - 1].text.casefold()
                if (
                    owner_start in implicit_peer_starts
                    or owner_first in (_CLAUSE_COORDINATORS | _COORD_AND | _COORD_OR)
                    or not any(owner_start <= p < dash for p in finite_positions)
                ):
                    # A punctuation/coordinator boundary already licensed the
                    # predicate-free peer.  Splitting inside it caused nested
                    # frames such as ``а Анна`` + ``журнал — на полку``.
                    continue

            last_finite = max(prior_finite)
            candidates: list[tuple[float, int]] = []
            for index in range(last_finite + 1, dash):
                if index in boundaries:
                    continue
                item = tokens[index - 1]
                if not re.search(r"\w", item.text):
                    continue
                dominance = nominative_dominance(item)
                if dominance < 0.75:
                    continue
                if not has_non_subject_realization(index, dash, right):
                    continue
                candidates.append((dominance, index))
            if not candidates:
                continue

            # Exact/near-exact nominative evidence outranks syncretic candidates;
            # on a true tie the later candidate is safer because a post-verbal
            # source subject may precede the new peer in punctuation-free input.
            best_strength = max(score for score, _index in candidates)
            best_start = max(
                index for score, index in candidates
                if best_strength - score <= 0.05
            )
            boundaries.add(best_start)
            implicit_peer_starts.add(best_start)

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

        # Comma-separated zero-copula predications have no overt predicate heads,
        # so the ordinary predicate-driven comma splitter cannot see them. Split
        # only when every comma-delimited segment independently has a copular shell
        # ("Иван врач, Мария учитель").
        expanded_spans: list[tuple[int, int]] = []
        for start, end in spans:
            if any(start <= p <= end for p in pred_positions):
                expanded_spans.append((start, end))
                continue
            commas = [t.index for t in tokens if start <= t.index <= end and t.text == ","]
            if not commas:
                expanded_spans.append((start, end))
                continue
            pieces: list[tuple[int, int]] = []
            previous = start
            for comma in commas:
                pieces.append((previous, comma - 1))
                previous = comma + 1
            pieces.append((previous, end))
            cleaned = [
                (a, b) for a, b in pieces
                if a <= b and any(re.search(r"\w", tokens[i - 1].text) for i in range(a, b + 1))
            ]
            if len(cleaned) >= 2 and all(looks_like_zero_copula(a, b) for a, b in cleaned):
                expanded_spans.extend(cleaned)
            else:
                expanded_spans.append((start, end))
        spans = expanded_spans

        clauses: list[ClauseCandidate] = []
        for idx, (start, end) in enumerate(spans, start=1):
            heads = tuple(p for p in predicates if start <= p.token_index <= end)
            if not heads and not any(re.search(r"\w", tokens[i - 1].text) for i in range(start, end + 1)):
                continue
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
            quoted = start in quoted_starts
            implicit_copula = not heads and looks_like_zero_copula(start, end)
            ellipsis_kind: EllipsisKind | None = None
            ellipsis_source_clause_id: str | None = None
            sentence_id = 1 + sum(
                1 for t in tokens if t.index < start and t.text in {".", "!", "?"}
            )

            def previous_clause_same_sentence() -> ClauseCandidate | None:
                if clauses and clauses[-1].sentence_id == sentence_id:
                    return clauses[-1]
                return None

            previous = previous_clause_same_sentence()
            previous_peer = clauses[-1] if clauses else None
            marker_only_predicate = bool(heads) and all(
                tokens[head.token_index - 1].text.casefold() in {"нет"}
                for head in heads
            )
            if (
                marker_only_predicate
                and (first_word in {"а", "и"} or start in implicit_peer_starts)
                and previous is not None
                and (previous.predicate_heads or previous.ellipsis_kind is not None)
            ):
                # In ``..., а Мария — нет`` pymorphy correctly exposes ``нет``
                # as PRED, but in this coordination shell it is a proposition-
                # level rejection marker, not the lexical predicate of an
                # independent fact.  Keep the morphology on the token; only the
                # runtime frame view suppresses it as a predicate head.
                heads = ()
                implicit_copula = False
            previous_can_supply_frame = (
                previous_peer is not None
                and (
                    bool(previous_peer.predicate_heads)
                    or previous_peer.ellipsis_kind is not None
                )
            )
            dash_shell = any(
                tokens[i - 1].text in {"—", "–", "-"}
                for i in range(start, end + 1)
            )
            structurally_parallel = (
                first_word in {"а", "и"}
                or start in implicit_peer_starts
                # Strong punctuation can continue a parallel table/list without
                # repeating the coordinator.  A dash only licenses an ellipsis
                # candidate; semantic recovery later requires a bijective role-
                # realization match and otherwise keeps nominal predication.
                or dash_shell
            )
            if (
                not heads
                and structurally_parallel
                and previous_can_supply_frame
            ):
                tail_lows = {
                    tokens[i - 1].text.casefold()
                    for i in range(start, end + 1)
                    if re.search(r"\w", tokens[i - 1].text)
                }
                if "нет" in tail_lows:
                    ellipsis_kind = EllipsisKind.PROPOSITION_NEGATION
                elif "тоже" in tail_lows:
                    ellipsis_kind = EllipsisKind.PROPOSITION_CONFIRMATION
                else:
                    ellipsis_kind = EllipsisKind.FRAME
                assert previous_peer is not None
                ellipsis_source_clause_id = previous_peer.clause_id
                # The peer-frame interpretation owns this coordinated shell.  It
                # must not be reintroduced later as an unrelated zero-copula
                # predication.  When the shell is independently valid nominal
                # predication, retain that parse provisionally; ellipsis recovery
                # will replace it only after complete structural slot alignment.
                if not bare_dash_nominal_predication(start, end):
                    implicit_copula = False

            compound = compound_by_start.get(start)
            if quoted:
                marker = "QUOTE"
                previous = previous_clause_same_sentence()
                if previous is not None:
                    parent = previous.clause_id
            elif compound is not None:
                connector_end, marker, role_hint = compound
                connector_span = self._span(text, tokens, start, connector_end)
                previous = previous_clause_same_sentence()
                if previous is not None:
                    parent = previous.clause_id
            elif (
                first_word in _RELATIVE_ADVERBS
                and previous_clause_same_sentence() is not None
                and clause_ends_in_nominal(previous_clause_same_sentence())
            ):
                # Relative adverbs are structural relatives only when a preceding
                # nominal anchor is present: ``дом, где...`` / ``день, когда...``.
                # Without such an anchor (``я знаю, где...``) they remain ordinary
                # subordinate connectors and their parent relation is resolved later.
                relative = True
                previous = previous_clause_same_sentence()
                if previous is not None:
                    parent = previous.clause_id
                if first_word_token is not None:
                    connector_span = self._span(text, tokens, first_word_token.index, first_word_token.index)
            elif first_word in _SUBORDINATORS:
                role_hint = _SUBORDINATORS.get(first_word)
                previous = previous_clause_same_sentence()
                if previous is not None:
                    parent = previous.clause_id
                if first_word_token is not None:
                    connector_span = self._span(text, tokens, first_word_token.index, first_word_token.index)
            elif first_word.startswith(_RELATIVE_PREFIXES):
                relative = True
                previous = previous_clause_same_sentence()
                if previous is not None:
                    parent = previous.clause_id
                if first_word_token is not None:
                    connector_span = self._span(text, tokens, first_word_token.index, first_word_token.index)

            clauses.append(
                ClauseCandidate(
                    clause_id=f"CL{idx}",
                    sentence_id=sentence_id,
                    span=self._span(text, tokens, start, end),
                    predicate_heads=heads,
                    marker=marker,
                    parent_clause_id=parent,
                    parent_role_hint=role_hint,
                    connector_span=connector_span,
                    relative=relative,
                    quoted=quoted,
                    implicit_copula=implicit_copula,
                    ellipsis_kind=ellipsis_kind,
                    ellipsis_source_clause_id=ellipsis_source_clause_id,
                )
            )

        # A structural subordinate clause can precede its matrix clause: "если A, B",
        # "когда A, B", "поскольку A, B". During the left-to-right pass there
        # is no previous clause to use as parent, so orient it toward the following
        # matrix clause using only the recognized surface subordinator. No AH role
        # is assigned here.
        for index, clause in enumerate(tuple(clauses)):
            if (
                clause.parent_clause_id is not None
                or clause.marker not in _SUBORDINATOR_MARKERS
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

    def _predicate_coordinations(
        self,
        tokens: tuple[SourceToken, ...],
        clauses: tuple[ClauseCandidate, ...],
    ) -> tuple[PredicateCoordinationCandidate, ...]:
        """Build predicate coordination groups without assigning shared roles.

        Explicit coordinators connect neighbouring predicate heads.  A
        comma-only pair is absorbed into the following explicit group so
        ``A, B and C`` becomes one three-member group.  Strong punctuation and
        clause boundaries stop grouping.
        """
        groups: list[PredicateCoordinationCandidate] = []

        for clause in clauses:
            heads = sorted(head.token_index for head in clause.predicate_heads)
            if len(heads) < 2:
                continue

            pair_ops: list[CoordinationKind | None] = []
            pair_coordinators: list[tuple[int, ...]] = []
            comma_only: list[bool] = []
            for left, right in zip(heads, heads[1:]):
                between = [token for token in tokens if left < token.index < right]
                if any(token.text in _HARD_BOUNDARY for token in between):
                    pair_ops.append(None)
                    pair_coordinators.append(())
                    comma_only.append(False)
                    continue
                and_positions = tuple(
                    token.index for token in between
                    if token.text.casefold() in _COORD_AND
                )
                or_positions = tuple(
                    token.index for token in between
                    if token.text.casefold() in _COORD_OR
                )
                if and_positions and not or_positions:
                    pair_ops.append(CoordinationKind.AND)
                    pair_coordinators.append(and_positions)
                elif or_positions and not and_positions:
                    pair_ops.append(CoordinationKind.OR)
                    pair_coordinators.append(or_positions)
                else:
                    pair_ops.append(None)
                    pair_coordinators.append(())
                comma_only.append(
                    pair_ops[-1] is None
                    and bool(between)
                    and all(token.text == "," for token in between)
                )

            # In a list such as A, B and C the final explicit coordinator licenses
            # the immediately preceding comma-separated members of the same list.
            propagated = list(pair_ops)
            for index in range(len(propagated) - 1, -1, -1):
                if propagated[index] is not None:
                    continue
                if not comma_only[index]:
                    continue
                if index + 1 < len(propagated) and propagated[index + 1] is not None:
                    propagated[index] = propagated[index + 1]

            start = 0
            while start < len(propagated):
                operator = propagated[start]
                if operator is None:
                    start += 1
                    continue
                end = start
                while end + 1 < len(propagated) and propagated[end + 1] is operator:
                    end += 1
                members = tuple(heads[start : end + 2])
                coordinator_indices = tuple(
                    index
                    for pair_index in range(start, end + 1)
                    for index in pair_coordinators[pair_index]
                )
                groups.append(
                    PredicateCoordinationCandidate(
                        operator=operator,
                        clause_id=clause.clause_id,
                        member_token_indices=members,
                        coordinator_token_indices=coordinator_indices,
                    )
                )
                start = end + 1

        return tuple(groups)

    def _frame_graph(
        self,
        tokens: tuple[SourceToken, ...],
        clauses: tuple[ClauseCandidate, ...],
        predicates: tuple[PredicateHeadCandidate, ...],
        coordinations: tuple[PredicateCoordinationCandidate, ...] = (),
    ) -> ClauseFrameGraph:
        """Orient structural frame dependencies independently of token order."""
        by_clause = {clause.clause_id: clause for clause in clauses}
        head_to_clause = {
            head.token_index: clause
            for clause in clauses
            for head in clause.predicate_heads
        }
        edges: list[FrameDependencyCandidate] = []
        seen: set[tuple[int, int]] = set()

        def primary_head(clause: ClauseCandidate) -> PredicateHeadCandidate | None:
            if not clause.predicate_heads:
                return None
            finite = [head for head in clause.predicate_heads if head.finite]
            pool = finite or list(clause.predicate_heads)
            return max(pool, key=lambda head: (head.strength, -head.token_index))

        def add(parent: PredicateHeadCandidate, child: PredicateHeadCandidate, kind: FrameDependencyKind) -> None:
            key = (parent.token_index, child.token_index)
            if parent.token_index == child.token_index or key in seen:
                return
            parent_clause = head_to_clause.get(parent.token_index)
            child_clause = head_to_clause.get(child.token_index)
            if parent_clause is None or child_clause is None:
                return
            seen.add(key)
            edges.append(
                FrameDependencyCandidate(
                    parent_token_index=parent.token_index,
                    child_token_index=child.token_index,
                    kind=kind,
                    parent_clause_id=parent_clause.clause_id,
                    child_clause_id=child_clause.clause_id,
                )
            )

        # Explicit clause parentage (subordination / quotation) orients matrix and
        # embedded propositions, but does not decide their semantic AH relation.
        for clause in clauses:
            if clause.parent_clause_id is None:
                continue
            parent_clause = by_clause.get(clause.parent_clause_id)
            if parent_clause is None:
                continue
            parent = primary_head(parent_clause)
            child = primary_head(clause)
            if parent is not None and child is not None:
                add(
                    parent, child,
                    FrameDependencyKind.QUOTED if clause.quoted else FrameDependencyKind.SUBORDINATE,
                )

        # Non-finite hierarchy follows local predicate dependency, not a blanket
        # "nearest finite" rule.  A non-coordinated infinitive may itself govern a
        # later infinitive (``хочет попросить Петра прийти`` => WANT->ASK->COME).
        # Members of one predicate coordination group remain siblings
        # (``хочет купить и прочитать`` => WANT->{BUY,READ}).  If a non-finite
        # predicate is fronted and has no preceding governor, prefer the nearest
        # following finite matrix frame (``Улыбаясь, Иван вошёл`` => ENTER->SMILE).
        finite_heads = [head for head in predicates if head.finite]
        coord_members_by_head: dict[int, frozenset[int]] = {}
        for group in coordinations:
            members = frozenset(group.member_token_indices)
            for member in members:
                coord_members_by_head[member] = members

        for child in (head for head in predicates if not head.finite):
            child_clause = head_to_clause.get(child.token_index)
            if child_clause is None:
                continue
            siblings = coord_members_by_head.get(child.token_index, frozenset({child.token_index}))
            local_heads = [
                head for head in child_clause.predicate_heads
                if head.token_index not in siblings
            ]
            preceding = [head for head in local_heads if head.token_index < child.token_index]
            parent: PredicateHeadCandidate | None = None
            if preceding:
                parent = max(preceding, key=lambda head: head.token_index)
            else:
                following_finite = [
                    head for head in local_heads
                    if head.finite and head.token_index > child.token_index
                ]
                if following_finite:
                    parent = min(following_finite, key=lambda head: head.token_index)

            if parent is None:
                sentence_finite = [
                    head for head in finite_heads
                    if head.token_index not in siblings
                    and (parent_clause := head_to_clause.get(head.token_index)) is not None
                    and parent_clause.sentence_id == child_clause.sentence_id
                ]
                if sentence_finite:
                    parent = min(
                        sentence_finite,
                        key=lambda head: (abs(head.token_index - child.token_index), head.token_index),
                    )
            if parent is not None:
                add(parent, child, FrameDependencyKind.NONFINITE)

        return ClauseFrameGraph(tuple(edges), coordinations)

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
