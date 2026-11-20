from dataclasses import replace
from itertools import chain

from .dated_clauses import calendar_day, year_unit
from .morphology import Morphology, PREDICATE_ROLES
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


def _ordinal_years(tokens, parse):
    for i, token in enumerate(tokens[:-1]):
        if not (len(token.surface) == 4 and token.surface.isdecimal() and int(token.surface)
                and year_unit(tokens[i + 1].surface)):
            continue
        if i >= 2 and calendar_day(tokens, i - 2):
            continue
        kept = (*range(i), *range(i + 1, len(tokens)))
        for tree in parse(tuple(tokens[j] for j in kept)):
            links = _map(tree, kept)
            unit = links[i + 1]
            if unit.role != 'genitive_modifier' or unit.lemma != 'год':
                continue
            form = Morphology(pos='ADJF', case='gent', number='sing', gender='masc')
            links[i] = Link('attribute', token.surface, i + 1, 'NUM.UNMARKED.ORDINAL', 'gent', morphology=form,
                            quantity=token.surface, quantity_kind='ordinal')
            yield tuple(links[j] for j in range(len(tokens)))


def _simple_titles(tokens):
    return {left + 1: (left, right) for left, right in spans(tokens)
            if right == left + 2 and tokens[left + 1].surface.istitle()}


def _calendar(tokens, parse):
    yield from _dates(tokens, parse)
    yield from _ordinal_years(tokens, parse)


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
