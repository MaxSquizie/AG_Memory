from .morphology import NOMINAL_ROLES
from .nominal_groups import _members, _prepositions
from .numerals import expressions, known_unit
from .quantity_groups import _groups


def _tail(tokens, start, budget):
    from .parser import Link

    for expression in expressions(tokens, start):
        if expression.kind not in ('cardinal', 'fraction'):
            continue
        for group in _groups(tokens, start, expression, budget):
            if group.case != 'accs' or group.morphology.animacy == 'anim' or not known_unit(group.lemma):
                continue
            boundary = group.noun + 1
            for first, prep in _prepositions(tokens, boundary):
                for noun, lemma, case, attrs in _members(tokens, first, prep):
                    if noun + 1 != len(tokens):
                        continue
                    links = dict((*group.links, *attrs))
                    links[boundary] = Link('preposition', prep, group.noun, 'P2')
                    for j in range(boundary + 1, first):
                        links[j] = Link('prep_part', tokens[j].surface.casefold(), boundary, 'P1')
                    links[noun] = Link('governed', lemma, boundary, 'P1', case)
                    yield group, boundary, links


def trees(tokens, parse, budget, *, inferred=False):
    from .parser import AnalysisBudgetExceeded, Link

    comma = next((i for i in reversed(range(1, len(tokens))) if tokens[i].surface == ','), None)
    if inferred:
        starts = range(1, len(tokens) - 2)
    elif comma is not None:
        starts = (comma + 1,)
    else:
        return
    seen = set()
    for start in starts:
        tail = tuple(_tail(tokens, start, budget))
        if not tail:
            continue
        boundary = start if inferred else comma
        for prefix in parse(tokens[:boundary]):
            adjacent = boundary - 1
            if prefix[adjacent].role not in NOMINAL_ROLES | {'genitive_modifier'}:
                continue
            hosts = []
            i = adjacent
            while i is not None:
                if prefix[i].role in NOMINAL_ROLES | {'genitive_modifier', 'predicate', 'infinitive'}:
                    hosts.append(i)
                i = prefix[i].head
            for group, prep_index, links in tail:
                for lower, host in enumerate(hosts):
                    predicate = prefix[host].role in ('predicate', 'infinitive')
                    role = 'oblique' if predicate else 'measure'
                    measure = Link(role, group.lemma, host, 'N.MEASURE', morphology=group.morphology)
                    completed = {**links, group.noun: measure}
                    if not inferred:
                        completed[comma] = Link('punctuation', ',', group.noun, 'N.MEASURE.COMMA')
                    for prep_host in (group.noun, *hosts[lower:]):
                        completed[prep_index] = Link('preposition', links[prep_index].lemma, prep_host, 'P2')
                        tree = (*prefix, *(completed[j] for j in range(boundary, len(tokens))))
                        if tree not in seen:
                            seen.add(tree)
                            if len(seen) > budget:
                                raise AnalysisBudgetExceeded('DETACHED_MEASURE_BUDGET')
                            yield tree
