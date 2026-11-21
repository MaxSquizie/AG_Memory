from dataclasses import replace

from .nominal_groups import _markers, _members, _prepositions
from .numerals import expressions
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .participle_connectives import relations
from .prepositions import DASHES
from .probe import Probe
from .quote_titles import spans
from .rules import known_forms


def _seeds(tokens, start):
    for head, lemma, case, attrs in _members(tokens, start, None, 'nomn'):
        yield head + 1, head, dict(attrs) | {head: Link('predicate', lemma, None, 'V2', case)}
    for number in expressions(tokens, start):
        parts = number.parts_for('nomn')
        if not parts or not any(_prepositions(tokens, number.end)):
            continue
        lemma, form = parts[0]
        links = {start: Link('predicate', lemma, None, 'V2.PARTITIVE', 'nomn', morphology=form,
                             quantity=number.value, quantity_kind=number.kind)}
        for j, (lemma, form) in enumerate(parts[1:], start + 1):
            links[j] = Link('numeral_part', lemma, start, 'NUM.PART', morphology=form)
        yield number.end, start, links


def _items(tokens, start, quotes, budget):
    pending = [(stop, head, (head,), links) for stop, head, links in _seeds(tokens, start)]
    while pending:
        stop, root, hosts, links = pending.pop()
        partitive = links[root].rule == 'V2.PARTITIVE' and hosts == (root,)
        if not partitive:
            yield stop, root, links
        if stop == len(tokens):
            continue
        for j, host in enumerate(hosts):
            for head, lemma, case, attrs in (() if partitive else _members(tokens, stop, None, 'gent')):
                group = dict(attrs) | {head: Link('genitive_modifier', lemma, host, 'N.GEN', case)}
                pending.append((head + 1, root, (*hosts[:j + 1], head), links | group))
            for first, prep in _prepositions(tokens, stop):
                for head, lemma, case, attrs in _members(tokens, first, prep):
                    group = dict(attrs)
                    for k in range(stop, first):
                        group[k] = (Link('preposition', prep, host, 'P2') if k == stop else
                                    Link('prep_part', tokens[k].surface.casefold(), stop, 'P1'))
                    group[head] = Link('governed', lemma, stop, 'P1', case)
                    pending.append((head + 1, root, (*hosts[:j + 1], head), links | group))
        host = hosts[-1]
        quoted = quotes.get(stop) == stop + 2
        if not partitive and (quoted or (tokens[stop].surface.isalpha() and not known_forms(tokens[stop].surface))):
            title = stop + int(quoted)
            group = {title: Link('apposition', tokens[title].surface.casefold(), host, 'APP.LABEL')}
            if quoted:
                for k in (stop, stop + 2):
                    group[k] = Link('punctuation', tokens[k].surface, title, 'TITLE.QUOTE')
            yield title + 1 + int(quoted), root, links | group
        if (stop + 2 < len(tokens) and tokens[stop].surface == '(' and tokens[stop + 2].surface == ')'
                and len(tokens[stop + 1].surface) == 4 and tokens[stop + 1].surface.isdecimal()
                and int(tokens[stop + 1].surface) > 0):
            year = tokens[stop + 1].surface
            for host in hosts:
                note = {stop + 1: Link('nominal_date', year, host, 'DATE.NOTE.YEAR',
                                       quantity=year, quantity_kind='ordinal')}
                for j in (stop, stop + 2):
                    note[j] = Link('punctuation', tokens[j].surface, stop + 1, 'NAME.NOTE.BOUND')
                yield stop + 3, root, links | note
        if len(pending) > budget:
            raise AnalysisBudgetExceeded('PREDICATE_LIST_BUDGET')


def _subjects(tokens):
    from . import dated_name_notes

    yield from dated_name_notes.prefixes(tokens)
    for stop, links in dated_name_notes._first_name(tokens):
        if stop > 1 and stop < len(tokens) and tokens[stop].surface in DASHES:
            dash = Link('punctuation', tokens[stop].surface, 0, 'V2.DASH')
            yield stop + 1, links | {stop: dash}, 0
    for head, lemma, case, attrs in _members(tokens, 0, None, 'nomn'):
        dash = head + 1
        if dash < len(tokens) and tokens[dash].surface in DASHES:
            links = dict(attrs)
            links[head] = Link('subject', lemma, None, 'S1', case)
            links[dash] = Link('punctuation', tokens[dash].surface, head, 'V2.DASH')
            yield dash + 1, links, head


def trees(tokens, parse, budget):
    has_markers = any(next(_markers(tokens, i), None) for i in range(len(tokens)))
    if not has_markers and not any(t.surface.isdecimal() or t.surface == '(' for t in tokens):
        return
    quotes = dict(spans(tokens))
    for start, intro, subject in _subjects(tokens):
        note = any(link.rule.startswith(('DATE.', 'NAME.FORM.')) for link in intro.values())
        if not note and not has_markers:
            continue
        stack = []
        for end, root, group in _items(tokens, start, quotes, budget):
            initial = dict(intro)
            initial[subject] = replace(initial[subject], head=root)
            if initial.get(start - 1) and initial[start - 1].rule == 'V2.DASH':
                initial[start - 1] = replace(initial[start - 1], head=root)
            if end == len(tokens) and note:
                complete = initial | group
                yield tuple(complete[j] for j in range(end))
            else:
                stack.append((end, root, root, False, initial | group))
        while stack:
            i, root, last, coordinated, links = stack.pop()
            if i == len(tokens):
                if coordinated:
                    yield tuple(links[j] for j in range(i))
                continue
            comma = tokens[i].surface in (',', ';')
            boundary = i + int(comma)
            for marker in (tuple(_markers(tokens, boundary)) or ((),)):
                if marker:
                    meanings = relations(' '.join(tokens[j].surface for j in marker))
                    if not meanings or not set(meanings) <= {'addition', 'contrast'}:
                        continue
                following = boundary + len(marker)
                for end, item, group in _items(tokens, following, quotes, budget):
                    anchor = group[item]
                    additions = dict(group)
                    if comma:
                        additions[i] = Link('punctuation', tokens[i].surface, item, 'V2.SEP')
                    for j in marker:
                        additions[j] = Link('coordinator' if j == marker[0] else 'coordinator_part',
                                            tokens[j].surface.casefold(), item if j == marker[0] else marker[0], 'P.COORD')
                    additions[item] = replace(anchor, role='clause_conjunct', rule='V2.CONJ', head=root, controller=subject)
                    stack.append((end, root, item, coordinated or bool(marker), links | additions))
                    if (not marker and last != root and item == following and end == item + 1
                            and any(tag.POS == 'NOUN' for _, tag in known_forms(tokens[item].surface))):
                        additions[item] = replace(anchor, role='apposition', rule='APP.NOMINAL', head=last)
                        stack.append((end, root, item, coordinated, links | additions))
            if len(stack) > budget:
                raise AnalysisBudgetExceeded('PREDICATE_LIST_BUDGET')


def partitions(analyses, tokens, text):
    for i in range(len(tokens)):
        links = [tree[i] for tree in analyses]
        if all(link.rule == 'DATE.NOTE.YEAR' for link in links):
            labels = [_span_label(tokens, link.head) for link in links]
            if len(set(labels)) > 1:
                question = confirmation(tokens, analyses[0], i, text).question
                yield Probe(question, tuple(dict.fromkeys(labels)), text), labels
        if {link.rule for link in links} != {'APP.NOMINAL', 'V2.CONJ'}:
            continue
        hosts = [link.head if link.role == 'apposition' else link.controller for link in links]
        labels = [_span_label(tokens, head) for head in hosts]
        focus = _span_label(tokens, i)
        question = f'Кого именно характеризует слово «{focus}» в этом перечислении?'
        yield Probe(question, tuple(dict.fromkeys(labels)), text), labels


def confirmation(tokens, tree, i, text):
    if tree[i].rule == 'DATE.NOTE.YEAR':
        host = _span_label(tokens, tree[i].head)
        return Probe(f'К какому слову относится год «{tokens[i].surface}» в скобках?', (host,), text)
    if tree[i].rule == 'APP.LABEL':
        host = _span_label(tokens, tree[i].head)
        return Probe(f'Каким словом дано само обозначение после «{host}»?', (_span_label(tokens, i),), text)
    return None
