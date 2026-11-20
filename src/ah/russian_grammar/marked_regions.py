from dataclasses import replace
from functools import cache

from . import clauses, detached_measures, relative_clauses
from .morphology import ROLE_CASE, from_tag
from .probe import Probe
from .rules import known_forms


class RelativeChoice(Exception):
    domain = 'relative_host'

    def __init__(self, marker, hosts, tokens, text, *, inferred=False):
        from .parser import _span_label

        self.start = marker
        self.heads = {_span_label(tokens, i): i for i in sorted(hosts)}
        if inferred:
            self.heads['нет такого слова'] = None
        self.probe = Probe(f'Какое слово поясняет придаточная часть от «{tokens[marker].surface}» '
                           f'до конца предложения?', tuple(self.heads), text)


class MeasureChoice(RelativeChoice):
    domain = 'measure_extent'

    def __init__(self, end, starts, tokens, text):
        from .parser import _span_label

        self.start = (self.domain, end)
        self.heads = {_span_label(tokens, i, end): i for i in sorted(starts)}
        self.heads['нет отдельной группы'] = None
        self.probe = Probe('Какие слова здесь образуют отдельную группу меры?', tuple(self.heads), text)


def _has_finite_predicate(tokens):
    return any(all(tag.POS in ('VERB', 'PRTS') for _, tag in forms)
               for token in tokens if (forms := known_forms(token.surface)))


def _matrix(tokens, parse, budget, *, inferred=False):
    from .parser import AnalysisBudgetExceeded

    words = tuple(clauses._key(token.surface) for token in tokens)
    boundaries = [b for b in clauses._boundaries(words) if b.relation == 'conj' and (inferred or b.start != b.marker)]
    if not boundaries:
        if inferred:
            return tuple(detached_measures.trees(tokens, parse, budget, inferred=True))
        return tuple(parse(tokens))
    if not inferred and len(boundaries) != 1:
        return ()
    matrix = {}
    for marker in boundaries:
        parts = (tokens[:marker.start], tokens[marker.stop:])
        if not all(_has_finite_predicate(side) for side in parts):
            continue
        lefts = tuple(parse(parts[0]))
        if inferred:
            lefts = tuple(tree for tree in lefts if any(link.role == 'subject' and tree[link.head].head is None
                                                        for link in tree))
        if not lefts:
            continue
        rights = (detached_measures.trees(parts[1], parse, budget, inferred=True) if inferred else parse(parts[1]))
        for right in rights:
            root = next(i for i, link in enumerate(right) if link.head is None)
            if not any(link.role == 'subject' and link.head == root for link in right):
                continue
            child = marker.stop + root
            shifted = tuple(clauses._shift(link, marker.stop) for link in right)
            for left in lefts:
                head = next(i for i, link in enumerate(left) if link.head is None)
                for tree, _ in clauses._attachments(left, ((head, head),), marker, shifted, child, words):
                    matrix[tree] = None
                    if len(matrix) > budget:
                        raise AnalysisBudgetExceeded('CLAUSE_REGION_BUDGET')
    return tuple(matrix)


def complete(tokens, text, parse, selected, budget):
    from .parser import AnalysisBudgetExceeded, Link

    commas = [i for i, token in enumerate(tokens) if token.surface == ',']
    relative = [i for i, token in enumerate(tokens) if i > 0 and
                any(lemma == 'который' for lemma, _ in known_forms(token.surface))]
    signalled = [i for i in relative if i - 1 in commas]
    possible = signalled or relative
    if len(possible) != 1:
        return ()
    marker, = possible
    marked = bool(signalled)
    inferred = not marked
    if marked and len(commas) < 2:
        return ()
    extent_key = (MeasureChoice.domain, marker)
    if any(key in selected and selected[key] is None for key in (marker, extent_key)):
        return ()
    if marker <= 1 or marker + 1 >= len(tokens):
        return ()
    tail = tokens[marker:]
    finite = [i for i, token in enumerate(tail) if any(tag.POS == 'VERB' for _, tag in known_forms(token.surface))]
    if len(finite) != 1:
        return ()
    matrix_tokens = tokens[:marker - int(marked)]
    if inferred:
        measure_starts = [i for i in range(1, len(matrix_tokens) - 2)
                          if next(detached_measures._tail(matrix_tokens, i, budget), None)]
        if not measure_starts:
            return ()
    matrix = _matrix(matrix_tokens, parse, budget, inferred=inferred)
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
    if not by_host or (not inferred and len(by_host) < 2):
        return ()
    if inferred:
        starts = {}
        for host, variants in by_host.items():
            for variant in variants:
                tree = variant[0]
                for start in measure_starts:
                    number = tree[start]
                    if number.role == 'numeral' and number.head is not None and tree[number.head].rule == 'N.MEASURE':
                        starts.setdefault(start, {}).setdefault(host, []).append(variant)
        if not starts:
            return ()
        if extent_key not in selected:
            raise MeasureChoice(marker, starts, tokens, text)
        by_host = starts[selected[extent_key]]
    if marker not in selected:
        raise RelativeChoice(marker, by_host, tokens, text, inferred=inferred)
    target = selected[marker]
    result = {}
    for tree, variants, tag in by_host[target]:
        for child in variants:
            root = next(i for i, link in enumerate(child) if link.head is None)
            merged = list(tree)
            if marked:
                merged.append(Link('punctuation', ',', marker + root, 'CL.PUNCT'))
            merged.extend(clauses._shift(link, marker) for link in child)
            merged[marker + root] = replace(merged[marker + root], role='clause_relative', rule='CL.REL', head=target)
            merged[marker] = replace(merged[marker], lemma='который', antecedent=target, rule='CL.NOMREF',
                                     case=tag.case, morphology=from_tag(tag))
            result[tuple(merged)] = None
            if len(result) > budget:
                raise AnalysisBudgetExceeded('RELATIVE_REGION_BUDGET')
    return tuple(result)
