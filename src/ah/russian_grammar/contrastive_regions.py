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
