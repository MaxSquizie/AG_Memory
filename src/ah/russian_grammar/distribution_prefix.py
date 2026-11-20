from bisect import bisect_left
from dataclasses import dataclass, replace
from functools import lru_cache

from .determiners import SCOPES
from .numerals import _atoms, expressions
from .rules import known_forms


@dataclass(frozen=True)
class DistributionStep:
    start: int
    surface: str
    kind: str
    marker_start: int
    quantities: tuple[str, ...] = ()


@lru_cache(maxsize=2048)
def _binders(surface):
    return tuple((word, tag) for word, tag in known_forms(surface)
                 if word in SCOPES and tag.POS == 'ADJF' and 'Subx' in tag)


class DistributionPrefix:
    def __init__(self):
        self._tokens = []
        self._openings = []
        self._indices = {}
        self._numbers = {}
        self._open = None

    def feed(self, token, report=None):
        i = len(self._tokens)
        self._indices[token.start] = i
        self._tokens.append(token)
        word = token.surface.casefold()
        forms = _binders(word)
        if self._open is not None:
            marker = self._open
            readings = known_forms(word)
            atoms = _atoms(word)
            if atoms:
                span = self._tokens[marker + 1:i + 1]
                values = tuple(e for e in expressions(span) if e.end == len(span))
                if not values and all(a.kind in ('cardinal', 'digit', 'collective') for a in atoms):
                    self._open = None
                self._numbers[marker].extend(values)
                if report is not None:
                    choices = tuple(dict.fromkeys(e.value for e in values if e.value is not None))
                    report(DistributionStep(token.start, token.surface, 'quantity_candidate',
                                            self._tokens[marker].start, choices))
            elif word == 'из' and marker + 1 == i and _binders(self._tokens[marker].surface.casefold()):
                if report is not None:
                    report(DistributionStep(token.start, token.surface, 'partitive_candidate', self._tokens[marker].start))
            elif any(tag.POS in ('NOUN', 'NPRO') for _, tag in readings):
                if report is not None:
                    readings = self._numbers[marker]
                    last = readings[-1].end if readings else None
                    choices = tuple(dict.fromkeys(e.value for e in readings if e.end == last and e.value is not None))
                    kind = 'domain_candidate' if _binders(self._tokens[marker].surface.casefold()) else 'nominal_candidate'
                    report(DistributionStep(token.start, token.surface, kind, self._tokens[marker].start, choices))
                self._open = None
            elif not any(tag.POS in ('ADJF', 'PRTF') for _, tag in readings):
                self._open = None
        if word in ('по', 'на') or forms:
            self._openings.append(i)
            self._open = i
            self._numbers[i] = []
            if report is not None:
                kind = 'binder_candidate' if forms else 'preposition_candidate'
                report(DistributionStep(token.start, token.surface, kind, token.start))

    @classmethod
    def from_tokens(cls, tokens):
        chart = cls()
        for token in tokens:
            chart.feed(token)
        return chart

    def sites(self, tokens):
        if not tokens:
            return
        offset = 0 if len(tokens) == len(self._tokens) else self._indices.get(tokens[0].start)
        if (offset is None or offset + len(tokens) > len(self._tokens)
                or any(token != self._tokens[offset + j] for j, token in enumerate(tokens))):
            if any(token.surface.casefold() == 'по' or _binders(token.surface.casefold()) for token in tokens):
                yield from self.from_tokens(tokens).sites(tokens)
            return
        stop = offset + len(tokens)
        left = bisect_left(self._openings, offset)
        right = bisect_left(self._openings, stop, lo=left)
        for i in self._openings[left:right]:
            j = i - offset
            surface = tokens[j].surface.casefold()
            counted = tuple(replace(e, end=j + 1 + e.end) for e in self._numbers[i] if i + 1 + e.end <= stop)
            yield j, _binders(surface), counted
