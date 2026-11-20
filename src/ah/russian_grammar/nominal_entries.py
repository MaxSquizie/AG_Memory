from dataclasses import dataclass, replace
from functools import lru_cache
from math import comb

from .nominal_groups import _groups, _members, _prepositions
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .prepositions import DASHES
from .probe import Probe
from .rules import known_forms



@dataclass(frozen=True)
class Unit:
    start: int
    end: int
    head: int
    link: Link
    extra: tuple
    prep: tuple | None = None


class GroupChoice(Exception):
    def __init__(self, start, heads, tokens, text):
        self.start = start
        self.heads = {_span_label(tokens, i): i for i in sorted(heads)}
        phrase = text[tokens[start].start:tokens[max(heads)].end]
        question = f'Какое слово служит вершиной первой именной группы в сочетании «{phrase}»?'
        self.probe = Probe(question, tuple(self.heads), text)


def _symbol(surface):
    return (surface.isalpha() and surface.isupper() and len(surface) > 1 and not known_forms(surface)
            or surface.isalnum() and any(c.isalpha() for c in surface) and any(c.isdecimal() for c in surface))


def _value(surface):
    return surface.isdecimal() or _symbol(surface)


def _modifiers(tokens, index, budget):
    word = tokens[index].surface
    if _symbol(word):
        yield Unit(index, index + 1, index, Link('designation', word, None, 'N.DESIGNATION'), ())
    for g in _groups(tokens, index, budget, bare_cases=('gent', 'gen2')):
        yield Unit(index, g.end, g.noun, Link('genitive_modifier', g.lemma, None, 'N.GEN', g.case), g.extra)
    for first, prep in _prepositions(tokens, index):
        for head, lemma, case, attrs in _members(tokens, first, prep):
            parts = tuple((i, Link('prep_part', tokens[i].surface.casefold(), index, 'P1'))
                          for i in range(index + 1, first))
            yield Unit(index, head + 1, head, Link('governed', lemma, index, 'P1', case),
                       (*parts, *attrs), (index, prep))


def _layouts(span, seed, constraints, budget):
    @lru_cache(maxsize=None)
    def at(index):
        return tuple(unit for unit in _modifiers(span, index, budget)
                     if index not in constraints or constraints[index] == unit.head)

    pending = [(seed.end, ())]
    layouts = []
    examined = 0
    while pending:
        index, layout = pending.pop()
        if index == len(span):
            layouts.append(layout)
        else:
            for unit in at(index):
                pending.append((unit.end, (*layout, unit)))
                examined += 1
                if examined > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_ENTRY_SEGMENTATION_BUDGET')
    return layouts


def _attach(layout, spine, links):
    pending = [(0, spine, links)]
    while pending:
        index, heads, current = pending.pop()
        if index == len(layout):
            yield tuple(current[i] for i in range(len(current)))
            continue
        unit = layout[index]
        for depth, host in enumerate(heads):
            expanded = {**current, **dict(unit.extra)}
            if unit.prep:
                prep, lemma = unit.prep
                expanded[prep] = Link('preposition', lemma, host, 'P2')
                expanded[unit.head] = unit.link
            else:
                expanded[unit.head] = replace(unit.link, head=host)
            pending.append((index + 1, (*heads[:depth + 1], unit.head), expanded))


def trees(tokens, text, constraints, budget):
    dashes = [i for i, token in enumerate(tokens) if token.surface in DASHES]
    if len(dashes) != 1 or len(tokens) < 3:
        return
    dash, = dashes
    prefix = dash == 1 and _value(tokens[0].surface)
    suffix = dash == len(tokens) - 2 and _value(tokens[-1].surface)
    if prefix == suffix:
        return
    start, stop = (dash + 1, len(tokens)) if prefix else (0, dash)
    span = tokens[:stop]
    for seed in _groups(span, start, budget, bare_cases=('nomn',)):
        layouts = _layouts(span, seed, constraints, budget)
        total = sum(comb(2 * len(layout), len(layout)) // (len(layout) + 1) for layout in layouts)
        if total > budget:
            for units in zip(*layouts):
                heads = {unit.head for unit in units}
                starts = {unit.start for unit in units}
                if len(heads) > 1 and len(starts) == 1:
                    raise GroupChoice(units[0].start, heads, tokens, text)
            raise AnalysisBudgetExceeded('NOMINAL_ENTRY_ATTACHMENT_BUDGET')
        root = seed.noun
        links = dict(seed.extra)
        if prefix:
            links[root] = Link('predicate', seed.lemma, None, 'N.HEADING', 'nomn', scope='heading')
            links[0] = Link('label', tokens[0].surface, root, 'N.LABEL')
            links[dash] = Link('punctuation', tokens[dash].surface, 0, 'N.DASH')
        else:
            value = len(tokens) - 1
            links[value] = Link('predicate', tokens[value].surface, None, 'N.VALUE')
            links[root] = Link('subject', seed.lemma, value, 'N.SUBJECT', 'nomn')
            links[dash] = Link('punctuation', tokens[dash].surface, value, 'N.DASH')
        for layout in layouts:
            yield from _attach(layout, (root,), links)
