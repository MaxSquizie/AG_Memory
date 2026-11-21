from dataclasses import replace

from .morphology import from_tag
from .nominal_entries import _attach, _layouts
from .nominal_groups import _groups
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .passive_arguments import _opaque
from .probe import Probe
from .rules import known_forms, name_type
from .utterances import _map


def _nominals(tokens, budget):
    stop = len(tokens)
    while stop and _opaque(tokens[stop - 1].surface):
        stop -= 1
    if not stop:
        return
    part = tokens[:stop]
    produced = 0
    for seed in _groups(part, 0, budget, bare_cases=('nomn',)):
        head = seed.noun
        links = dict(seed.extra) | {head: Link('predicate', seed.lemma, None, 'N.HEADING', 'nomn', scope='heading')}
        for layout in _layouts(part, seed, {}, budget):
            for tree in _attach(layout, (head,), links):
                produced += 1
                if produced > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_ENTRY_ATTACHMENT_BUDGET')
                if stop == len(tokens):
                    yield head, tree
                    continue
                anchor = tree[-1]
                if not any(lemma == anchor.lemma and tag.case == anchor.case and name_type(tag)
                           for lemma, tag in known_forms(part[-1].surface)):
                    continue
                extra = tuple(Link('name_part', t.surface, stop - 1, 'NAME.HEADING.PART') for t in tokens[stop:])
                yield head, (*tree, *extra)


def _title_spans(tokens, start, quoted):
    if quoted:
        if len(quoted) == 1 and quoted[0][1] == len(tokens) - 1 and quoted[0][0] > start:
            left, right = quoted[0]
            yield left, left + 1, right
        return
    yield len(tokens), len(tokens), len(tokens)
    for i in range(start + 1, len(tokens)):
        if tokens[i].surface.istitle():
            yield i, i, len(tokens)


def trees(tokens, quoted, budget):
    if len(tokens) < 3:
        return
    first = tokens[0].surface
    if not (len(first) == 4 and first.isdecimal() and int(first)):
        return
    for lemma, tag in known_forms(tokens[1].surface):
        if lemma != 'год' or tag.POS != 'NOUN' or tag.case != 'nomn' or tag.number != 'sing':
            continue
        separator = tokens[2].surface in {',', ':', ';'}
        start = 2 + int(separator)
        produced = 0
        for stop, begin, end in _title_spans(tokens, start, quoted):
            for head, body in _nominals(tokens[start:stop], budget):
                records = ((None, ()),) if begin == end else _nominals(tokens[begin:end], budget)
                for title, phrase in records:
                    produced += 1
                    if produced > budget:
                        raise AnalysisBudgetExceeded('DATED_HEADING_BUDGET')
                    item = start + head
                    links = _map(body, range(start, stop))
                    links[item] = replace(links[item], role='list_item', rule='N.HEADING.ITEM', head=1)
                    links[1] = Link('predicate', lemma, None, 'N.HEADING', 'nomn', scope='heading', morphology=from_tag(tag))
                    links[0] = Link('attribute', first, 1, 'NUM.UNMARKED.ORDINAL', 'nomn', quantity=first, quantity_kind='ordinal')
                    if separator:
                        links[2] = Link('punctuation', tokens[2].surface, item, 'N.HEADING.SEP')
                    if title is not None:
                        name = begin + title
                        links.update(_map(phrase, range(begin, end)))
                        links[name] = replace(links[name], role='apposition', scope='title', head=item, rule='N.HEADING.TITLE')
                        if stop != begin:
                            for j in (stop, end):
                                links[j] = Link('punctuation', tokens[j].surface, name, 'TITLE.QUOTE')
                    yield tuple(links[i] for i in range(len(tokens)))


def confirmation(tokens, tree, index, text):
    link = tree[index]
    if link.rule == 'N.HEADING.ITEM':
        head = link.head
        date = _span_label(tokens, head - 1, head + 1)
        return Probe(f'Какой заголовок указывает год, к которому отнесена эта запись?', (date,), text)
    if link.rule == 'NAME.HEADING.PART' and index == link.head + 1:
        end = index + 1
        while end < len(tree) and tree[end].rule == link.rule and tree[end].head == link.head:
            end += 1
        return Probe('Какими словами передано одно имя в этой записи?', (_span_label(tokens, link.head, end),), text)
    if link.rule == 'N.HEADING.TITLE':
        from .quote_titles import title_bounds

        first, last = title_bounds(tree, index)
        phrase = text[tokens[first].start:tokens[last].end]
        return Probe('Какие слова образуют отдельное название в этой записи?', (phrase,), text)
    return None
