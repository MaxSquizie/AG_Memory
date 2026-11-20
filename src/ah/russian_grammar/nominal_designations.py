from dataclasses import replace
from itertools import chain, combinations

from .lexical_parts import opaque_abbreviation
from .nominal_entries import _attach, _layouts
from .nominal_groups import _groups
from .parser import AnalysisBudgetExceeded, Link
from .passive_arguments import _opaque
from .prepositions import DASHES, FORMS
from .rules import dictionary, known_forms
from .utterances import _map


def _name(surface):
    if not known_forms(surface) and any('LATN' in p.tag for p in dictionary().parse(surface)):
        return Link('apposition', surface, None, 'APP.FOREIGN')
    if _opaque(surface):
        return Link('apposition', surface, None, 'OPAQUE.APPOSITION')
    if surface.istitle():
        for lemma, tag in known_forms(surface):
            if 'Geox' in tag and tag.case == 'nomn':
                return Link('apposition', lemma, None, 'APP.NAME', 'nomn')
    return None


def _definition(tokens, budget):
    if len(tokens) < 2:
        return
    label = tokens[0].surface
    if not (_opaque(label) or opaque_abbreviation(label)):
        return
    dash = tokens[1].surface in DASHES
    start = 1 + int(dash)
    commas = {i for i in range(start + 1, len(tokens) - 1) if tokens[i].surface == ','
              and tokens[i + 1].surface.casefold() in FORMS}
    kept = tuple(i for i in range(len(tokens)) if i not in commas)
    part = tuple(tokens[i] for i in kept)
    for seed in _groups(part, start, budget, bare_cases=('nomn',)):
        links = dict(seed.extra)
        if dash:
            links[start - 1] = Link('punctuation', tokens[start - 1].surface, seed.noun, 'V2.DASH')
        links[0] = Link('subject', label, seed.noun, 'OPAQUE.SUBJECT' if _opaque(label) else 'S1', 'nomn')
        links[seed.noun] = Link('predicate', seed.lemma, None, 'V2', 'nomn')
        for layout in _layouts(part, seed, {}, budget):
            for tree in _attach(layout, (seed.noun,), links):
                result = _map(tree, kept)
                for i in commas:
                    left, right = result[i - 1], result[i + 1]
                    if (left.role != 'governed' or right.role != 'preposition'
                            or result[left.head].lemma != right.lemma):
                        break
                    result[i] = Link('punctuation', ',', i + 1, 'PP.BOUND')
                else:
                    yield tuple(result[i] for i in range(len(tokens)))


def _candidates(tokens, parse, budget):
    yield from _definition(tokens, budget)
    sites = []
    for i in range(1, len(tokens)):
        host = known_forms(tokens[i - 1].surface)
        if not any(tag.POS == 'NOUN' and not {'Geox', 'Name', 'Surn', 'Patr'} & tag.grammemes for _, tag in host):
            continue
        name = _name(tokens[i].surface)
        if name is None:
            continue
        sites.append((i, replace(name, head=i - 1)))
    if 2 ** len(sites) - 1 > budget:
        raise AnalysisBudgetExceeded('NOMINAL_DESIGNATION_BUDGET')
    for n in range(1, len(sites) + 1):
        for selected in combinations(sites, n):
            titles = dict(selected)
            kept = tuple(j for j in range(len(tokens)) if j not in titles)
            reduced = tuple(tokens[j] for j in kept)
            for base in chain(_definition(reduced, budget), parse(reduced)):
                links = _map(base, kept)
                if not all(i - 1 in links and links[i - 1].role in {
                        'subject', 'object', 'genitive_modifier', 'governed', 'nominal_conjunct'} for i in titles):
                    continue
                links.update(titles)
                yield tuple(links[j] for j in range(len(tokens)))


def trees(tokens, parse, budget):
    empty = {j: i - 1 for i in range(1, len(tokens) - 1)
             if tokens[i].surface == '(' and tokens[i + 1].surface == ')' and tokens[i - 1].surface.isalnum()
             for j in (i, i + 1)}
    kept = tuple(i for i in range(len(tokens)) if i not in empty)
    part = tuple(tokens[i] for i in kept) if empty else tokens
    variants = _candidates(part, parse, budget)
    first = next(variants, None)
    if first is None:
        return
    for count, tree in enumerate(chain((first,), variants, parse(part)), 1):
        if count > budget:
            raise AnalysisBudgetExceeded('NOMINAL_DESIGNATION_BUDGET')
        if empty:
            links = _map(tree, kept)
            links.update({i: Link('punctuation', tokens[i].surface, host, 'PUNCT.EMPTY')
                          for i, host in empty.items()})
            yield tuple(links[i] for i in range(len(tokens)))
        else:
            yield tree
