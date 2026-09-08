from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
import re


@dataclass(frozen=True, slots=True)
class MorphInfo:
    normal_form: str
    pos: str | None
    case: str | None = None
    number: str | None = None
    gender: str | None = None
    mood: str | None = None
    animacy: str | None = None
    transitivity: str | None = None
    grammemes: frozenset[str] = frozenset()
    score: float = 0.0


class Morphology(Protocol):
    name: str

    def analyze(self, word: str) -> MorphInfo | None: ...
    def analyze_all(self, word: str) -> tuple[MorphInfo, ...]: ...

    # Optional lexical-recovery capabilities.  Lightweight/test morphology
    # adapters need not implement them; callers feature-detect the methods and
    # leave their input untouched when no dictionary index is available.
    def is_known(self, word: str) -> bool: ...
    def indexed_candidates(
        self, word: str, *, max_distance: int, limit: int = 512
    ) -> tuple[str, ...]: ...


def material_analyses(analyses: tuple[MorphInfo, ...]) -> tuple[MorphInfo, ...]:
    """Return morphology readings strong enough to remain runtime candidates.

    Dictionary analysers intentionally expose rare parses.  Those are useful for
    ambiguity handling but must not let negligible readings explode the candidate
    lattice. Keep only readings that are competitive with the best parse. This
    filtering is not authority to choose or mutate canonical lexical identity.
    Scoreless test morphologies preserve every reading.
    """
    if not analyses:
        return ()
    top = max((item.score for item in analyses), default=0.0)
    if top <= 0.0:
        return analyses
    floor = top * 0.30
    return tuple(item for item in analyses if item.score >= floor)



def stable_transitivity(analyses: tuple[MorphInfo, ...]) -> str | None:
    """Return a deterministic lexical transitivity cue, or ``None``.

    This is perception-side dictionary evidence only.  It may narrow a latent
    OBJECT hypothesis before any SLM call, but it never creates canonical AH
    objects or mutates a T.  A cue is accepted only when all material verbal
    readings that expose transitivity agree.
    """
    material = tuple(
        item for item in material_analyses(analyses)
        if item.pos in {"VERB", "INFN", "PRTF", "PRTS", "GRND"}
        and item.transitivity in {"tran", "intr"}
    )
    if not material:
        return None
    values = {item.transitivity for item in material}
    if len(values) != 1:
        return None
    return next(iter(values))

def stable_normal_form(
    analyses: tuple[MorphInfo, ...],
    *,
    poses: set[str] | None = None,
) -> str | None:
    """Return one deterministic lexical normal form, or ``None`` if ambiguous.

    Canonicalization is allowed only when all material readings that satisfy the
    optional POS restriction agree on the same normal form.  This lets obvious
    paradigms such as ``Мария/Марии/Марию`` share one lexical key without silently
    collapsing genuine homonymy.
    """
    # Materiality is computed against *all* readings before an optional POS
    # restriction. Otherwise a tiny noun reading of an overwhelmingly adverbial
    # token (e.g. ``Потом``) could become "stable" merely because ADVB was filtered
    # out by a nominal caller.
    globally_material = material_analyses(analyses)
    material = tuple(
        item for item in globally_material
        if item.normal_form.strip() and (poses is None or item.pos in poses)
    )
    if not material:
        return None
    folded = {item.normal_form.strip().casefold() for item in material}
    if len(folded) == 1:
        return material[0].normal_form.strip()

    # Proper-name paradigms occasionally receive one secondary dictionary reading
    # at about half the probability of the dominant analysis (e.g. ``Петру``:
    # Пётр/datv vs Петра/accs). When one lexical normal form is strongly dominant
    # among globally material readings, use it; equal/near-equal forms such as
    # ``пришли`` remain unresolved for later syntactic disambiguation.
    scores: dict[str, float] = {}
    surfaces: dict[str, str] = {}
    for item in material:
        key = item.normal_form.strip().casefold()
        scores[key] = scores.get(key, 0.0) + max(0.0, item.score)
        surfaces.setdefault(key, item.normal_form.strip())
    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    if len(ranked) == 1:
        return surfaces[ranked[0][0]]
    best_key, best_score = ranked[0]
    second_score = ranked[1][1]
    if best_score >= 0.60 and best_score >= second_score * 1.8:
        return surfaces[best_key]
    return None


class NullMorphology:
    name = "none"

    def analyze(self, word: str) -> MorphInfo | None:
        return None

    def analyze_all(self, word: str) -> tuple[MorphInfo, ...]:
        return ()


def _plain_tag_scalar(value: object | None) -> str | None:
    """Normalize pymorphy tag attributes to plain Python strings.

    pymorphy3 exposes several tag attributes (number/case/gender/etc.) as
    grammeme objects that behave *almost* like strings but overload equality and
    may raise when compared with unrelated strings.  MorphInfo's public contract
    is ``str | None``; crossing the adapter boundary with library-specific scalar
    objects leaks those semantics into integration and can make innocent
    comparisons fail at runtime.

    Keep the dependency quarantined here: every scalar leaving the pymorphy
    adapter is either an exact built-in ``str`` or ``None``.
    """
    if value is None:
        return None
    text = str(value)
    return text if text else None


class Pymorphy3Morphology:
    """Dictionary/rule morphology only; no semantic or AH knowledge.

    `analyze_all` is important for Russian ambiguity. The most probable parse is not
    always the syntactically relevant one (for example, a surface form can be both
    nominative plural and genitive singular). Deterministic candidate construction
    therefore keeps all materially distinct parses and lets later syntax constraints
    narrow them instead of treating the top parse as truth.
    """

    name = "pymorphy3"

    def __init__(self) -> None:
        from pymorphy3 import MorphAnalyzer

        self._analyzer = MorphAnalyzer()

    @lru_cache(maxsize=8192)
    def analyze_all(self, word: str) -> tuple[MorphInfo, ...]:
        if re.search(r"[А-Яа-яЁё]", word) is None:
            return ()
        parses = self._analyzer.parse(word)
        if not parses:
            return ()
        result: list[MorphInfo] = []
        seen: set[tuple[object, ...]] = set()
        for item in parses:
            tag = item.tag
            grammemes = frozenset(str(value) for value in getattr(tag, "grammemes", ()))
            transitivity = (
                "tran" if "tran" in grammemes
                else "intr" if "intr" in grammemes
                else None
            )
            info = MorphInfo(
                normal_form=str(item.normal_form),
                pos=_plain_tag_scalar(getattr(tag, "POS", None)),
                case=_plain_tag_scalar(getattr(tag, "case", None)),
                number=_plain_tag_scalar(getattr(tag, "number", None)),
                gender=_plain_tag_scalar(getattr(tag, "gender", None)),
                mood=_plain_tag_scalar(getattr(tag, "mood", None)),
                animacy=_plain_tag_scalar(getattr(tag, "animacy", None)),
                transitivity=transitivity,
                grammemes=grammemes,
                score=float(getattr(item, "score", 0.0) or 0.0),
            )
            key = (
                info.normal_form, info.pos, info.case, info.number, info.gender,
                info.mood, info.animacy, info.transitivity, info.grammemes,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(info)
        return tuple(result)

    def analyze(self, word: str) -> MorphInfo | None:
        analyses = self.analyze_all(word)
        return analyses[0] if analyses else None

    @lru_cache(maxsize=16384)
    def is_known(self, word: str) -> bool:
        """Return dictionary membership, not pymorphy's productive OOV guess.

        ``MorphAnalyzer.parse`` deliberately invents analyses for unknown words.
        Lexical Recovery must distinguish that useful morphology fallback from an
        exact dictionary hit, otherwise every typo would be mislabeled EXACT.
        """
        return bool(self._analyzer.word_is_known(word.casefold()))

    @lru_cache(maxsize=4096)
    def _indexed_candidates_cached(
        self, word: str, max_distance: int, limit: int
    ) -> tuple[str, ...]:
        """Search pymorphy's compressed word DAWG with edit-distance pruning.

        This is an on-demand Levenshtein automaton over the dictionary trie.  It
        visits only prefixes whose dynamic-programming row can still reach the
        query inside ``max_distance``; it never scans or materializes the full
        dictionary.  Adjacent transpositions are added as exact DAWG lookups and
        weighted more precisely by the recovery ranker.
        """
        query = word.casefold()
        if not query or max_distance < 0 or limit <= 0:
            return ()
        words = self._analyzer.dictionary.words
        dictionary = words.dct
        alphabet = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя-"
        initial_row = tuple(range(len(query) + 1))
        found: set[str] = set()

        def visit(prefix: str, state: int, previous_row: tuple[int, ...]) -> None:
            if len(found) >= limit:
                return
            for char in alphabet:
                next_state = dictionary.follow_bytes(char.encode("utf-8"), state)
                if next_state is None:
                    continue
                current = [previous_row[0] + 1]
                for column, query_char in enumerate(query, start=1):
                    current.append(
                        min(
                            current[column - 1] + 1,
                            previous_row[column] + 1,
                            previous_row[column - 1] + (query_char != char),
                        )
                    )
                candidate = prefix + char
                if current[-1] <= max_distance and words._has_value(next_state) is not None:
                    found.add(candidate)
                    if len(found) >= limit:
                        return
                if min(current) <= max_distance:
                    visit(candidate, next_state, tuple(current))

        visit("", dictionary.ROOT, initial_row)

        # A transposition is two Levenshtein edits but one keyboard event.  Probe
        # those O(len(word)) exact variants directly in the same compressed DAWG.
        if max_distance >= 1:
            chars = list(query)
            for index in range(len(chars) - 1):
                if chars[index] == chars[index + 1]:
                    continue
                swapped = chars.copy()
                swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
                candidate = "".join(swapped)
                if self._analyzer.word_is_known(candidate):
                    found.add(candidate)

        return tuple(sorted(found))

    def indexed_candidates(
        self, word: str, *, max_distance: int, limit: int = 512
    ) -> tuple[str, ...]:
        return self._indexed_candidates_cached(
            word.casefold(), int(max_distance), int(limit)
        )


def build_morphology(backend: str = "auto") -> Morphology:
    value = backend.strip().lower()
    if value in {"", "none", "off", "disabled"}:
        return NullMorphology()
    if value not in {"auto", "pymorphy3"}:
        raise ValueError(f"Unsupported morphology backend: {backend}")
    try:
        return Pymorphy3Morphology()
    except (ImportError, ModuleNotFoundError):
        return NullMorphology()
