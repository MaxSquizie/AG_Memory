from dataclasses import replace
from itertools import chain

from .dated_clauses import calendar_day, year_unit
from .morphology import Morphology, NOMINAL_ROLES, PREDICATE_ROLES, ROLE_CASE
from .numerals import HYPHENS, RANGE_MARKS, roman_value
from .parser import Link, _span_label
from .probe import Probe
from .quote_titles import spans
from .rules import known_forms
from .utterances import _map


def day_links(tokens, i, host, role, with_unit):
    month = next(lemma for lemma, tag in known_forms(tokens[i + 1].surface) if tag.POS == 'NOUN' and tag.case == 'gent')
    year = tokens[i + 2].surface
    links = {i: Link(role, tokens[i].surface, host, 'DATE.DAY', quantity=str(int(tokens[i].surface)), quantity_kind='ordinal'),
             i + 1: Link('date_month', month, i, 'DATE.MONTH', case='gent'),
             i + 2: Link('date_year', year, i + (3 if with_unit else 1), 'DATE.YEAR', quantity=year, quantity_kind='ordinal')}
    if with_unit:
        links[i + 3] = Link('genitive_modifier', 'год', i + 1, 'DATE.YEAR.UNIT', case='gent')
    return links


def _dates(tokens, parse):
    for i in range(1, len(tokens) - 2):
        if calendar_day(tokens, i) is None:
            continue
        if not any(tag.POS in {'VERB', 'PRTS', 'INFN', 'GRND', 'PRTF'} for token in tokens[:i]
                   for _, tag in known_forms(token.surface)):
            continue
        with_unit = i + 3 < len(tokens) and year_unit(tokens[i + 3].surface)
        stop = i + 3 + int(with_unit)
        kept = (*range(i), *range(stop, len(tokens)))
        for tree in parse(tuple(tokens[j] for j in kept)):
            links = _map(tree, kept)
            head = i - 1
            while head is not None:
                if links[head].role in PREDICATE_ROLES | {'infinitive', 'participle', 'converb'}:
                    completed = links | day_links(tokens, i, head, 'temporal', with_unit)
                    yield tuple(completed[j] for j in range(len(tokens)))
                    verb = links[head].morphology
                    if verb and verb.transitivity == 'tran' and not any(
                            l.head == head and l.role == 'object' for l in links.values()):
                        completed[i] = replace(completed[i], role='object', case='accs')
                        yield tuple(completed[j] for j in range(len(tokens)))
                    break
                if links[head].role in {'subject', 'object', 'governed', 'genitive_modifier'}:
                    completed = links | day_links(tokens, i, head, 'nominal_date', with_unit)
                    yield tuple(completed[j] for j in range(len(tokens)))
                head = links[head].head


def leading_year_range(tokens, parse):
    if len(tokens) <= 4:
        return
    first, lower, last, upper = (t.surface.casefold() for t in tokens[:4])
    cases = {('с', 'по'): ('gent', 'accs'), ('от', 'до'): ('gent', 'gent')}.get((first, last))
    if not cases or not all(len(n) == 4 and n.isdecimal() for n in (lower, upper)) or not 0 < int(lower) <= int(upper):
        return
    for tree in parse(tokens[4:]):
        root = next(i for i, link in enumerate(tree) if link.head is None)
        if not any(l.role == 'subject' and l.head == root for l in tree):
            continue
        links = _map(tree, range(4, len(tokens)))
        for j, (prep, year, case) in enumerate(zip((first, last), (lower, upper), cases)):
            i = 2 * j
            links[i] = Link('preposition', prep, root + 4, 'P2')
            links[i + 1] = Link('governed', year, i, 'DATE.YEAR.BOUND', case,
                                scope='year_interval', quantity=year, quantity_kind='ordinal')
        yield tuple(links[j] for j in range(len(tokens)))


def _ordinal_years(tokens, parse):
    from .numerals import expressions
    from .prepositions import GOVERNMENT

    for i, token in enumerate(tokens[:-1]):
        if not (len(token.surface) == 4 and token.surface.isdecimal() and int(token.surface)):
            continue
        forms = [tag for lemma, tag in known_forms(tokens[i + 1].surface) if lemma == 'год' and tag.POS == 'NOUN']
        if not any(tag.number == 'sing' and tag.case == 'gent' for tag in forms) or i >= 2 and calendar_day(tokens, i - 2):
            continue
        kept = (*range(i), *range(i + 1, len(tokens)))
        cardinal_possible = False
        for tree in parse(tuple(tokens[j] for j in kept)):
            links = _map(tree, kept)
            unit = links[i + 1]
            if unit.lemma != 'год':
                continue
            if (unit.role == 'governed' and i > 0 and unit.head == i - 1 and links[i - 1].role == 'preposition'):
                cases = GOVERNMENT.get(links[i - 1].lemma, ())
                cardinal_possible |= any(number.compatible(case, tag) for number in expressions((token.surface,))
                                         if number.kind == 'cardinal' for case in cases for tag in forms)
            elif unit.role != 'genitive_modifier':
                continue
            if unit.case != 'gent':
                continue
            form = Morphology(pos='ADJF', case=unit.case, number='sing', gender='masc')
            links[i] = Link('attribute', token.surface, i + 1, 'NUM.UNMARKED.ORDINAL', unit.case, morphology=form,
                            quantity=token.surface, quantity_kind='ordinal')
            yield tuple(links[j] for j in range(len(tokens)))
        if cardinal_possible:
            for tree in parse(tokens):
                if tree[i].head == i + 1 and tree[i].quantity_kind == 'cardinal':
                    yield tree


def _roman_interval(tokens, start):
    surface = tokens[start].surface
    left = roman_value(surface)
    if left is None:
        mark = next((letter for letter in surface if letter in HYPHENS), None)
        if mark is None:
            return
        lower, _, upper = surface.partition(mark)
        left, right = roman_value(lower), roman_value(upper)
        noun, marked = start + 1, True
    else:
        marked = tokens[start + 1].surface in RANGE_MARKS or tokens[start + 1].surface == '--'
        end = start + 1 + int(marked)
        if end + 1 >= len(tokens):
            return
        right = roman_value(tokens[end].surface)
        noun = end + 1
    if left is not None and right is not None and left < right:
        return noun, left, right, marked


def _ordinal_intervals(tokens, parse):
    sites = {}
    hidden = set()
    for i in range(len(tokens) - 1):
        if i in hidden:
            continue
        interval = _roman_interval(tokens, i)
        if interval is None:
            continue
        noun, left, right, marked = interval
        forms = [(lemma, tag.case) for lemma, tag in known_forms(tokens[noun].surface)
                 if tag.POS == 'NOUN' and tag.number == 'plur']
        if forms:
            sites[i] = noun, left, right, marked, forms
            hidden.update(range(i, noun))
    if not sites:
        return
    kept = tuple(i for i in range(len(tokens)) if i not in hidden)
    for tree in parse(tuple(tokens[j] for j in kept)):
        links = _map(tree, kept)
        for i, (noun, left, right, marked, forms) in sites.items():
            host = links[noun]
            case = host.case or ROLE_CASE.get(host.role) or (host.morphology and host.morphology.case)
            if (host.role not in NOMINAL_ROLES | {'genitive_modifier'} or (host.lemma, case) not in forms
                    or host.morphology and host.morphology.number == 'sing'):
                break
            rule = 'NUM.ORDINAL.INTERVAL' if marked else 'NUM.ORDINAL.UNMARKED.INTERVAL'
            links[i] = Link('attribute', tokens[i].surface, noun, rule, case,
                            quantity=f'{left}..{right}', quantity_kind='ordinal_range')
            if noun > i + 1:
                end = noun - 1
                links[end] = Link('numeral_part', tokens[end].surface, i, 'NUM.PART')
                if marked:
                    links[i + 1] = Link('punctuation', tokens[i + 1].surface, end, 'NUM.RANGE.MARK')
        else:
            yield tuple(links[j] for j in range(len(tokens)))


def confirmation(tokens, tree, i, text):
    if i == 1 and tree[i].rule == 'DATE.YEAR.BOUND':
        return Probe('Какие слова обозначают начало и конец периода в годах?', (_span_label(tokens, 0, 4),), text)
    if tree[i].rule == 'NUM.ORDINAL.UNMARKED.INTERVAL':
        host = tree[i].head
        first, last = (_span_label(tokens, j) for j in (i, i + 1))
        region = _span_label(tokens, i, host + 1)
        return Probe(f'Какое сочетание обозначает весь промежуток от «{first}» до «{last}» включительно?',
                     (region,), text)


def _simple_titles(tokens):
    return {left + 1: (left, right) for left, right in spans(tokens)
            if right == left + 2 and tokens[left + 1].surface.istitle()}


def _printed_year(word):
    return len(word) == 4 and word.isdecimal() and int(word) != 0


def year_lists(tokens):
    from .nominal_groups import _markers
    from .parentheses import _pairs

    notes = dict(_pairs(tokens))
    start = 0
    while start < len(tokens):
        years, separators = [], []
        index = start
        while index < len(tokens):
            word = tokens[index].surface
            if not _printed_year(word):
                break
            years.append(index)
            following = index + 1
            index = notes[following] + 1 if following in notes else following
            if index == len(tokens):
                break
            unit = tokens[index].surface.casefold()
            if len(years) > 1 and unit.startswith('год') and any(
                    lemma == 'год' and tag.number == 'plur' for lemma, tag in known_forms(unit)):
                if any(left < right for left, right in separators):
                    yield tuple(years), tuple(separators), index
                break
            comma = tokens[index].surface == ','
            conjunction = next(_markers(tokens, index + int(comma)), ())
            if not comma and not conjunction and not _printed_year(tokens[index].surface):
                break
            end = index + int(comma) + len(conjunction)
            separators.append((index, end))
            index = end
        start = max(start + 1, index)


def year_links(tokens, years, separators, unit, case):
    from .measured_series import _separator_links

    first = years[0]
    links = {}
    for year in years:
        links[year] = Link('attribute' if year == first else 'nominal_conjunct', tokens[year].surface,
                           unit if year == first else first, 'DATE.YEAR.SERIES', case,
                           quantity=tokens[year].surface, quantity_kind='ordinal')
    for (begin, end), year in zip(separators, years[1:]):
        comma = tokens[begin].surface == ','
        links.update(_separator_links(tokens, begin, comma, tuple(range(begin + int(comma), end)), year))
    return links


def _year_lists(tokens, parse):
    lists = tuple(year_lists(tokens))
    if not lists:
        return
    hidden = {i for years, _, unit in lists for i in range(years[0], unit)}
    if any(tokens[i].surface == '(' for i in hidden):
        return
    kept = tuple(i for i in range(len(tokens)) if i not in hidden)
    for tree in parse(tuple(tokens[i] for i in kept)):
        links = _map(tree, kept)
        for years, separators, unit in lists:
            noun = links[unit]
            if noun.lemma != 'год' or noun.role not in NOMINAL_ROLES | {'genitive_modifier'}:
                break
            case = noun.case or ROLE_CASE.get(noun.role) or (noun.morphology and noun.morphology.case)
            if not any(tag.number == 'plur' and tag.case == case for _, tag in known_forms(tokens[unit].surface)):
                break
            links.update(year_links(tokens, years, separators, unit, case))
        else:
            yield tuple(links[i] for i in range(len(tokens)))


def _calendar(tokens, parse):
    yield from _year_lists(tokens, parse)
    yield from _dates(tokens, parse)
    yield from _ordinal_years(tokens, parse)
    yield from _ordinal_intervals(tokens, parse)


def trees(tokens, parse, budget):
    yield from _calendar(tokens, parse)
    quoted = _simple_titles(tokens)
    if not quoted:
        return
    excluded = {j for pair in quoted.values() for j in pair}
    kept = tuple(j for j in range(len(tokens)) if j not in excluded)
    part = tuple(tokens[j] for j in kept)
    readings = _calendar(part, parse)
    first = next(readings, None)
    for tree in chain((first,), readings) if first is not None else parse(part):
        links = _map(tree, kept)
        for name, pair in quoted.items():
            if links[name].role not in {'subject', 'object', 'governed', 'apposition', 'genitive_modifier'}:
                break
            morph = links[name].morphology
            links[name] = replace(links[name], scope='proper_name', rule='NAME.MENTION',
                                  morphology=replace(morph, animacy=None) if morph else None)
            for j in pair:
                links[j] = Link('punctuation', tokens[j].surface, name, 'TITLE.QUOTE')
        else:
            yield tuple(links[j] for j in range(len(tokens)))


def partitions(trees, tokens, text):
    for i, token in enumerate(tokens):
        if not token.surface.isdecimal() or not all(tree[i].rule == 'DATE.DAY' for tree in trees):
            continue
        links = [tree[i] for tree in trees]
        hosts = {l.head for l in links}
        end = i + 3 + int(i + 3 < len(tokens) and year_unit(tokens[i + 3].surface))
        label = _span_label(tokens, i, end)
        if len(hosts) > 1:
            choices = {j: _span_label(tokens, j) for j in sorted(hosts)}
            yield Probe(f'К какому слову относится дата «{label}»?', tuple(choices.values()), text), [
                choices[l.head] for l in links]
        if len(hosts) == 1 and {l.role for l in links} == {'object', 'temporal'}:
            verb = _span_label(tokens, links[0].head)
            question = (f'Что обозначает «{label}»? Если предмет действия «{verb}» — сама дата, выберите дату. '
                        f'Если указано, когда произошло действие, выберите «{verb}».')
            yield Probe(question, (label, verb), text), [label if l.role == 'object' else verb for l in links]
