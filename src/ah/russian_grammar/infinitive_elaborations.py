from dataclasses import replace
from itertools import product

from .clauses import _boundaries, _key
from .morphology import from_tag
from .nominal_groups import _markers
from .nominal_mentions import _units
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .participle_connectives import relations
from .probe import Probe
from .quote_titles import spans
from .rules import known_forms
from .utterances import _map, _root


def _forms(tokens, i, pos):
    return [(lemma, form) for lemma, form in known_forms(tokens[i].surface) if form.POS == pos]


def _additive_markers(tokens, start):
    for marker in _markers(tokens, start):
        phrase = ' '.join(tokens[j].surface for j in marker)
        if set(relations(phrase)).intersection({'addition', 'contrast'}):
            yield marker


def _adverbs(tokens, start, end, verb):
    if start == end:
        yield {}
        return
    pending = [(start, None, {})]
    while pending:
        i, last, links = pending.pop()
        if i == end:
            yield links
            continue
        markers = []
        if last is not None:
            mark = i + int(tokens[i].surface == ',')
            markers = [m for m in _additive_markers(tokens, mark) if m[-1] + 1 < end]
        for marker in ((), *markers):
            j = marker[-1] + 1 if marker else i
            for lemma, form in _forms(tokens, j, 'ADVB'):
                primary = links[last].head if marker and links[last].rule == 'ADV.COORD' else last
                added = dict(links)
                if marker:
                    for k in range(i, j):
                        role = 'punctuation' if k < marker[0] else 'coordinator' if k == marker[0] else 'fixed'
                        added[k] = Link(role, tokens[k].surface.casefold(), j if k <= marker[0] else marker[0], 'C1')
                added[j] = Link('adverb', lemma, primary if marker else verb,
                                'ADV.COORD' if marker else 'B1', morphology=from_tag(form))
                pending.append((j + 1, j, added))


def _single(tokens, start, end, host, budget):
    verbs = [i for i in range(start, end) if _forms(tokens, i, 'INFN')]
    if len(verbs) != 1:
        return
    verb, = verbs
    lefts = [(start, None, {})]
    for noun, lemma, tag, attrs in _units(tokens[:verb], start, 'datv', budget):
        lefts.append((noun + 1, noun, {**attrs, noun: Link('experiencer', lemma, verb, 'INF.DAT', 'datv',
                                                            morphology=from_tag(tag))}))
    for left, actor, group in lefts:
        for before, after in product(_adverbs(tokens, left, verb, verb), _adverbs(tokens, verb + 1, end, verb)):
            for lemma, form in _forms(tokens, verb, 'INFN'):
                yield verb, {**group, **before, **after, verb: Link('infinitive', lemma, host, 'INF.CONTENT',
                             controller=actor, scope='embedded', morphology=from_tag(form))}


def _content(tokens, start, end, host, budget):
    stops = [(m[0] - int(m[0] > start and tokens[m[0] - 1].surface == ','), m)
             for i in range(start + 1, end) for m in _additive_markers(tokens, i) if m[-1] + 1 < end]
    pending = [(start, None, {}, ())]
    while pending:
        left, first, links, before = pending.pop()
        for stop, marker in [*stops, (end, ())]:
            if stop <= left:
                continue
            for verb, unit in _single(tokens, left, stop, host, budget):
                result = {**links, **unit}
                if first is not None:
                    result[verb] = replace(result[verb], rule='INF.COORD', head=first,
                                           controller=result[first].controller if result[verb].controller is None
                                           else result[verb].controller)
                    for j in before:
                        role = 'punctuation' if tokens[j].surface == ',' else 'coordinator'
                        result[j] = Link(role, tokens[j].surface.casefold(), verb, 'C1')
                if marker:
                    pending.append((marker[-1] + 1, verb if first is None else first, result,
                                    tuple(range(stop, marker[-1] + 1))))
                else:
                    yield verb if first is None else first, result


def _elaborations(tokens, start, end, budget):
    if start >= end:
        return
    host = start - 1
    left = start + int(tokens[start].surface == ':')
    quote = next(((a, b) for a, b in spans(tokens[left:end]) if a == 0 and b == end - left - 1), None)
    body = left + int(quote is not None)
    stop = end - int(quote is not None)
    for verb, contents in _content(tokens, body, stop, host, budget):
        links = dict(contents)
        if left > start:
            links[start] = Link('punctuation', ':', host, 'INF.SEP')
        if quote:
            for j in (left, end - 1):
                links[j] = Link('punctuation', tokens[j].surface, verb, 'INF.QUOTE')
        yield verb, links


def _relative_bases(tokens, start, end, parse, budget):
    for stop in range(start + 2, end + 1):
        extra = [({}, None)]
        if stop != end:
            extra = [(attrs, (noun, lemma, form)) for noun, lemma, form, attrs
                     in _units(tokens[:end], stop, 'ablt', budget) if noun == end - 1]
        if not extra:
            continue
        for tree in parse(tokens[start:stop]):
            root = start + _root(tree)
            if tree[0].role != 'subject' or tree[0].head != root - start:
                continue
            for attrs, instrument in extra:
                links = {**_map(tree, range(start, stop)), **attrs}
                if instrument:
                    i, lemma, tag = instrument
                    links[i] = Link('oblique', lemma, root, 'INF.INSTRUMENTAL', 'ablt', morphology=from_tag(tag))
                yield root, links


def trees(tokens, parse, budget):
    words = tuple(_key(t.surface) for t in tokens)
    infinitives = [i for i in range(len(tokens)) if _forms(tokens, i, 'INFN')]
    if not infinitives:
        return
    relative = [b for b in _boundaries(words) if b.relation == 'relative' and b.start > infinitives[0]]
    ends = [(len(tokens), None), *((b.start, b) for b in relative)]
    produced = set()
    for end, boundary in ends:
        for start in range(1, infinitives[0] + 1):
            if not _forms(tokens, start - 1, 'NOUN'):
                continue
            potential = list(_elaborations(tokens, start, end, budget))
            if not potential:
                continue
            for matrix in parse(tokens[:start]):
                if matrix[-1].role not in {'subject', 'object', 'nominal_conjunct', 'governed', 'oblique'}:
                    continue
                for verb, extra in potential:
                    if (tokens[start].surface != ':' and not spans(tokens[start:end])
                            and extra[verb].controller is None):
                        continue
                    links = {**extra, **dict(enumerate(matrix))}
                    if boundary is None:
                        tails = [links]
                    else:
                        tails = _relative_tails(tokens, links, verb, boundary, parse, budget)
                    for merged in tails:
                        tree = tuple(merged[i] for i in range(len(tokens)))
                        if tree not in produced:
                            produced.add(tree)
                            if len(produced) > budget:
                                raise AnalysisBudgetExceeded('INFINITIVE_CONTENT_BUDGET')
                            yield tree


def _relative_tails(tokens, matrix, host, boundary, parse, budget):
    start = boundary.marker
    for end in range(start + 2, len(tokens) + 1):
        tails = [{}] if end == len(tokens) else [tail for _, tail in _elaborations(tokens, end, len(tokens), budget)]
        if not tails:
            continue
        for root, child in _relative_bases(tokens, start, end, parse, budget):
            full = {**matrix, **child}
            full[start] = replace(full[start], rule='CL.REF', antecedent=host, event_view='situation')
            full[root] = replace(full[root], role='clause_relative', rule='CL.REL', head=host)
            for j in range(boundary.start, start):
                full[j] = Link('punctuation', tokens[j].surface, root, 'CL.PUNCT')
            if end == len(tokens):
                yield full
            elif full[end - 1].role in {'subject', 'object', 'governed', 'genitive_modifier',
                                        'nominal_conjunct', 'oblique', 'instrument'}:
                for result in tails:
                    yield {**full, **result}


def confirmation(tokens, tree, i, text):
    if tree[i].rule == 'INF.CONTENT':
        host = _span_label(tokens, tree[i].head)
        return Probe(f'Какое слово в неопределённой форме раскрывает содержание слова «{host}»?',
                     (_span_label(tokens, i),), text)
