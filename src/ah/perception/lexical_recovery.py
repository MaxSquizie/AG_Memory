from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from math import sqrt
from typing import Protocol, Sequence, TYPE_CHECKING
import re

from .morphology import MorphInfo, Morphology, material_analyses, stable_transitivity

if TYPE_CHECKING:  # pragma: no cover - imports are only for static checking
    from .linguistic_candidates import LinguisticCandidateGraph, SourceToken


class LexicalRecoveryStatus(str, Enum):
    """Runtime-only outcome for one source token."""

    EXACT = "EXACT"
    CORRECTED_HIGH_CONFIDENCE = "CORRECTED_HIGH_CONFIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN_TOKEN = "UNKNOWN_TOKEN"


@dataclass(frozen=True, slots=True)
class TokenCandidate:
    """A normalized token handed to the existing formalization pipeline.

    ``raw_text`` and offsets remain provenance.  Only ``normalized_text`` may be
    consumed by morphology/semantics.  No field is an AH element and this object
    never authorizes a canonical write.
    """

    token_index: int
    raw_text: str
    normalized_text: str | None
    status: LexicalRecoveryStatus
    alternatives: tuple[str, ...] = ()
    confidence: float | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.token_index <= 0:
            raise ValueError("TokenCandidate.token_index must be positive")
        if not self.raw_text:
            raise ValueError("TokenCandidate.raw_text must be non-empty")
        if self.status in {
            LexicalRecoveryStatus.EXACT,
            LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE,
            LexicalRecoveryStatus.UNKNOWN_TOKEN,
        } and not self.normalized_text:
            raise ValueError(f"{self.status.value} requires normalized_text")
        if self.status is LexicalRecoveryStatus.AMBIGUOUS and self.normalized_text is not None:
            raise ValueError("AMBIGUOUS must not select normalized_text")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("TokenCandidate.confidence must be in [0, 1]")


class SemanticCandidateReranker(Protocol):
    """Optional local vector scorer; it is not a generative language model."""

    def rank(self, context: str, candidates: tuple[str, ...]) -> dict[str, float]: ...


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class EmbeddingSemanticReranker:
    """Cosine reranking for the small shortlist left by deterministic filters."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = sqrt(sum(value * value for value in left))
        right_norm = sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)

    def rank(self, context: str, candidates: tuple[str, ...]) -> dict[str, float]:
        if not context.strip() or len(candidates) < 2:
            return {}
        vectors = self.provider.embed_texts((context, *candidates))
        if len(vectors) != len(candidates) + 1:
            return {}
        anchor = vectors[0]
        return {
            candidate: self._cosine(anchor, vector)
            for candidate, vector in zip(candidates, vectors[1:])
        }


_CYRILLIC_WORD = re.compile(r"^[А-Яа-яЁё-]+$")
_WORD_PART = re.compile(r"[А-Яа-яЁё]+")


# Surface-case government for common Russian prepositions.  This is a grammar
# constraint only: it narrows candidate word forms, never assigns an AH role.
# Ambiguous prepositions intentionally expose every ordinary governed case.
_PREPOSITION_CASES: dict[str, frozenset[str]] = {
    "без": frozenset({"gent", "gen1", "gen2"}),
    "близ": frozenset({"gent", "gen1", "gen2"}),
    "вдоль": frozenset({"gent", "gen1", "gen2"}),
    "вместо": frozenset({"gent", "gen1", "gen2"}),
    "вне": frozenset({"gent", "gen1", "gen2"}),
    "внутри": frozenset({"gent", "gen1", "gen2"}),
    "возле": frozenset({"gent", "gen1", "gen2"}),
    "вокруг": frozenset({"gent", "gen1", "gen2"}),
    "для": frozenset({"gent", "gen1", "gen2"}),
    "до": frozenset({"gent", "gen1", "gen2"}),
    "из": frozenset({"gent", "gen1", "gen2"}),
    "из-за": frozenset({"gent", "gen1", "gen2"}),
    "из-под": frozenset({"gent", "gen1", "gen2"}),
    "кроме": frozenset({"gent", "gen1", "gen2"}),
    "около": frozenset({"gent", "gen1", "gen2"}),
    "от": frozenset({"gent", "gen1", "gen2"}),
    "после": frozenset({"gent", "gen1", "gen2"}),
    "против": frozenset({"gent", "gen1", "gen2"}),
    "ради": frozenset({"gent", "gen1", "gen2"}),
    "среди": frozenset({"gent", "gen1", "gen2"}),
    "у": frozenset({"gent", "gen1", "gen2"}),
    "к": frozenset({"datv"}),
    "ко": frozenset({"datv"}),
    "по": frozenset({"datv", "loct", "accs"}),
    "о": frozenset({"loct", "loc1", "loc2", "accs"}),
    "об": frozenset({"loct", "loc1", "loc2", "accs"}),
    "обо": frozenset({"loct", "loc1", "loc2", "accs"}),
    "при": frozenset({"loct", "loc1", "loc2"}),
    "через": frozenset({"accs"}),
    "про": frozenset({"accs"}),
    "в": frozenset({"accs", "loct", "loc1", "loc2"}),
    "во": frozenset({"accs", "loct", "loc1", "loc2"}),
    "на": frozenset({"accs", "loct", "loc1", "loc2"}),
    "за": frozenset({"accs", "ablt"}),
    "под": frozenset({"accs", "ablt"}),
    "над": frozenset({"ablt"}),
    "перед": frozenset({"ablt"}),
    "между": frozenset({"ablt", "gent"}),
    "с": frozenset({"ablt", "gent", "gen1", "gen2"}),
    "со": frozenset({"ablt", "gent", "gen1", "gen2"}),
}

_PROPER_GRAMMEMES = frozenset({"Name", "Surn", "Patr", "Geox", "Orgn", "Trad"})

# Russian ЙЦУКЕН physical-key neighbourhood.  It changes only substitution cost;
# it is never a lexical/semantic word list.
_KEYBOARD_ROWS = ("йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю")
_KEYBOARD_NEIGHBOURS: dict[str, frozenset[str]] = {}
for _row_index, _row in enumerate(_KEYBOARD_ROWS):
    for _column, _char in enumerate(_row):
        _near: set[str] = set()
        for _other_row_index in range(max(0, _row_index - 1), min(len(_KEYBOARD_ROWS), _row_index + 2)):
            _other = _KEYBOARD_ROWS[_other_row_index]
            # Rows are physically staggered; checking both adjacent columns is a
            # conservative keyboard-neighbour approximation.
            for _other_column in range(max(0, _column - 1), min(len(_other), _column + 2)):
                _near.add(_other[_other_column])
        _near.discard(_char)
        _KEYBOARD_NEIGHBOURS[_char] = frozenset(_near)


def weighted_damerau_levenshtein(left: str, right: str) -> float:
    """Optimal-string-alignment distance with Russian keyboard weights."""

    source = left.casefold()
    target = right.casefold()
    if source == target:
        return 0.0
    if not source:
        return float(len(target))
    if not target:
        return float(len(source))

    rows: list[list[float]] = [[float(index) for index in range(len(target) + 1)]]
    for i, source_char in enumerate(source, start=1):
        current = [float(i)]
        for j, target_char in enumerate(target, start=1):
            if source_char == target_char:
                substitution = 0.0
            elif {source_char, target_char} == {"е", "ё"}:
                substitution = 0.15
            elif target_char in _KEYBOARD_NEIGHBOURS.get(source_char, ()): 
                substitution = 0.55
            else:
                substitution = 1.0
            value = min(
                current[j - 1] + 1.0,       # insertion
                rows[i - 1][j] + 1.0,       # deletion
                rows[i - 1][j - 1] + substitution,
            )
            if (
                i > 1
                and j > 1
                and source_char == target[j - 2]
                and source[i - 2] == target_char
            ):
                value = min(value, rows[i - 2][j - 2] + 0.65)
            current.append(value)
        rows.append(current)
    return rows[-1][-1]


@dataclass(frozen=True, slots=True)
class _RankedCandidate:
    text: str
    analyses: tuple[MorphInfo, ...]
    distance: float
    grammar_score: float
    morphology_score: float
    frequency_score: float
    base_score: float


class LexicalRecovery:
    """Conservative typo/OOV recovery before final morphology and semantics.

    Candidate generation is delegated to a dictionary index (pymorphy's DAWG in
    production).  Orthography, morphology and source-frame constraints are applied
    in that order.  A local embedding provider may rerank only the final close
    shortlist; a failed/unavailable provider leaves the decision AMBIGUOUS.
    """

    def __init__(
        self,
        morphology: Morphology,
        *,
        semantic_reranker: SemanticCandidateReranker | None = None,
        max_candidates: int = 512,
    ) -> None:
        self.morphology = morphology
        self.semantic_reranker = semantic_reranker
        self.max_candidates = max_candidates

    def available(self) -> bool:
        return callable(getattr(self.morphology, "is_known", None)) and callable(
            getattr(self.morphology, "indexed_candidates", None)
        )

    @staticmethod
    def _is_word(text: str) -> bool:
        return _CYRILLIC_WORD.fullmatch(text) is not None

    @staticmethod
    def _restore_case(raw: str, candidate: str) -> str:
        if raw.isupper():
            return candidate.upper()
        if raw[:1].isupper():
            return candidate[:1].upper() + candidate[1:]
        return candidate

    @staticmethod
    def _analyses(morphology: Morphology, word: str) -> tuple[MorphInfo, ...]:
        try:
            return tuple(morphology.analyze_all(word))
        except AttributeError:
            one = morphology.analyze(word)
            return () if one is None else (one,)

    @staticmethod
    @lru_cache(maxsize=65536)
    def _weak_frequency(word: str) -> float:
        """Optional corpus prior, deliberately capped below structural evidence."""
        try:
            from wordfreq import zipf_frequency  # type: ignore[import-not-found]
        except (ImportError, ModuleNotFoundError):
            return 0.0
        value = float(zipf_frequency(word, "ru"))
        return max(0.0, min(1.0, (value - 1.5) / 6.0))

    @staticmethod
    def _previous_word(tokens: tuple["SourceToken", ...], index: int) -> "SourceToken | None":
        for token in reversed(tokens[: index - 1]):
            if _WORD_PART.search(token.text):
                return token
            if token.text in {".", "!", "?", ";", ":"}:
                return None
        return None

    @staticmethod
    def _is_sentence_initial(tokens: tuple["SourceToken", ...], index: int) -> bool:
        return LexicalRecovery._previous_word(tokens, index) is None

    @staticmethod
    def _has_pos(analyses: tuple[MorphInfo, ...], poses: set[str]) -> bool:
        return any(item.pos in poses for item in analyses)

    @staticmethod
    def _governed_cases(token: "SourceToken | None") -> frozenset[str] | None:
        if token is None:
            return None
        lemmas = {
            item.normal_form.casefold()
            for item in material_analyses(token.analyses)
            if item.pos == "PREP" and item.normal_form
        }
        cases: set[str] = set()
        for lemma in lemmas:
            cases.update(_PREPOSITION_CASES.get(lemma, ()))
        return frozenset(cases) if cases else None

    @staticmethod
    def _candidate_case_compatible(
        candidate: _RankedCandidate, governed_cases: frozenset[str] | None
    ) -> bool:
        if governed_cases is None:
            return True
        return any(
            item.pos in {"NOUN", "NPRO", "ADJF", "PRTF", "NUMR"}
            and item.case in governed_cases
            for item in material_analyses(candidate.analyses)
        )

    @staticmethod
    def _morphology_continuity(
        raw_analyses: tuple[MorphInfo, ...], candidate_analyses: tuple[MorphInfo, ...]
    ) -> float:
        """Weakly reward inflectional continuity without trusting productive OOV parses.

        Pymorphy can infer morphology for an unknown surface form.  That inference is
        useful for preserving endings/case, but it is not reliable enough to veto a
        correction.  Therefore this score is positive-only and deliberately weaker
        than orthography and clause structure.
        """
        raw = material_analyses(raw_analyses)
        candidate = material_analyses(candidate_analyses)
        if not raw or not candidate:
            return 0.0
        best = 0.0
        for left in raw:
            for right in candidate:
                score = 0.0
                if left.pos is not None and left.pos == right.pos:
                    score += 0.35
                if left.case is not None and left.case == right.case:
                    score += 0.30
                if left.number is not None and left.number == right.number:
                    score += 0.15
                if left.gender is not None and left.gender == right.gender:
                    score += 0.05
                if left.mood is not None and left.mood == right.mood:
                    score += 0.10
                if (
                    left.transitivity is not None
                    and left.transitivity == right.transitivity
                ):
                    score += 0.05
                best = max(best, score)
        return min(1.0, best)

    def _structural_object_bias(
        self,
        token: "SourceToken",
        analyses: tuple[MorphInfo, ...],
        tokens: tuple["SourceToken", ...],
        graph: "LinguisticCandidateGraph",
    ) -> float:
        """Return a small form-level bias for a direct-object-shaped open slot.

        This never assigns OBJECT.  It is used only while choosing the corrected
        *surface word form*.  The signal is admitted when a reliable transitive
        finite predicate and a separate overt nominative participant already exist
        in the same clause, so an accusative-compatible candidate is structurally
        better than a nominative-only one.
        """
        clause = graph.clause_for_token(token.index)
        if clause is None:
            return 0.0
        is_known = getattr(self.morphology, "is_known", None)
        transitive_heads = []
        for head in clause.predicate_heads:
            if head.token_index == token.index or not head.finite:
                continue
            head_token = graph.token(head.token_index)
            if callable(is_known) and not bool(is_known(head_token.text)):
                continue
            if stable_transitivity(head_token.analyses) == "tran":
                transitive_heads.append(head)
        if len(transitive_heads) != 1:
            return 0.0
        overt_subject = any(
            item.index != token.index
            and (not callable(is_known) or bool(is_known(item.text)))
            and any(
                info.pos in {"NOUN", "NPRO"} and info.case == "nomn"
                for info in material_analyses(item.analyses)
            )
            for item in tokens[clause.span.start_index - 1 : clause.span.end_index]
        )
        if not overt_subject:
            return 0.0
        material = material_analyses(analyses)
        has_acc = any(
            item.pos in {"NOUN", "NPRO", "ADJF", "PRTF", "NUMR"}
            and item.case == "accs"
            for item in material
        )
        has_nom = any(
            item.pos in {"NOUN", "NPRO", "ADJF", "PRTF", "NUMR"}
            and item.case == "nomn"
            for item in material
        )
        if has_acc:
            return 0.30
        if has_nom:
            return -0.08
        return 0.0

    def _titlecase_non_name_slot(
        self,
        token: "SourceToken",
        tokens: tuple["SourceToken", ...],
        graph: "LinguisticCandidateGraph",
        ranked: tuple[_RankedCandidate, ...],
    ) -> bool:
        """Whether syntax independently shows a title-cased OOV is not the subject/name slot."""
        if not ranked or not self._is_sentence_initial(tokens, token.index):
            return False
        clause = graph.clause_for_token(token.index)
        if clause is None:
            return False
        is_known = getattr(self.morphology, "is_known", None)
        heads = []
        for head in clause.predicate_heads:
            if head.token_index == token.index or not head.finite:
                continue
            head_token = graph.token(head.token_index)
            if callable(is_known) and not bool(is_known(head_token.text)):
                continue
            if stable_transitivity(head_token.analyses) == "tran":
                heads.append(head)
        if len(heads) != 1:
            return False
        has_other_subject = any(
            item.index != token.index
            and (not callable(is_known) or bool(is_known(item.text)))
            and any(
                info.pos in {"NOUN", "NPRO"} and info.case == "nomn"
                for info in material_analyses(item.analyses)
            )
            for item in tokens[clause.span.start_index - 1 : clause.span.end_index]
        )
        if not has_other_subject:
            return False
        best = ranked[0]
        common_accusative = any(
            item.pos == "NOUN"
            and item.case == "accs"
            and not (item.grammemes & _PROPER_GRAMMEMES)
            for item in material_analyses(best.analyses)
        )
        return common_accusative

    def _grammar_score(
        self,
        token: "SourceToken",
        analyses: tuple[MorphInfo, ...],
        tokens: tuple["SourceToken", ...],
        graph: "LinguisticCandidateGraph",
    ) -> tuple[float, float]:
        material = material_analyses(analyses)
        if not material:
            return -1.0, 0.0
        index = token.index
        predicate_indices = {head.token_index for head in graph.predicates}
        verbal = {"VERB", "INFN", "GRND", "PRED", "PRTS", "ADJS"}
        finite = {"VERB", "PRED", "PRTS", "ADJS"}
        nominal = {"NOUN", "NPRO", "ADJF", "PRTF", "NUMR"}
        previous = self._previous_word(tokens, index)
        previous_analyses = () if previous is None else material_analyses(previous.analyses)
        governed = any(item.pos == "PREP" for item in previous_analyses)
        governed_cases = self._governed_cases(previous) if governed else None
        counted = any(item.pos == "NUMR" for item in previous_analyses)

        clause = graph.clause_for_token(index)
        clause_heads = () if clause is None else clause.predicate_heads
        is_known = getattr(self.morphology, "is_known", None)

        def reliable_other_head(head: object) -> bool:
            head_index = int(getattr(head, "token_index"))
            if not bool(getattr(head, "finite")) or head_index == index:
                return False
            # Productive morphology deliberately proposes parses for OOV words.
            # Such a parse is useful as a hypothesis for *that* token, but must
            # not veto a finite correction for a neighbouring typo.  Only an
            # exact dictionary token is stable enough to constrain another one.
            if callable(is_known):
                try:
                    return bool(is_known(graph.token(head_index).text))
                except (IndexError, TypeError, ValueError):
                    return False
            return True

        reliable_clause_heads = tuple(
            head for head in clause_heads if reliable_other_head(head)
        )
        clause_has_finite = bool(reliable_clause_heads)
        raw_was_predicate = index in predicate_indices
        structurally_linked_predicate = any(
            index in {edge.parent_token_index, edge.child_token_index}
            for edge in graph.frame_graph.dependencies
        ) or any(
            index in group.member_token_indices
            for group in graph.frame_graph.coordinations
        )

        clause_start = 1 if clause is None else clause.span.start_index
        clause_end = len(tokens) if clause is None else clause.span.end_index
        overt_subjects = tuple(
            (item.index, analysis)
            for item in tokens[clause_start - 1 : clause_end]
            if item.index != index
            and (
                not callable(is_known)
                or bool(is_known(item.text))
            )
            for analysis in material_analyses(item.analyses)
            if analysis.pos in {"NOUN", "NPRO"} and analysis.case == "nomn"
        )

        def agrees_with_overt_subject(candidate: MorphInfo) -> bool:
            if not overt_subjects:
                return True
            for _subject_index, subject in overt_subjects:
                if (
                    candidate.number is not None
                    and subject.number is not None
                    and candidate.number != subject.number
                ):
                    continue
                if (
                    "past" in candidate.grammemes
                    and candidate.number == "sing"
                    and candidate.gender is not None
                    and subject.gender is not None
                    and candidate.gender != subject.gender
                ):
                    continue
                if (
                    subject.pos == "NOUN"
                    and candidate.grammemes & {"1per", "2per"}
                ):
                    continue
                return True
            # Coordinated singular nominatives can license a plural predicate.
            return (
                candidate.number == "plur"
                and len({subject_index for subject_index, _ in overt_subjects}) >= 2
            )

        if governed:
            if governed_cases:
                compatible = tuple(
                    item for item in material
                    if item.pos in nominal and item.case in governed_cases
                )
            else:
                compatible = tuple(
                    item for item in material
                    if item.pos in nominal and item.case not in {None, "nomn"}
                )
            grammar = 1.0 if compatible else -1.0
        elif counted:
            compatible = tuple(
                item for item in material
                if item.pos == "NOUN" and item.case in {"gent", "gen1", "gen2"}
            )
            grammar = 1.0 if compatible else -0.75
        elif raw_was_predicate and (
            not clause_has_finite or structurally_linked_predicate
        ):
            compatible = tuple(item for item in material if item.pos in verbal)
            grammar = 1.0 if compatible else -1.0
        elif not clause_has_finite and self._has_pos(material, finite):
            compatible = tuple(
                item for item in material
                if item.pos in finite and agrees_with_overt_subject(item)
            )
            grammar = 0.9 if compatible else -0.75
        elif clause_has_finite:
            raw_nonverbal_poses = {
                item.pos for item in token.analyses
                if item.pos is not None and item.pos not in verbal
            }
            compatible = tuple(
                item for item in material
                if item.pos in nominal or item.pos in raw_nonverbal_poses
            )
            grammar = 0.55 if compatible else -0.35
        else:
            raw_poses = {item.pos for item in material_analyses(token.analyses) if item.pos}
            compatible = tuple(item for item in material if item.pos in raw_poses)
            grammar = 0.35 if compatible else 0.0

        grammar += self._structural_object_bias(token, analyses, tokens, graph)

        # Lower-case source tokens must not drift toward dictionary proper names
        # merely because a name paradigm has a high morphology probability.
        # This is a morphology-class constraint, not a private name list; a
        # title-cased raw token keeps those candidates fully available.
        if not token.text[:1].isupper() and compatible:
            if all(item.grammemes & _PROPER_GRAMMEMES for item in compatible):
                grammar -= 0.25

        score_pool = compatible or material
        morph_score = max((max(0.0, item.score) for item in score_pool), default=0.0)
        return grammar, morph_score

    def _context_text(
        self,
        token: "SourceToken",
        tokens: tuple["SourceToken", ...],
        graph: "LinguisticCandidateGraph",
    ) -> str:
        clause = graph.clause_for_token(token.index)
        selected = (
            tokens
            if clause is None
            else tokens[clause.span.start_index - 1 : clause.span.end_index]
        )
        values = [
            item.text
            for item in selected
            if item.index != token.index and self._is_word(item.text)
        ]
        predicate_lemmas: list[str] = []
        if clause is not None:
            for head in clause.predicate_heads:
                predicate_lemmas.extend(head.lemma_candidates)
        parts = []
        if predicate_lemmas:
            parts.append("PREDICATE " + " ".join(dict.fromkeys(predicate_lemmas)))
        if values:
            parts.append("CONTEXT " + " ".join(values))
        return " | ".join(parts)

    def _rank_candidates(
        self,
        token: "SourceToken",
        candidates: tuple[str, ...],
        tokens: tuple["SourceToken", ...],
        graph: "LinguisticCandidateGraph",
    ) -> tuple[_RankedCandidate, ...]:
        ranked: list[_RankedCandidate] = []
        for candidate in candidates:
            analyses = self._analyses(self.morphology, candidate)
            grammar, morph_score = self._grammar_score(
                token, analyses, tokens, graph
            )
            distance = weighted_damerau_levenshtein(token.text, candidate)
            frequency = self._weak_frequency(candidate)
            continuity = self._morphology_continuity(token.analyses, analyses)
            length = max(len(token.text), len(candidate), 1)
            score = (
                1.0
                - distance / length
                + 0.42 * grammar
                + 0.08 * morph_score
                + 0.04 * frequency
                + 0.10 * continuity
            )
            ranked.append(
                _RankedCandidate(
                    candidate,
                    analyses,
                    distance,
                    grammar,
                    morph_score,
                    frequency,
                    score,
                )
            )
        ranked.sort(key=lambda item: (-item.base_score, item.distance, item.text))
        if not ranked:
            return ()
        # A strongly incompatible POS/case candidate cannot survive merely because
        # it is common. Keep all candidates close to the best grammatical fit so
        # rare valid words are never dropped by frequency alone.
        best_grammar = max(item.grammar_score for item in ranked)
        narrowed = tuple(
            item for item in ranked
            if item.grammar_score >= best_grammar - 0.40
        )
        return tuple(sorted(narrowed, key=lambda item: (-item.base_score, item.distance, item.text)))

    def _protected_oov(
        self,
        token: "SourceToken",
        tokens: tuple["SourceToken", ...],
        graph: "LinguisticCandidateGraph",
        ranked: tuple[_RankedCandidate, ...],
    ) -> bool:
        raw = token.text
        neighbours = {
            tokens[position].text
            for position in (token.index - 2, token.index)
            if 0 <= position < len(tokens)
        }
        if neighbours & {"«", "»", "“", "”", "„", '"', "'", "`"}:
            return True
        if raw.isupper() and len(raw) > 1:
            return True
        if any(char.isdigit() for char in raw) or not self._is_word(raw):
            return True
        if not raw[:1].isupper():
            return False

        # Preserve names/new terms by default.  A title-cased geographic typo in
        # a prepositional slot is recoverable only when every competitive candidate
        # is independently marked geographic by morphology.  Sentence-initial OOV
        # remains protected unless syntax has no other finite predicate and the
        # candidates are unambiguously finite verbal forms.
        previous = self._previous_word(tokens, token.index)
        previous_is_prep = previous is not None and any(
            item.pos == "PREP" for item in material_analyses(previous.analyses)
        )
        governed_cases = self._governed_cases(previous) if previous_is_prep else None
        if previous_is_prep and ranked:
            competitive = tuple(
                candidate
                for candidate in ranked[: min(6, len(ranked))]
                if ranked[0].base_score - candidate.base_score <= 0.12
                and self._candidate_case_compatible(candidate, governed_cases)
            )
            top_is_geographic = any(
                "Geox" in item.grammemes
                for item in material_analyses(ranked[0].analyses)
            )
            if top_is_geographic and (
                len(competitive) <= 1
                or all(
                    any("Geox" in item.grammemes for item in material_analyses(candidate.analyses))
                    for candidate in competitive
                )
            ):
                return False
        if self._titlecase_non_name_slot(token, tokens, graph, ranked):
            return False
        if self._is_sentence_initial(tokens, token.index) and ranked:
            finite = {"VERB", "PRED", "PRTS", "ADJS"}
            if all(self._has_pos(candidate.analyses, finite) for candidate in ranked):
                return False
        return True

    def recover(
        self,
        text: str,
        tokens: tuple["SourceToken", ...],
        graph: "LinguisticCandidateGraph",
    ) -> tuple[TokenCandidate, ...]:
        del text  # offsets/raw evidence remain owned by the caller's graph
        if not self.available():
            return tuple(
                TokenCandidate(
                    token.index,
                    token.text,
                    token.text,
                    LexicalRecoveryStatus.EXACT,
                    confidence=1.0,
                    reason="dictionary index unavailable; recovery disabled",
                )
                for token in tokens
            )

        is_known = getattr(self.morphology, "is_known")
        indexed_candidates = getattr(self.morphology, "indexed_candidates")
        decisions: list[TokenCandidate] = []
        for token in tokens:
            raw = token.text
            if not self._is_word(raw):
                word_like = bool(re.search(r"\w", raw, flags=re.UNICODE))
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        raw,
                        (
                            LexicalRecoveryStatus.UNKNOWN_TOKEN
                            if word_like else LexicalRecoveryStatus.EXACT
                        ),
                        confidence=0.0 if word_like else 1.0,
                        reason=(
                            "protected non-Cyrillic/alphanumeric token"
                            if word_like else "non-lexical token"
                        ),
                    )
                )
                continue
            if is_known(raw):
                decisions.append(
                    TokenCandidate(
                        token.index, raw, raw, LexicalRecoveryStatus.EXACT,
                        confidence=1.0, reason="dictionary exact",
                    )
                )
                continue
            if len(raw.replace("-", "")) < 3:
                decisions.append(
                    TokenCandidate(
                        token.index, raw, raw, LexicalRecoveryStatus.UNKNOWN_TOKEN,
                        confidence=0.0, reason="short OOV is unsafe to autocorrect",
                    )
                )
                continue

            generated = tuple(indexed_candidates(
                raw, max_distance=1, limit=self.max_candidates
            ))
            if not generated and len(raw.replace("-", "")) >= 7:
                generated = tuple(indexed_candidates(
                    raw, max_distance=2, limit=self.max_candidates
                ))
            ranked = self._rank_candidates(token, generated, tokens, graph)
            display = tuple(
                self._restore_case(raw, item.text) for item in ranked[:8]
            )

            if self._protected_oov(token, tokens, graph, ranked):
                decisions.append(
                    TokenCandidate(
                        token.index, raw, raw, LexicalRecoveryStatus.UNKNOWN_TOKEN,
                        alternatives=display, confidence=0.0,
                        reason="protected name/term/acronym OOV",
                    )
                )
                continue
            if not ranked:
                decisions.append(
                    TokenCandidate(
                        token.index, raw, raw, LexicalRecoveryStatus.UNKNOWN_TOKEN,
                        confidence=0.0, reason="no indexed candidate",
                    )
                )
                continue

            best = ranked[0]
            base_margin = (
                float("inf") if len(ranked) == 1
                else best.base_score - ranked[1].base_score
            )
            selected = best
            confidence = 0.0
            reason = ""
            if len(ranked) == 1:
                confidence = 0.97
                reason = "unique orthographic+morphosyntactic candidate"
            elif base_margin >= 0.20:
                confidence = min(0.96, 0.84 + base_margin / 2.0)
                reason = "morphosyntactic margin"
            elif (
                best.grammar_score - ranked[1].grammar_score >= 0.35
                and best.distance <= ranked[1].distance + 0.25
            ):
                confidence = 0.88
                reason = "strong grammatical dominance"
            elif (
                ranked[1].distance - best.distance >= 0.45
                and best.grammar_score >= ranked[1].grammar_score - 0.10
            ):
                confidence = 0.87
                reason = "weighted orthographic dominance"
            else:
                close = tuple(
                    item for item in ranked[:8]
                    if best.base_score - item.base_score <= 0.20
                )
                semantic_scores: dict[str, float] = {}
                if self.semantic_reranker is not None and len(close) >= 2:
                    try:
                        semantic_scores = self.semantic_reranker.rank(
                            self._context_text(token, tokens, graph),
                            tuple(item.text for item in close),
                        )
                    except Exception:
                        # Embeddings are optional enrichment. Transport/model errors
                        # must not turn into a forced correction or parser outage.
                        semantic_scores = {}
                if semantic_scores and all(item.text in semantic_scores for item in close):
                    sem_sorted = sorted(
                        close,
                        key=lambda item: (
                            -(item.base_score + 0.35 * semantic_scores[item.text]),
                            item.distance,
                            item.text,
                        ),
                    )
                    semantic_best = sem_sorted[0]
                    semantic_margin = (
                        semantic_best.base_score
                        + 0.35 * semantic_scores[semantic_best.text]
                        - sem_sorted[1].base_score
                        - 0.35 * semantic_scores[sem_sorted[1].text]
                    )
                    raw_semantic_margin = (
                        semantic_scores[semantic_best.text]
                        - semantic_scores[sem_sorted[1].text]
                    )
                    if semantic_margin >= 0.10 and raw_semantic_margin >= 0.05:
                        selected = semantic_best
                        confidence = min(0.94, 0.82 + semantic_margin / 2.0)
                        reason = "local embedding rerank after deterministic narrowing"

            if confidence > 0.0:
                normalized = self._restore_case(raw, selected.text)
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        normalized,
                        LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE,
                        alternatives=display,
                        confidence=confidence,
                        reason=reason,
                    )
                )
            else:
                decisions.append(
                    TokenCandidate(
                        token.index,
                        raw,
                        None,
                        LexicalRecoveryStatus.AMBIGUOUS,
                        alternatives=display,
                        confidence=0.0,
                        reason="no safe deterministic or embedding margin",
                    )
                )
        return tuple(decisions)
