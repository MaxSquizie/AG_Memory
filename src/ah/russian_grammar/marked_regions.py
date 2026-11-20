from dataclasses import replace
from functools import cache

from . import clauses, relative_clauses
from .morphology import ROLE_CASE, from_tag
from .probe import Probe
from .rules import known_forms


class RelativeChoice(Exception):
    def __init__(self, marker, hosts, tokens, text):
        from .parser import _span_label

        self.start = marker
        self.heads = {_span_label(tokens, i): i for i in sorted(hosts)}
        self.probe = Probe(f'Какое слово поясняет придаточная часть от «{tokens[marker].surface}» '
                           f'до конца предложения?', tuple(self.heads), text)


def _matrix(tokens, parse, budget):
    from .parser import AnalysisBudgetExceeded

    words = tuple(clauses._key(token.surface) for token in tokens)
    boundaries = [b for b in clauses._boundaries(words) if b.relation == 'conj' and b.start != b.marker]
    if not boundaries:
        return tuple(parse(tokens))
    if len(boundaries) != 1:
        return ()
    marker, = boundaries
    for side in (tokens[:marker.start], tokens[marker.stop:]):
        if not any(forms and all(tag.POS in ('VERB', 'PRTS') for _, tag in forms)
                   for token in side if (forms := known_forms(token.surface))):
            return ()
    lefts = tuple(parse(tokens[:marker.start]))
    rights = tuple(parse(tokens[marker.stop:]))
    matrix = {}
    for left in lefts:
        head = next(i for i, link in enumerate(left) if link.head is None)
        for right in rights:
            root = next(i for i, link in enumerate(right) if link.head is None)
            if not any(link.role == 'subject' and link.head == root for link in right):
                continue
            child = marker.stop + root
            shifted = tuple(clauses._shift(link, marker.stop) for link in right)
            for tree, _ in clauses._attachments(left, ((head, head),), marker, shifted, child, words):
                matrix[tree] = None
                if len(matrix) > budget:
                    raise AnalysisBudgetExceeded('CLAUSE_REGION_BUDGET')
    return tuple(matrix)


def complete(tokens, text, parse, selected, budget):
    from .parser import AnalysisBudgetExceeded, Link

    commas = [i for i, token in enumerate(tokens) if token.surface == ',']
    relative = [i + 1 for i in commas if i + 1 < len(tokens)
                and any(lemma == 'который' for lemma, _ in known_forms(tokens[i + 1].surface))]
    if len(relative) != 1 or len(commas) < 2:
        return ()
    marker, = relative
    if marker <= 1 or marker + 1 >= len(tokens):
        return ()
    tail = tokens[marker:]
    finite = [i for i, token in enumerate(tail) if any(tag.POS == 'VERB' for _, tag in known_forms(token.surface))]
    if len(finite) != 1:
        return ()
    matrix = _matrix(tokens[:marker - 1], parse, budget)
    if not matrix:
        return ()

    @cache
    def inside(surface):
        return tuple(parse((replace(tail[0], surface=surface), *tail[1:])))

    by_host = {}

    @cache
    def children(word, lemma, case):
        return tuple(child for child in inside(word) if child[0].lemma == lemma and
                     (child[0].case or ROLE_CASE.get(child[0].role)) == case)

    for tree in matrix:
        for host in relative_clauses._anchors(tree, len(tree)):
            projections = relative_clauses._projections(tokens[host], tree[host], tokens[marker])
            for word, tag in dict.fromkeys(projections):
                valid = children(word, tree[host].lemma, tag.case)
                if valid:
                    by_host.setdefault(host, []).append((tree, valid, tag))
    if len(by_host) < 2:
        return ()
    if marker not in selected:
        raise RelativeChoice(marker, by_host, tokens, text)
    target = selected[marker]
    result = {}
    for tree, variants, tag in by_host[target]:
        for child in variants:
            root = next(i for i, link in enumerate(child) if link.head is None)
            merged = [*tree, Link('punctuation', ',', marker + root, 'CL.PUNCT'),
                      *(clauses._shift(link, marker) for link in child)]
            merged[marker + root] = replace(merged[marker + root], role='clause_relative', rule='CL.REL', head=target)
            merged[marker] = replace(merged[marker], lemma='который', antecedent=target, rule='CL.NOMREF',
                                     case=tag.case, morphology=from_tag(tag))
            result[tuple(merged)] = None
            if len(result) > budget:
                raise AnalysisBudgetExceeded('RELATIVE_REGION_BUDGET')
    return tuple(result)
