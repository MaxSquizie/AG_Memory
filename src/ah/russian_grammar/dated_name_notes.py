from dataclasses import replace
from unicodedata import name

from .calendar_regions import calendar_day, day_links, year_unit
from .morphology import Morphology, from_tag
from .parser import Link, _span_label
from .passive_arguments import _opaque
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
    if _opaque(first):
        group = {0: Link('subject', first, None, 'OPAQUE.NOTE.SUBJECT', 'nomn', scope='proper_name')}
        for end in range(1, len(tokens)):
            yield end, group
            surface = tokens[end].surface
            if _script(surface) != _script(first):
                break
            if not _opaque(surface):
                if _name(surface):
                    for lemma, tag in known_forms(surface):
                        if tag.case == 'nomn' and tag.number == 'sing' and name_type(tag) in ('Surn', 'Patr'):
                            named = Link('name_part', lemma, 0, 'NAME', 'nomn', morphology=from_tag(tag), scope='proper_name')
                            yield end + 1, group | {end: named}
                break
            group = group | {end: Link('name_part', surface, 0, 'NAME', scope='proper_name')}
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


def _year_interval(tokens, start, host):
    comma = start < len(tokens) and tokens[start].surface == ','
    first = start + int(comma)
    marked = first + 1 < len(tokens) and tokens[first + 1].surface in DASHES
    last = first + 1 + int(marked)
    if last >= len(tokens):
        return None
    years = [tokens[j].surface for j in (first, last)]
    if not all(len(year) == 4 and year.isdecimal() for year in years) or not 0 < int(years[0]) <= int(years[1]):
        return None
    links = {first: Link('list_item', years[0], host, 'DATE.NOTE.INTERVAL',
                         quantity='..'.join(years), quantity_kind='ordinal_range'),
             last: Link('numeral_part', years[1], first, 'NUM.PART', quantity=years[1], quantity_kind='ordinal')}
    if marked:
        links[first + 1] = Link('punctuation', tokens[first + 1].surface, last, 'NUM.RANGE.MARK')
    if comma:
        links[start] = Link('punctuation', ',', first, 'DATE.SEP')
    return last + 1, first, links


def _cited_form(tokens, start):
    from .utterances import _quotation_governors

    if start >= len(tokens) or tokens[start].surface != '(':
        return
    verb = start + 1
    if verb + 2 >= len(tokens):
        return
    forms = [(lemma, tag) for lemma, tag in known_forms(tokens[verb].surface)
             if tag.POS == 'VERB' and tag.person == '3per' and tag.number == 'sing'
             and lemma.endswith('ся') and lemma[:-2] in _quotation_governors()]
    if len(forms) != 1:
        return
    lemma, tag = forms[0]
    quoted = verb + 1
    links = {verb: Link('parenthetical', lemma, None, 'NAME.FORM.NOTE',
                        scope='parenthetical', morphology=from_tag(tag))}
    if tokens[quoted].surface == ',':
        closing = next((i for i in range(quoted + 1, len(tokens)) if tokens[i].surface in {',', ')'}), None)
        if closing is None or closing < quoted + 2 or tokens[closing].surface != ',':
            return
        gerund = closing - 1
        verbs = [(l, t) for l, t in known_forms(tokens[gerund].surface)
                 if t.POS == 'GRND' and l in _quotation_governors()]
        if len(verbs) != 1:
            return
        for j in range(quoted + 1, gerund):
            modifiers = {l for l, t in known_forms(tokens[j].surface) if t.POS == 'ADVB' or 'Prnt' in t}
            if len(modifiers) != 1:
                return
            links[j] = Link('adverb', next(iter(modifiers)), gerund, 'MOD.ADV')
        links[gerund] = Link('parenthetical', verbs[0][0], verb, 'NAME.FORM.ASIDE',
                             scope='parenthetical', morphology=from_tag(verbs[0][1]))
        for j in (quoted, closing):
            links[j] = Link('punctuation', ',', gerund, 'PAREN.BOUND')
        quoted = closing + 1
    close = quoted
    while close < len(tokens) and _name(tokens[close].surface):
        close += 1
    if close == quoted or close >= len(tokens) or tokens[close].surface != ')':
        return
    links[quoted] = Link('designation', tokens[quoted].surface, verb, 'NAME.FORM.CITATION', antecedent=0)
    for j in range(quoted + 1, close):
        links[j] = Link('name_part', tokens[j].surface, quoted, 'NAME', scope='proper_name')
    for j in (start, close):
        links[j] = Link('punctuation', tokens[j].surface, verb, 'PAREN.BOUND')
    return close + 1, verb, links


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
    separator = i < size and tokens[i].surface in {';', ','}
    citation = _cited_form(tokens, i + int(separator)) if enclosed else None
    if citation:
        after, verb, remark = citation
        if separator:
            links[i] = Link('punctuation', tokens[i].surface, verb, 'PAREN.BOUND')
        links.update(remark)
        i = after
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
    if first_day is None:
        interval = _year_interval(tokens, i, alias if alias is not None else 0)
        if interval:
            i, first_day, group = interval
            links.update(group)
    if alias is None and first_day is None:
        return
    if citation:
        links[verb] = replace(links[verb], head=first_day if first_day is not None else alias)
    if enclosed:
        if i >= size or tokens[i].surface != ')':
            return
        for j in (start, i):
            links[j] = Link('punctuation', tokens[j].surface, alias if alias is not None else first_day, 'NAME.NOTE.BOUND')
        i += 1
    if i < size and tokens[i].surface in DASHES:
        links[i] = Link('punctuation', tokens[i].surface, 0, 'V2.DASH')
        i += 1
    if i < size:
        yield i, links


def prefixes(tokens):
    for stop, initial in _first_name(tokens):
        citation = _cited_form(tokens, stop)
        if citation:
            end, verb, links = citation
            if end < len(tokens) and tokens[end].surface in DASHES:
                links[verb] = replace(links[verb], head=0)
                links[end] = Link('punctuation', tokens[end].surface, 0, 'V2.DASH')
                yield end + 1, initial | links, 0
        for end, note in _note(tokens, stop):
            yield end, initial | note, 0


def confirmation(tokens, tree, i, text):
    link = tree[i]
    if link.rule == 'NAME.FORM.CITATION':
        end = i + 1
        while end < len(tree) and tree[end].head == i and tree[end].role == 'name_part':
            end += 1
        return Probe('Какую форму имени приводят в скобках?', (_span_label(tokens, i, end),), text)
    if link.rule == 'DATE.NOTE.INTERVAL':
        end = next(j for j, child in enumerate(tree) if child.role == 'numeral_part' and child.head == i)
        years = text[tokens[i].start:tokens[end].end]
        if text.count(years) != 1:
            years = _span_label(tokens, i, end + 1)
        return Probe('Какие числа указывают границы периода, приведённого при имени?', (years,), text)
    if link.rule == 'OPAQUE.NOTE.SUBJECT':
        end = i + 1
        while end < len(tree) and tree[end].head == i and tree[end].role == 'name_part':
            end += 1
        return Probe('Какими словами назван тот, кому дана характеристика?', (_span_label(tokens, i, end),), text)
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
