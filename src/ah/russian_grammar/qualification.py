from dataclasses import replace
from functools import cache
from importlib.resources import files
from itertools import combinations
from typing import NamedTuple

from .detached_prepositions import extent
from .morphology import NOMINAL_ROLES, PREDICATE_ROLES
from .prepositions import FORMS, PREFIXES
from .rules import readings


@cache
def _attestations():
    rows = files(__package__).joinpath('lexicon/detached-groups.tsv').read_text(encoding='utf8')
    return frozenset(tuple(line.split('\t')) for line in rows.splitlines())


class Opening(NamedTuple):
    left: int | None
    start: int
    noun: int
    lemmas: frozenset[str]


class GroupOpenings:
    def __init__(self):
        self.pending = []
        self.prefixes = []
        self.position = 0

    def feed(self, surface):
        i = self.position
        self.position += 1
        continuing = []
        opened = []
        for start, prep in self.pending:
            options = readings(surface, prep)
            nouns = frozenset(r.lemma for r in options if r.role == 'governed')
            if nouns:
                left = start - 1 if start else None
                opened.append(Opening(left, start, i, nouns))
            if any(r.role == 'group_attribute' for r in options):
                continuing.append((start, prep))
        word = surface.casefold()
        phrases = [(start, prefix + ' ' + word) for start, prefix in self.prefixes]
        phrases.append((i, word))
        self.prefixes = []
        for start, phrase in phrases:
            if phrase in FORMS:
                continuing.append((start, FORMS[phrase]))
            if phrase in PREFIXES:
                self.prefixes.append((start, phrase))
        self.pending = continuing
        return opened


def openings(words):
    scanner = GroupOpenings()
    for token in words:
        yield from scanner.feed(token.surface)


def _interrupted(tree, left, end, host):
    if left is None or host < end or tree[left].role not in NOMINAL_ROLES:
        return False
    index = left
    while index is not None and index != host:
        index = tree[index].head
    return index == host


def sites(tree, opened):
    seen = set()
    for left, start, noun, lemmas in opened:
        if start in seen:
            continue
        prep = tree[start]
        if (prep.role != 'preposition' or prep.scope is not None or prep.rule == 'PP.DETACHED'
                or prep.head is None or tree[prep.head].role not in PREDICATE_ROLES):
            continue
        nominal = tree[noun]
        if nominal.role != 'governed' or nominal.head != start or nominal.lemma not in lemmas:
            continue
        end = extent(tree, start)
        if end is None:
            continue
        attested = (prep.lemma, nominal.lemma) in _attestations()
        expanded = any(tree[j].head == noun and tree[j].role in {'genitive_modifier', 'possessive'}
                       for j in range(start + 1, end))
        if ((attested and (start == 0 or prep.head >= end or expanded))
                or (expanded and _interrupted(tree, left, end, prep.head))):
            seen.add(start)
            yield start, end


def filtered(tree, opened, accept, budget):
    from .parser import AnalysisBudgetExceeded

    if accept(tree):
        yield tree
    starts = tuple(i for i, _ in sites(tree, opened))
    if 2 ** len(starts) > budget:
        raise AnalysisBudgetExceeded('QUALIFICATION_BUDGET')
    for size in range(1, len(starts) + 1):
        for selection in combinations(starts, size):
            variant = list(tree)
            for i in selection:
                variant[i] = replace(variant[i], scope='qualification')
            option = tuple(variant)
            if accept(option):
                yield option
