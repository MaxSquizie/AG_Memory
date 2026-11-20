from dataclasses import replace
from itertools import chain

from .homogeneous import _restore
from .morphology import PREDICATE_ROLES
from .nominal_groups import _groups
from .participle_connectives import PAIRS, openers


_OPENING_WORDS = frozenset(key.split()[0] for key in PAIRS)


def _plans(tokens):
    words = tuple(t.surface.casefold() for t in tokens)
    for i, word in enumerate(words):
        if word not in _OPENING_WORDS:
            continue
        choices = list(openers(tokens[i:i + 2]))
        opening, width = max(choices, key=lambda choice: choice[1])
        if opening:
            for closing, relation in PAIRS[opening].items():
                phrase = tuple(closing.split())
                markers = []
                for j in range(i + width + 1, len(tokens) - len(phrase)):
                    if words[j:j + len(phrase)] != phrase:
                        continue
                    marker = tuple(range(j, j + len(phrase)))
                    if closing == opening:
                        markers.append(marker)
                    yield tuple(range(i, i + width)), tuple(markers) if closing == opening else (marker,), relation


def has_opening(tokens):
    return next(_plans(tokens), None) is not None


def comma_head(tree, left, right):
    link = tree[left]
    if link.rule == 'PAIR.PART':
        lead = tree[link.head]
        if right in (link.head, lead.head):
            return right
    if link.rule == 'PAIR.MARK' and (link.head == right or tree[right].head == left):
        return left
    if link.role == 'nominal_conjunct' and any(x.rule == 'PAIR.MARK' and x.head == left for x in tree):
        governor = _governor(tree, left)
        if governor == right or (tree[right].role == 'particle' and tree[right].head == governor):
            return governor
    return None


def _nominal_series(tokens, start, markers, parse, budget, nearest):
    from .morphology import NOMINAL_ROLES, ROLE_CASE
    from .parser import Link

    cases = ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct')
    for group in _groups(tokens, start, budget, bare_cases=cases):
        members = [(i, link) for i, link in group.extra if link.role == 'nominal_conjunct']
        joins = tuple(i for i, link in group.extra if link.role == 'coordinator')
        if joins != markers:
            continue
        last, member = members[-1]
        nearest_subject = group.case == 'nomn'
        if nearest_subject and not nearest:
            continue
        pivot, lemma = (last, member.lemma) if nearest_subject else (group.noun, group.lemma)
        kept = (*range(start), pivot, *range(group.end, len(tokens)))
        for tree in parse(tuple(tokens[j] for j in kept)):
            host = tree[start]
            case = host.case or ROLE_CASE.get(host.role) or getattr(host.morphology, 'case', None)
            if host.role not in NOMINAL_ROLES or host.lemma != lemma or case != group.case:
                continue
            if nearest_subject and (host.role != 'subject' or host.head <= start):
                continue
            restored = _restore(tree, kept, len(tokens))
            if nearest_subject:
                restored[group.noun] = Link('subject', group.lemma, restored[pivot].head, 'S1', case='nomn')
            for j, link in group.extra:
                restored[j] = link
            yield tuple(restored)


def _governor(tree, index):
    while index is not None and tree[index].role not in PREDICATE_ROLES | {'infinitive', 'participle'}:
        index = tree[index].head
    return index


def _belongs(tree, index, head):
    while index is not None and index != head:
        index = tree[index].head
    return index == head


def _first_member(tree, start, close, second):
    right = tree[second]
    for i in range(start, close):
        left = tree[i]
        if right.role in ('nominal_conjunct', 'clause_conjunct') and right.head == i:
            return i
        if right.role in ('subject', 'object', 'attribute', 'infinitive') and left.role == right.role and left.head == right.head:
            return i
    return None


def trees(tokens, parse, budget):
    from .parser import AnalysisBudgetExceeded, Link

    attempts = 0
    for opening, closings, relation in _plans(tokens):
        attempts += 1
        if attempts > budget:
            raise AnalysisBudgetExceeded('COORDINATION_BUDGET')
        removed = set(opening)
        for marker in closings:
            removed.update(marker[1:])
            if tokens[marker[0] - 1].surface == ',':
                removed.add(marker[0] - 1)
        kept = tuple(i for i in range(len(tokens)) if i not in removed)
        starts = {marker[0] for marker in closings}
        projected = tuple(replace(tokens[i], surface='и') if i in starts else tokens[i] for i in kept)
        markers = tuple(i for i, j in enumerate(kept) if j in starts)
        left = opening[0]
        nearest = len(opening) > 1 or relation == 'alternative'
        variants = chain(parse(projected), _nominal_series(projected, left, markers, parse, budget, nearest))
        for tree in variants:
            if any(tree[i].role not in ('coordinator', 'clause_marker') or tree[i].head is None for i in markers):
                continue
            seconds = [tree[i].head for i in markers]
            first = _first_member(tree, left, markers[0], seconds[0])
            if first is None or any(_first_member(tree, first, markers[0], second) != first for second in seconds):
                continue
            members = (first, *seconds)
            if not all(_belongs(tree, i, first) for i in range(left, markers[0])):
                continue
            if relation == 'negative_coordination' and not all(
                    (host := _governor(tree, i)) is not None and 'negated' in (tree[host].scope or '').split('_')
                    for i in members):
                continue
            links = _restore(tree, kept, len(tokens))
            for marker, member in zip((opening, *closings), members):
                host = kept[member]
                lead = marker[0]
                role = 'clause_marker' if tree[member].role == 'clause_conjunct' else 'coordinator'
                links[lead] = Link(role, tokens[lead].surface.casefold(), host, 'PAIR.MARK', scope=relation)
                for j in marker[1:]:
                    links[j] = Link('coordinator_part', tokens[j].surface.casefold(), lead, 'PAIR.PART')
                if marker != opening and tree[member].role == tree[first].role == 'object':
                    links[host] = replace(links[host], role='nominal_conjunct', head=kept[first], rule='P.COORD',
                                          case=tree[member].case or 'accs')
                if marker != opening and tokens[lead - 1].surface == ',':
                    links[lead - 1] = Link('punctuation', ',', host, 'PAIR.COMMA')
                if relation in ('alternative', 'comparison'):
                    inner = links[host].scope
                    links[host] = replace(links[host], scope=f'{relation}_{inner}' if inner else relation)
            yield tuple(links)
