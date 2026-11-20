from dataclasses import replace
from fractions import Fraction

from .morphology import from_tag
from .numerals import expressions
from .quantity_groups import _groups, _inflect
from .rules import known_forms


_DIRECT = {'subject': 'nomn', 'object': 'accs', 'duration': 'accs'}
_PATTERNS = {}
for code, governed, phrases in (
    ('approximate', False, ('примерно', 'приблизительно', 'ориентировочно', 'приближённо', 'где-то', 'плюс-минус')),
    ('approximate', True, ('около', 'порядка')),
    ('exact', False, ('ровно', 'точно')),
    ('almost', False, ('почти', 'без малого', 'чуть ли не', 'едва ли не')),
    ('negative_concord', False, ('ни',)),
    ('not_exact', False, ('не', 'не ровно', 'не точно')),
    ('just_above', True, ('чуть больше', 'немного больше', 'чуть более')),
    ('just_below', True, ('чуть меньше', 'немного меньше', 'чуть менее')),
    ('at_least', False, ('хотя бы', 'как минимум', 'минимум', 'по меньшей мере', 'не менее чем', 'не меньше чем')),
    ('at_most', False, ('как максимум', 'максимум', 'самое большее', 'не более чем', 'не больше чем')),
    ('at_least', True, ('не менее', 'не меньше')),
    ('at_most', True, ('не более', 'не больше')),
    ('more_than', True, ('более', 'больше', 'свыше')),
    ('less_than', True, ('менее', 'меньше')),
    ('more_than', False, ('более чем', 'больше чем')),
    ('less_than', False, ('менее чем', 'меньше чем')),
):
    for phrase in phrases:
        _PATTERNS[tuple(phrase.replace('ё', 'е').split())] = code, governed

_LENGTHS = sorted({len(key) for key in _PATTERNS}, reverse=True)


def _first(tokens, offset):
    words = tuple(token.surface.casefold().replace('ё', 'е') for token in tokens)
    for start in range(offset, len(tokens)):
        if words[start] == 'от':
            for lower in expressions(tokens, start + 1):
                if lower.end >= len(tokens) or words[lower.end] != 'до':
                    continue
                upper = list(expressions(tokens, lower.end + 1))
                if upper:
                    end = max(expr.end for expr in upper)
                    return start, lower.end + 1, ('range', True), [expr for expr in upper if expr.end == end], lower
        for length in _LENGTHS:
            anchor = start + length
            pattern = words[start:anchor]
            if len(pattern) != length or pattern not in _PATTERNS or anchor >= len(tokens):
                continue
            numeric = [expr for expr in expressions(tokens, anchor)
                       if expr.kind not in ('ordinal', 'both')]
            if pattern == ('ни',):
                numeric = [expr for expr in numeric if expr.kind == 'cardinal' and expr.value == '1' and expr.end == anchor + 1]
            if numeric:
                end = max(expr.end for expr in numeric)
                return start, anchor, _PATTERNS[pattern], [expr for expr in numeric if expr.end == end], None


class UnsupportedRange(Exception):
    pass


def unsupported_scope(tokens):
    words = tuple(token.surface.casefold() for token in tokens)
    for i, word in enumerate(words):
        if word in {'до', 'и', 'или', '-', '–', '—'} and i and i + 1 < len(tokens):
            if next(expressions(tokens, i + 1), None) is None:
                continue
            start = i - 1
            if not any(expr.end == i for expr in expressions(tokens, start)):
                continue
            while start and any(expr.end == i for expr in expressions(tokens, start - 1)):
                start -= 1
            if (word in {'-', '–', '—', 'или'} or
                    start and (words[start - 1], word) in {('с', 'до'), ('между', 'и')}):
                return 'UNSUPPORTED_QUANTITY_RANGE'
        if any(mark in word for mark in '-‐‑'):
            parts = word.replace('‐', '-').replace('‑', '-').split('-')
            if len(parts) == 2 and all(next(expressions((replace(tokens[i], surface=part),)), None)
                                       for part in parts):
                return 'UNSUPPORTED_QUANTITY_RANGE'


def _map(tree, kept):
    return {i: replace(link, **{key: kept[j] for key in ('head', 'controller', 'antecedent')
                                 if (j := getattr(link, key)) is not None})
            for i, link in zip(kept, tree)}


def _mark(links, tokens, start, anchor, modifier, lower=None):
    from .parser import Link

    if lower is not None:
        head = start + 1
        upper = links[anchor]
        parts = lower.parts_for('gent')
        lemma, morph = parts[0]
        for i, link in tuple(links.items()):
            changes = {key: head for key in ('head', 'controller', 'antecedent') if getattr(link, key) == anchor}
            if changes:
                links[i] = replace(link, **changes)
        links[head] = replace(upper, lemma=lemma, morphology=morph, quantity_kind='range',
                              quantity=f'{lower.value}..{upper.quantity}', quantity_modifier=None)
        links[anchor] = Link('numeral_part', upper.lemma, head, 'NUM.PART', morphology=upper.morphology)
        for i, (lemma, morph) in enumerate(parts[1:], head + 1):
            links[i] = Link('numeral_part', lemma, head, 'NUM.PART', morphology=morph)
        for i in (start, anchor - 1):
            links[i] = Link('quantity_modifier', tokens[i].surface.casefold(), head, 'NUM.MOD')
        return tuple(links[i] for i in range(len(tokens)))
    links[anchor] = replace(links[anchor], quantity_modifier=modifier)
    for i in range(start, anchor):
        forms = known_forms(tokens[i].surface)
        lemma = tokens[i].surface.casefold()
        if len({word for word, _ in forms}) == 1:
            lemma = forms[0][0]
        links[i] = Link('quantity_modifier', lemma, anchor, 'NUM.MOD')
    return tuple(links[i] for i in range(len(tokens)))


def _projections(tokens, group, expr):
    word = tokens[group.noun]
    for lemma, tag in known_forms(word.surface):
        if lemma != group.lemma or from_tag(tag) != group.morphology:
            continue
        for number, gender in expr.agreement('gent', tag):
            if gender == 'neut' and tag.gender != 'neut':
                yield 'оно', 'оно', 'nomn'
            elif form := _inflect(word.surface, lemma, tag, 'nomn', number):
                yield form, lemma, 'nomn'
        if form := _inflect(word.surface, lemma, tag, 'accs', tag.number):
            yield form, lemma, 'accs'


def trees(tokens, local, *, budget=256):
    from .parser import AnalysisBudgetExceeded, Link

    def parse(part, depth, offset=0):
        found = _first(part, offset)
        if not found:
            yield from local(part)
            return
        if depth >= budget:
            raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
        start, anchor, (modifier, governed), numeric, lower = found
        if lower is not None:
            kinds = {'cardinal', 'fraction', 'collective'}
            numeric = [expr for expr in numeric if expr.kind in kinds and 'gent' in expr.cases]
            if lower.kind not in kinds or 'gent' not in lower.cases or not numeric:
                raise AnalysisBudgetExceeded('UNSUPPORTED_QUANTITY_RANGE')
            numeric = [expr for expr in numeric if Fraction(lower.value) <= Fraction(expr.value)]
            if not numeric:
                raise AnalysisBudgetExceeded('REVERSED_QUANTITY_RANGE')
        if any(start >= length and tuple(t.surface.casefold().replace('ё', 'е') for t in part[start-length:start])
               in _PATTERNS for length in _LENGTHS):
            raise AnalysisBudgetExceeded('UNSUPPORTED_QUANTITY_SCOPE')
        if not governed:
            kept = (*range(start), *range(anchor, len(part)))
            for tree in parse(tuple(part[i] for i in kept), depth + 1, start):
                links = _map(tree, kept)
                if links[anchor].quantity_kind and not links[anchor].quantity_modifier:
                    yield _mark(links, part, start, anchor, modifier, lower)
            if modifier != 'negative_concord':
                return

        if part[start].surface.casefold() == 'около':
            for tree in parse(part, depth + 1, anchor):
                if tree[start].role == 'preposition' and tree[anchor].role in {'numeral', 'governed'}:
                    yield tree

        for expr in numeric:
            if 'gent' not in expr.cases:
                continue
            groups = [g for g in _groups(part, anchor, expr, budget) if g.case == 'gent']
            choices = []
            for group in groups:
                for surface, lemma, case in _projections(part, group, expr):
                    choices.append((group.noun, surface, lemma, case, group))
            if not groups:
                for surface, lemma, case in (('они', 'они', 'nomn'), ('оно', 'оно', 'nomn'),
                                             ('книгу', 'книга', 'accs')):
                    choices.append((anchor, surface, lemma, case, None))
            for noun, surface, lemma, case, group in dict.fromkeys(choices):
                end = noun + 1 if group else expr.end
                kept = (*range(start), noun, *range(end, len(part)))
                reduced = tuple(replace(part[i], surface=surface) if i == noun else part[i] for i in kept)
                for tree in parse(reduced, depth + 1, start):
                    links = _map(tree, kept)
                    head = links[noun]
                    if modifier == 'negative_concord' and (not group or head.role != 'object'):
                        continue
                    if _DIRECT.get(head.role) != case or head.lemma != lemma:
                        continue
                    if group:
                        links[noun] = replace(head, case=case, lemma=group.lemma, morphology=group.morphology)
                        links.update(group.links)
                    else:
                        parts = expr.parts_for('gent')
                        word, morph = parts[0]
                        links[anchor] = replace(head, case=case, lemma=word, morphology=morph, rule='NUM.ARG',
                                                quantity_kind=expr.kind, quantity=expr.value)
                        for i, (word, morph) in enumerate(parts[1:], anchor + 1):
                            links[i] = Link('numeral_part', word, anchor, 'NUM.PART', morphology=morph)
                    yield _mark(links, part, start, anchor, modifier, lower)

    failure = unsupported_scope(tokens)
    if failure:
        raise UnsupportedRange(failure)
    if not _first(tokens, 0):
        yield from local(tokens)
        return
    seen = set()
    for tree in parse(tokens, 0):
        for numeral in tree:
            if numeral.quantity_modifier != 'negative_concord':
                continue
            host = numeral
            while host.head is not None and host.role not in ('predicate', 'infinitive', 'converb'):
                host = tree[host.head]
            if 'negated' not in (host.scope or '').split('_'):
                break
        else:
            if tree in seen:
                continue
            seen.add(tree)
            if len(seen) > budget:
                raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
            yield tree
