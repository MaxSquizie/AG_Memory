from dataclasses import replace

from .morphology import NOMINAL_ROLES, ROLE_CASE, from_tag
from .nominal_groups import _agree, _members
from .parser import Link
from .participle_connectives import relations
from .relative_clauses import _anchors
from .rules import known_forms
from .short_participles import _predicative_instrumentals
from .utterances import _map


def joins(tokens):
    for i, token in enumerate(tokens):
        if 'contrast' in relations(token.surface):
            comma = i > 0 and tokens[i - 1].surface == ','
            yield i - int(comma), i


def _join(tokens, links, start, marker, host):
    if start < marker:
        links[start] = Link('punctuation', tokens[start].surface, host, 'CL.PUNCT')
    links[marker] = Link('coordinator', tokens[marker].surface.casefold(), host, 'C1')


def attributes(tokens, parse):
    boundaries = tuple(joins(tokens))
    for (left, first), (middle, second) in zip(boundaries, boundaries[1:]):
        if not left or first + 3 != middle or second + 2 != len(tokens):
            continue
        neg, a, b = first + 1, first + 2, second + 1
        if tokens[neg].surface.casefold() != 'не':
            continue
        for tree in parse(tokens[:left]):
            for host in _anchors(tree, left):
                nominal = tree[host]
                if nominal.role not in NOMINAL_ROLES | {'genitive_modifier'}:
                    continue
                case = nominal.case or ROLE_CASE.get(nominal.role)
                nouns = [tag for lemma, tag in known_forms(tokens[host].surface)
                         if lemma == nominal.lemma and tag.POS in ('NOUN', 'NPRO') and tag.case == case]
                for lemma, form in known_forms(tokens[a].surface):
                    if form.POS not in ('PRTF', 'ADJF'):
                        continue
                    for other, adj in known_forms(tokens[b].surface):
                        if adj.POS not in ('PRTF', 'ADJF') or not any(
                                _agree(form, noun) and _agree(adj, noun) for noun in nouns):
                            continue
                        links = dict(enumerate(tree))
                        _join(tokens, links, left, first, a)
                        _join(tokens, links, middle, second, b)
                        links[neg] = Link('particle', 'не', a, 'MOD.NEG')
                        participle = form.POS == 'PRTF'
                        links[a] = Link('participle' if participle else 'attribute', lemma, host, 'MOD.CONTRAST',
                                        form.case, controller=host if participle else None, scope='negated',
                                        morphology=from_tag(form))
                        links[b] = Link('attribute_conjunct', other, a, 'MOD.CONTRAST', adj.case,
                                        scope='correction', morphology=from_tag(adj))
                        yield tuple(links[i] for i in range(len(tokens)))


def predicates(tokens, parse):
    for end, marker in joins(tokens):
        for neg in range(1, end):
            if tokens[neg].surface.casefold() != 'не':
                continue
            indices = tuple(j for j in range(end) if j != neg)
            for left in parse(tuple(tokens[j] for j in indices)):
                base = _map(left, indices)
                for first, nominal in base.items():
                    if first <= neg or nominal.case != 'ablt' or nominal.head is None:
                        continue
                    if base[nominal.head].lemma not in _predicative_instrumentals():
                        continue
                    if any(base[j].role != 'attribute' or base[j].head != first for j in range(neg + 1, first)):
                        continue
                    for head, lemma, case, attrs in _members(tokens, marker + 1, None, 'ablt'):
                        if head + 1 != len(tokens):
                            continue
                        links = {**base, **dict(attrs)}
                        links[first] = replace(nominal, role='predicative_complement', scope='focus_negated')
                        links[neg] = Link('particle', 'не', first, 'MOD.NEG')
                        links[head] = Link('nominal_conjunct', lemma, first, 'N.COORD', case, scope='correction')
                        _join(tokens, links, end, marker, head)
                        yield tuple(links[j] for j in range(len(tokens)))


def nominal_remnants(tokens, parse, budget):
    from .determiners import with_agreeing_determiners
    from .nominal_groups import _groups, _prepositions
    from .parser import AnalysisBudgetExceeded
    from .prepositions import DASHES

    def endings(part, case):
        for group in _groups(part, 0, budget, bare_cases=(case,)):
            if group.end != len(part):
                continue
            links = dict(group.extra)
            links[group.noun] = Link('nominal_conjunct', group.lemma, None, 'ELL.COORD', case)
            yield tuple(links[i] for i in range(len(part)))

    for start, marker in joins(tokens):
        if not start:
            continue
        prep_start = marker + 1
        for first, prep in _prepositions(tokens, prep_start):
            for noun, lemma, case, attrs in _members(tokens, first, prep):
                dash = noun + 1
                if dash >= len(tokens) - 1 or tokens[dash].surface not in DASHES:
                    continue
                suffix = tokens[dash + 1:]
                tails = {}
                seen = set()
                for tree in parse(tokens[:start]):
                    roots = [i for i, link in enumerate(tree) if link.head is None and link.role == 'predicate']
                    if len(roots) != 1 or any(link.role.startswith('clause_') for link in tree):
                        continue
                    for host in range(roots[0] + 1, start):
                        l = tree[host]
                        if l.role not in NOMINAL_ROLES | {'genitive_modifier'}:
                            continue
                        hcase = l.case or ROLE_CASE.get(l.role)
                        if not hcase:
                            continue
                        if hcase not in tails:
                            tails[hcase] = tuple(with_agreeing_determiners(suffix, lambda p: endings(p, hcase),
                                                                         include_bare=True))
                        for tail in tails[hcase]:
                            kept = range(dash + 1, len(tokens))
                            links = dict(enumerate(tree)) | _map(tail, kept)
                            head = next(j for j in kept if links[j].head is None)
                            links[head] = replace(links[head], head=host)
                            _join(tokens, links, start, marker, head)
                            links[dash] = Link('punctuation', tokens[dash].surface, head, 'ELL.PUNCT')
                            links[prep_start] = Link('preposition', prep, head, 'ELL.REMNANT.PP',
                                                     scope='elliptical')
                            links.update((j, Link('prep_part', tokens[j].surface.casefold(), prep_start, 'P1'))
                                         for j in range(prep_start + 1, first))
                            links.update(attrs)
                            links[noun] = Link('governed', lemma, prep_start, 'P1', case)
                            result = tuple(links[j] for j in range(len(tokens)))
                            if result in seen:
                                continue
                            if len(seen) >= budget:
                                raise AnalysisBudgetExceeded('ELLIPSIS_BUDGET')
                            seen.add(result)
                            yield result
