from itertools import product

from . import infinitives
from .nominal_groups import _members, _prepositions
from .parser import AnalysisBudgetExceeded, Link
from .rules import known_forms, name_continuations, readings
from .utterances import _map


def _attributes(tokens, start):
    for case in ('nomn', 'accs', 'datv'):
        for noun, lemma, _, attrs in _members(tokens, start, None, case):
            if attrs:
                yield noun + 1, noun, (lemma, case), dict(attrs)


def _names(tokens, start):
    if start + 1 >= len(tokens):
        return
    for first in readings(tokens[start].surface):
        if not first.name_type:
            continue
        for last in name_continuations(tokens[start + 1].surface, (first,)):
            yield start + 2, start, (first.lemma, first.case), {
                start + 1: Link('name_part', last.lemma, start, last.name_rule, case=last.case)}


def trees(tokens, *, budget):
    if not any(any(tag.POS == 'INFN' for _, tag in known_forms(t.surface)) for t in tokens):
        return
    from .prepositions import GOVERNMENT
    layouts = [(0, (), {}, {}, ())]
    count = 0
    while layouts:
        i, kept, constraints, extra, pps = layouts.pop()
        if i < len(tokens):
            layouts.append((i + 1, (*kept, i), constraints, extra, pps))
            for end, noun, bound, links in (*_attributes(tokens, i), *_names(tokens, i)):
                layouts.append((end, (*kept, noun), {**constraints, noun: bound}, {**extra, **links}, pps))
            for first, prep in _prepositions(tokens, i):
                if not GOVERNMENT.get(prep):
                    continue
                for noun, lemma, case, attrs in _members(tokens, first, prep):
                    links = dict(attrs)
                    links[noun] = Link('governed', lemma, i, 'P1', case=case)
                    for k in range(i + 1, first):
                        links[k] = Link('prep_part', tokens[k].surface.casefold(), i, 'P1')
                    layouts.append((noun + 1, kept, constraints, {**extra, **links}, (*pps, (i, prep))))
            if len(layouts) > budget:
                raise AnalysisBudgetExceeded('INFINITIVE_PHRASE_BUDGET')
            continue
        if not extra:
            continue
        count += 1
        if count > budget:
            raise AnalysisBudgetExceeded('INFINITIVE_PHRASE_BUDGET')
        for tree in infinitives.candidates(tuple(tokens[j] for j in kept), budget=budget):
            links = _map(tree, kept)
            if any((links[j].lemma, links[j].case) != expected for j, expected in constraints.items()):
                continue
            links.update(extra)
            hosts = []
            for start, prep in pps:
                left = next((j for j in reversed(kept) if j < start), None)
                chain = []
                j = left
                while j is not None:
                    if links[j].role in {'predicate', 'infinitive', 'subject', 'object', 'recipient'}:
                        chain.append(j)
                    j = links[j].head
                if not chain:
                    chain = [j for j in kept if links[j].role == 'predicate']
                hosts.append([(start, Link('preposition', prep, head, 'P2')) for head in chain])
            for selected in product(*hosts):
                restored = links.copy()
                restored.update(selected)
                yield tuple(restored[j] for j in range(len(tokens)))
