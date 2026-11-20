from unicodedata import name

from .calendar_regions import calendar_day, day_links, year_unit
from .morphology import Morphology, from_tag
from .parser import Link, _span_label
from .prepositions import DASHES
from .probe import Probe
from .rules import Reading, known_forms, name_continuations, name_type, unaccented


def _script(surface):
    scripts = {name(c, '').partition(' ')[0] for c in unaccented(surface) if c.isalpha()}
    return next(iter(scripts)) if len(scripts) == 1 else None


def _name(surface):
    return unaccented(surface).isalpha() and unaccented(surface).istitle()


def _first_name(tokens):
    if not tokens or not _name(tokens[0].surface):
        return
    first = tokens[0].surface
    for lemma, tag in known_forms(first):
        if tag.POS != 'NOUN' or tag.case != 'nomn' or not name_type(tag) or tag.number != 'sing':
            continue
        subject = Link('subject', lemma, None, 'S1', 'nomn', morphology=from_tag(tag), scope='proper_name')
        initial = Reading(lemma, 'subject', tag.case, tag.number, tag.gender, '3per', tag.animacy, False, name_type(tag))
        pending = [(1, (initial,), {0: subject})]
        while pending:
            end, parts, links = pending.pop()
            yield end, links
            if end == len(tokens):
                continue
            surface = tokens[end].surface
            if not _name(surface) or _script(surface) != _script(first):
                continue
            if not known_forms(surface):
                extra = Link('name_part', unaccented(surface).casefold(), 0, 'OPAQUE.NAME.CONTINUATION',
                             'nomn', scope='proper_name')
                yield end + 1, links | {end: extra}
                continue
            for part in name_continuations(surface, parts):
                extra = Link('name_part', part.lemma, 0, part.name_rule, part.case, scope='proper_name')
                pending.append((end + 1, (*parts, part), links | {end: extra}))


def _note(tokens, start):
    size = len(tokens)
    enclosed = start < size and tokens[start].surface == '('
    i = start + int(enclosed)
    if i == size:
        return
    first = i
    script = _script(tokens[i].surface)
    links = {}
    if script and script != _script(tokens[0].surface):
        while i < size and _name(tokens[i].surface) and _script(tokens[i].surface) == script:
            role = 'apposition' if i == first else 'name_part'
            rule = 'NAME.ALIAS' if i == first else 'NAME.ALIAS.PART'
            links[i] = Link(role, tokens[i].surface, 0 if i == first else first, rule, scope='proper_name')
            i += 1
    alias = first if i != first else None
    first_day = None
    while i < size:
        separator = tokens[i].surface in {';', ','} | DASHES
        day = i + int(separator)
        if calendar_day(tokens, day) is None:
            break
        if separator:
            links[i] = Link('punctuation', tokens[i].surface, day, 'DATE.SEP')
        host = first_day if first_day is not None else alias if alias is not None else 0
        with_unit = day + 3 < size and year_unit(tokens[day + 3].surface)
        links.update(day_links(tokens, day, host, 'list_item', with_unit))
        if first_day is None:
            first_day = day
        i = day + 3 + int(with_unit)
        comma = i < size and tokens[i].surface == ','
        label = i + int(comma)
        if label < size and _name(tokens[label].surface):
            if comma:
                links[i] = Link('punctuation', ',', label, 'DATE.SEP')
            links[label] = Link('list_item', tokens[label].surface, day, 'DATE.NOTE.LABEL',
                                scope='proper_name', morphology=Morphology(pos='NOUN'))
            i = label + 1
    if alias is None and first_day is None:
        return
    if enclosed:
        if i >= size or tokens[i].surface != ')':
            return
        for j in (start, i):
            links[j] = Link('punctuation', tokens[j].surface, first, 'NAME.NOTE.BOUND')
        i += 1
    if i < size and tokens[i].surface in DASHES:
        links[i] = Link('punctuation', tokens[i].surface, 0, 'V2.DASH')
        i += 1
    if i < size:
        yield i, links


def prefixes(tokens):
    for stop, initial in _first_name(tokens):
        for end, note in _note(tokens, stop):
            yield end, initial | note, 0


def confirmation(tokens, tree, i, text):
    link = tree[i]
    if link.rule == 'NAME.ALIAS':
        stop = i + 1
        while stop < len(tree) and tree[stop].head == i and tree[stop].rule == 'NAME.ALIAS.PART':
            stop += 1
        subject = link.head
        end = subject + 1
        while end < len(tree) and tree[end].head == subject and tree[end].role == 'name_part':
            end += 1
        word = _span_label(tokens, subject, end)
        return Probe(f'Какие слова дают другое написание имени «{word}»?', (_span_label(tokens, i, stop),), text)
    if link.rule == 'DATE.NOTE.LABEL':
        day = link.head
        label = _span_label(tokens, day, day + 3)
        return Probe(f'Какое название в перечне относится к дате «{label}»?', (_span_label(tokens, i),), text)
    return None
