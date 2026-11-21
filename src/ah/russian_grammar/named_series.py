from dataclasses import dataclass, replace
from functools import cache, lru_cache

from .morphology import NOMINAL_ROLES, PREDICATE_ROLES, ROLE_CASE
from .named_arguments import opaque_cases
from .nominal_groups import Group, _markers, _members, _names, _prepositions
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .prepositions import DASHES, GOVERNMENT
from .probe import Probe
from .numerals import expressions
from .quantity_groups import _groups as quantity_groups
from .rules import known_forms, name_type
from .utterances import _map, _root


@dataclass(frozen=True)
class Member:
    stop: int
    noun: int
    lemma: str
    case: str
    links: tuple


@lru_cache(maxsize=2048)
def _person(surface):
    if not surface.istitle():
        return ()
    return tuple((lemma, tag) for lemma, tag in known_forms(surface)
                 if tag.POS == 'NOUN' and name_type(tag) and tag.number == 'sing')


def _named(tokens, noun, lemma, case, attrs):
    first = noun + 1
    if first >= len(tokens):
        return
    for name, form in _person(tokens[first].surface):
        if form.case != case:
            continue
        seed = Group(first, first + 1, None, first, name, case, ())
        groups = (seed, *_names(tokens, seed))
        for group in groups:
            entries = (*attrs, (first, Link('apposition', name, noun, 'NAME.APPOS', case)), *group.extra)
            yield Member(group.end, noun, lemma, case, entries)
            end = group.end
            if any(other.end == end + 1 and other.extra[:-1] == group.extra for other in groups):
                continue
            if (end < len(tokens) and tokens[end].surface.istitle() and tokens[end].surface.isalpha()
                    and not known_forms(tokens[end].surface)):
                part = Link('name_part', tokens[end].surface.casefold(), first, 'OPAQUE.NAME.CONTINUATION')
                yield Member(end + 1, noun, lemma, case, (*entries, (end, part)))


def _numeric_note(tokens, member):
    start = member.stop
    enclosed = start < len(tokens) and tokens[start].surface == '('
    i = start + int(enclosed)
    if i + 2 >= len(tokens):
        return
    left, mark, right = tokens[i:i + 3]
    if not (left.surface.isdecimal() and right.surface.isdecimal() and mark.surface in DASHES
            and left.end == mark.start and mark.end == right.start):
        return
    end = i + 3
    if enclosed and (end >= len(tokens) or tokens[end].surface != ')'):
        return
    links = [(i, Link('apposition', left.surface, member.noun, 'NUM.NOTE', quantity=left.surface,
                      quantity_kind='cardinal')),
             (i + 1, Link('punctuation', mark.surface, i, 'NUM.SEP')),
             (i + 2, Link('numeral_part', right.surface, i, 'NUM.NOTE.PART', quantity=right.surface,
                          quantity_kind='cardinal'))]
    if enclosed:
        links.extend((j, Link('punctuation', tokens[j].surface, i, 'NUM.BOUND')) for j in (start, end))
    yield replace(member, stop=end + int(enclosed), links=(*member.links, *links))


def _qualified_members(tokens, start, case):
    yield from _members(tokens, start, None, case)
    i = start
    while i + 2 < len(tokens) and any(tag.POS == 'ADJF' for _, tag in known_forms(tokens[i].surface)):
        i += 1
        if tokens[i].surface != ',':
            continue
        kept = (*range(i), *range(i + 1, len(tokens)))
        for noun, lemma, reading, attrs in _members(tuple(tokens[j] for j in kept), start, None, case):
            if noun < i or not any(j == i - 1 for j, _ in attrs):
                continue
            head = kept[noun]
            links = tuple((kept[j], replace(link, head=head)) for j, link in attrs)
            yield head, lemma, reading, (*links, (i, Link('punctuation', ',', head, 'PUNCT')))
        break


def _members_at(tokens, start, case):
    for noun, word, grammatical_case, attrs in _qualified_members(tokens, start, case):
        if not any(lemma == word and tag.POS == 'NOUN' and tag.case == grammatical_case
                   and tag.animacy == 'anim' and not name_type(tag) for lemma, tag in known_forms(tokens[noun].surface)):
            continue
        for member in _named(tokens, noun, word, grammatical_case, attrs):
            yield member
            yield from _numeric_note(tokens, member)


def _series(tokens, start, members_at, budget):
    pending = [(first, False, False) for first in members_at(start, None)]
    examined = 0
    while pending:
        current, unmarked, coordinated = pending.pop()
        examined += 1
        if examined > budget:
            raise AnalysisBudgetExceeded('NAMED_SERIES_BUDGET')
        if not unmarked or coordinated:
            yield current
        i = current.stop
        comma = i < len(tokens) and tokens[i].surface == ','
        j = i + int(comma)
        markers = list(_markers(tokens, j))
        markers.append(())
        for marker in markers:
            begin = marker[-1] + 1 if marker else j
            for other in members_at(begin, current.case):
                additions = list(other.links)
                additions.append((other.noun, Link('nominal_conjunct', other.lemma, current.noun,
                                                    'N.COORD', other.case)))
                if comma:
                    additions.append((i, Link('punctuation', ',', other.noun, 'P.COORD')))
                for k in marker:
                    head = other.noun if k == marker[0] else marker[0]
                    additions.append((k, Link('coordinator' if k == marker[0] else 'coordinator_part',
                                              tokens[k].surface.casefold(), head, 'P.COORD')))
                expanded = replace(current, stop=other.stop, links=(*current.links, *additions))
                pending.append((expanded, unmarked or not (marker or comma), coordinated or bool(marker)))


def _attachment_heads(links, start, root):
    if start == 0:
        yield root
        return
    index = start - 1
    while index is not None:
        link = links[index]
        if link.role in PREDICATE_ROLES | {'infinitive', 'converb'}:
            yield index
            return
        if link.role in NOMINAL_ROLES | {'genitive_modifier', 'apposition'}:
            yield index
        index = link.head


def _designations(tokens, parse, budget):
    from .dated_clauses import calendar_day

    for i in range(1, len(tokens)):
        number = tokens[i].surface
        if not number.isdecimal() or calendar_day(tokens, i) is not None:
            continue
        dash = tokens[i - 1].surface in DASHES
        head = i - 1 - int(dash)
        if head < 0:
            continue
        word = tokens[head]
        if not (word.surface.istitle() or dash and word.end == tokens[head + 1].start):
            continue
        if not dash and any(next(quantity_groups(tokens, i, expression, budget), None) is not None
                            for expression in expressions(tokens, i)):
            continue
        extras = {i: Link('designation', number, head, 'NUM.LABEL')}
        if dash:
            extras[head + 1] = Link('punctuation', tokens[head + 1].surface, head, 'NUM.LABEL.BOUND')
        known = any(tag.POS == 'NOUN' for _, tag in known_forms(word.surface))
        if known:
            kept = (*range(head + 1), *range(i + 1, len(tokens)))
            for tree in parse(tuple(tokens[j] for j in kept)):
                if tree[head].role in NOMINAL_ROLES | {'genitive_modifier', 'apposition'}:
                    links = _map(tree, kept) | extras
                    yield tuple(links[k] for k in range(len(tokens)))
            continue
        cases = opaque_cases(word.surface)
        if not cases:
            continue
        for start in range(head):
            for first, prep in _prepositions(tokens, start):
                if first != head:
                    continue
                yield from _attach_governed(tokens, parse, start, prep, head, i + 1, cases, extras)


def _attach_governed(tokens, parse, start, prep, head, end, cases, extras):
    allowed = cases.intersection(GOVERNMENT.get(prep, ()))
    kept = (*range(start), *range(end, len(tokens)))
    if not allowed or not kept:
        return
    for tree in parse(tuple(tokens[j] for j in kept)):
        links = _map(tree, kept)
        root = kept[_root(tree)]
        if links[root].role not in PREDICATE_ROLES:
            continue
        for host in _attachment_heads(links, start, root):
            pp = {start: Link('preposition', prep, host, 'P2')}
            for k in range(start + 1, head):
                pp[k] = Link('prep_part', tokens[k].surface.casefold(), start, 'P1')
            for case in sorted(allowed):
                pp[head] = Link('governed', tokens[head].surface, start, 'OPAQUE.GOVERNED.NAME', case)
                completed = links | pp | extras
                yield tuple(completed[k] for k in range(len(tokens)))


def _governed_names(tokens, parse, budget):
    candidates = 0
    for start in range(len(tokens)):
        for head, prep in _prepositions(tokens, start):
            if head >= len(tokens) or not opaque_cases(tokens[head].surface):
                continue
            parts = {}
            for tail in range(head + 1, len(tokens)):
                cases = opaque_cases(tokens[tail].surface)
                if not cases:
                    break
                parts[tail] = Link('name_part', tokens[tail].surface, head, 'NAME')
                if not cases.intersection(GOVERNMENT.get(prep, ())):
                    continue
                candidates += 1
                if candidates > budget:
                    raise AnalysisBudgetExceeded('NAMED_SERIES_BUDGET')
                yield from _attach_governed(tokens, parse, start, prep, head, tail + 1, cases, parts)


def initial_name_groups(tokens, parse, budget):
    from .rules import dictionary

    pending = [(0, {})]
    examined = 0
    while pending:
        start, prefix = pending.pop()
        if prefix and start < len(tokens):
            for tree in parse(tokens[start:]):
                root = start + _root(tree)
                links = _map(tree, range(start, len(tokens)))
                for i, link in prefix.items():
                    links[i] = replace(link, head=root) if link.role == 'preposition' else link
                yield tuple(links[i] for i in range(len(tokens)))
        for first, prep in _prepositions(tokens, start):
            if first + 1 >= len(tokens):
                continue
            head = tokens[first].surface
            if not head.istitle() or any(tag.POS == 'NOUN' for _, tag in known_forms(head)):
                continue
            cases = frozenset(GOVERNMENT.get(prep, ()))
            for i in range(first + 1, len(tokens)):
                word = tokens[i].surface
                if not word.isalpha() or known_forms(word):
                    break
                forms = dictionary().parse(word)
                if not word.istitle() and not any(p.tag.POS == 'NOUN' and p.tag.case in cases for p in forms):
                    break
                if not word.istitle() and i != first + 1:
                    break
                for case in sorted(cases.intersection(p.tag.case for p in forms if p.tag.POS == 'NOUN')):
                    links = dict(prefix)
                    links[start] = Link('preposition', prep, None, 'P2')
                    for j in range(start + 1, first):
                        links[j] = Link('prep_part', tokens[j].surface.casefold(), start, 'P1')
                    links[first] = Link('governed', head, start, 'OPAQUE.GOVERNED.NAME', case)
                    for j in range(first + 1, i + 1):
                        links[j] = Link('name_part', tokens[j].surface, first, 'NAME')
                    end = i + 1
                    if end < len(tokens) and tokens[end].surface == ',':
                        links[end] = Link('punctuation', ',', first, 'PP.SEP')
                        end += 1
                    pending.append((end, links))
                    examined += 1
                    if examined > budget:
                        raise AnalysisBudgetExceeded('NAMED_SERIES_BUDGET')


def trees(tokens, parse, budget):
    yield from _governed_names(tokens, parse, budget)
    if any(t.surface.isdecimal() for t in tokens):
        yield from _designations(tokens, parse, budget)
    if not any(_person(token.surface) for token in tokens):
        return

    @cache
    def members_at(start, case):
        return tuple(dict.fromkeys(_members_at(tokens, start, case)))

    @cache
    def bases(kept):
        part = tuple(tokens[i] for i in kept)
        result = []
        for generate in (parse(part), _designations(part, parse, budget)):
            for tree in generate:
                result.append(tree)
                if len(result) > budget:
                    raise AnalysisBudgetExceeded('NAMED_SERIES_BUDGET')
        return result

    for start in range(len(tokens)):
        for group in _series(tokens, start, members_at, budget):
            kept = (*range(start), group.noun, *range(group.stop, len(tokens)))
            for tree in bases(kept):
                head = tree[start]
                case = head.case or ROLE_CASE.get(head.role)
                if head.lemma != group.lemma or case != group.case:
                    continue
                links = _map(tree, kept)
                links.update(group.links)
                yield tuple(links[i] for i in range(len(tokens)))


def confirmation(tokens, tree, i, text):
    link = tree[i]
    if link.rule == 'NUM.NOTE':
        span = text[tokens[i].start:tokens[i + 2].end]
        host = _span_label(tokens, link.head)
        return Probe(f'Какое сочетание здесь служит числовой пометой к слову «{host}»?', (span,), text)
    if link.rule == 'NUM.LABEL':
        host = _span_label(tokens, link.head)
        return Probe(f'Какое число входит в обозначение вместе со словом «{host}»?', (_span_label(tokens, i),), text)
    if link.rule == 'OPAQUE.GOVERNED.NAME':
        prep = _span_label(tokens, link.head)
        end = i + 1
        while end < len(tree) and tree[end].role == 'name_part' and tree[end].head == i:
            end += 1
        if end > i + 1:
            return Probe(f'Какие слова вместе образуют имя, к которому относится предлог «{prep}»?',
                         (_span_label(tokens, i, end),), text)
        return Probe(f'Какое слово управляется предлогом «{prep}»?', (_span_label(tokens, i),), text)
    return None
