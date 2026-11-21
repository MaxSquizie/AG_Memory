from dataclasses import replace
from itertools import islice, product

from .calendar_regions import year_links, year_lists
from .marked_regions import RelativeChoice
from .named_arguments import opaque_cases
from .nominal_entries import Unit, _attach, _layouts, _modifiers
from .nominal_groups import _groups, _prepositions
from .parentheses import _pairs
from .parser import AnalysisBudgetExceeded, Link, _partition, _span_label
from .prepositions import GOVERNMENT
from .probe import Probe
from .short_participles import _predicative_instrumentals
from .rules import fixed_noun_cases, known_forms
from .utterances import _map


class MemberChoice(RelativeChoice):
    domain = 'nominal_member'

    def __init__(self, key, probe):
        self.start = key
        self.probe = probe
        self.heads = {option: option for option in probe.options}


def _notes(part, begin, end, host, budget):
    body = part[begin + 1:end]
    for first, prep in _prepositions(body, 0):
        for case in GOVERNMENT.get(prep, ()):
            for noun in _groups(body, first, budget, bare_cases=(case,)):
                frame = {**dict(noun.extra), 0: Link('preposition', prep, None, 'PP.NOTE'),
                         noun.noun: Link('governed', noun.lemma, 0, 'P1', case)}
                for i in range(1, first):
                    frame[i] = Link('prep_part', body[i].surface.casefold(), 0, 'P1')
                for layout in _layouts(body, noun, {}, budget):
                    for tree in _attach(layout, (noun.noun,), frame):
                        links = _map(tree, range(begin + 1, end))
                        links[begin + 1] = replace(links[begin + 1], head=host)
                        for j in (begin, end):
                            links[j] = Link('punctuation', part[j].surface, begin + 1, 'PAREN.BOUND')
                        yield links


def _modifiers_with_dates(part, i, budget):
    fixed = {}
    for unit in _modifiers(part, i, budget):
        if unit.prep and len(fixed_noun_cases(part[unit.head].surface, unit.link.lemma,
                                              GOVERNMENT.get(unit.prep[1], ()))) > 1:
            fixed.setdefault(replace(unit, link=replace(unit.link, case=None)), set()).add(unit.link.case)
        else:
            yield unit
    for unit, cases in fixed.items():
        yield replace(unit, link=replace(unit.link, case=next(iter(cases)))) if len(cases) == 1 else unit
    for first, prep in _prepositions(part, i):
        if first >= len(part):
            continue
        word = part[first].surface
        for case in sorted(opaque_cases(word).intersection(GOVERNMENT.get(prep, ()))):
            parts = tuple((k, Link('prep_part', part[k].surface.casefold(), i, 'P1')) for k in range(i + 1, first))
            yield Unit(i, first + 1, first, Link('governed', word, i, 'OPAQUE.GOVERNED.NAME', case), parts, (i, prep))
    starts = [(i, None), *((first, (i, prep)) for first, prep in _prepositions(part, i))]
    for start, prep in starts:
        if start >= len(part):
            continue
        groups = [row for row in year_lists(part) if row[0][0] == start]
        year = part[start].surface
        if len(year) == 4 and year.isdecimal() and start + 1 < len(part):
            groups.append(((start,), (), start + 1))
        for years, separators, unit in groups:
            for lemma, tag in known_forms(part[unit].surface):
                if (lemma != 'год' or tag.POS != 'NOUN' or tag.number != ('sing' if len(years) == 1 else 'plur')
                        or tag.case not in (GOVERNMENT.get(prep[1], ()) if prep else ('gent',))):
                    continue
                extras = year_links(part, years, separators, unit, str(tag.case))
                notes = []
                combinations = 1
                for a, b in _pairs(part):
                    if start < a < b < unit and a - 1 in years:
                        readings = tuple(islice(_notes(part, a, b, a - 1, budget), budget + 1))
                        combinations *= len(readings)
                        if combinations > budget:
                            raise AnalysisBudgetExceeded('NOMINAL_ENTRY_ATTACHMENT_BUDGET')
                        notes.append(readings)
                for attached in product(*notes):
                    extra = dict(extras)
                    for links in attached:
                        extra.update(links)
                    if prep:
                        extra.update((k, Link('prep_part', part[k].surface.casefold(), i, 'P1'))
                                     for k in range(i + 1, start))
                    if set(extra) != set(range(start if not prep else i + 1, unit)):
                        continue
                    role = Link('governed', lemma, i, 'P1', str(tag.case)) if prep else Link(
                        'genitive_modifier', lemma, None, 'N.GEN', str(tag.case))
                    yield Unit(i, unit + 1, unit, role, tuple(extra.items()), prep)


def _members(part, head, budget):
    choices = {}
    for seed in _groups(part, 0, budget, bare_cases=(head.case,)):
        if seed.noun or seed.lemma != head.lemma:
            continue
        for layout in _layouts(part, seed, {}, budget, modifiers=_modifiers_with_dates):
            if not any(link.rule == 'DATE.YEAR.SERIES' for unit in layout for _, link in unit.extra):
                continue
            for tree in _attach(layout, (0,), {0: replace(head, head=None), **dict(seed.extra)}):
                choices[tree] = None
                if len(choices) > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_ENTRY_ATTACHMENT_BUDGET')
    return tuple(choices)


def _choose(partition, key, choices):
    probe, labels = partition
    key = ('nominal_member', key, probe.prompt())
    if key not in choices:
        raise MemberChoice(key, probe)
    return tuple(label == choices[key] for label in labels)


def _member_partition(trees, tokens, text):
    for i in range(len(tokens)):
        roles = {tree[i].role for tree in trees}
        if 'preposition' in roles and 'genitive_modifier' in roles:
            complements = {j for tree in trees if tree[i].role == 'preposition'
                           for j, link in enumerate(tree) if link.head == i and link.role == 'governed'}
            if len(complements) == 1:
                noun, = complements
                word, group = _span_label(tokens, i), _span_label(tokens, i, noun + 1)
                question = f'Если «{word}» служит предлогом, выберите сочетание с зависимым словом. Если это имя, выберите само имя.'
                return Probe(question, (group, word), text), [
                    group if tree[i].role == 'preposition' else word for tree in trees]
    for i in range(1, len(tokens)):
        matches = [tree[i].role == 'name_part' and tree[i].head == i - 1 for tree in trees]
        if any(matches) and not all(matches):
            name = _span_label(tokens, i - 1, i + 1)
            absent = 'нет такого сочетания'
            probe = Probe('Какие слова вместе называют одного человека в этом фрагменте?',
                          (name, absent), text)
            return probe, [name if linked else absent for linked in matches]
    for unit in range(len(tokens)):
        first = next((i for i, link in enumerate(trees[0])
                      if link.rule == 'DATE.YEAR.SERIES' and link.head == unit and link.role == 'attribute'), None)
        heads = {tree[unit].head for tree in trees}
        if first is not None and len(heads) > 1 and None not in heads:
            labels = {head: _span_label(tokens, head) for head in sorted(heads)}
            span = text[tokens[first].start:tokens[unit].end]
            question = f'Что датируется сочетанием «{span}»? Выберите главное слово того, к чему относятся эти годы.'
            return Probe(question, tuple(labels.values()), text), [labels[tree[unit].head] for tree in trees]
    return _partition(trees, tokens, text)


def trees(tokens, parse, choices, text, budget):
    if not any(year_lists(tokens)):
        return
    pairs = dict(_pairs(tokens))
    separators = [i for i in range(1, len(tokens) - 1) if tokens[i].surface == ','
                  and not any(a < i < b for a, b in pairs.items())
                  and any(tag.POS == 'NOUN' for _, tag in known_forms(tokens[i + 1].surface))]
    if not separators:
        return
    forms = [{(lemma, str(tag.case)) for lemma, tag in known_forms(tokens[i + 1].surface)
              if tag.POS == 'NOUN' and tag.case} for i in separators]
    for lemma, case in sorted(set.intersection(*forms)):
        for first in range(1, separators[0]):
            if not any(l == lemma and t.case == case for l, t in known_forms(tokens[first].surface)):
                continue
            begins = [first, *(j + 1 for j in separators)]
            stops = [*separators, len(tokens)]
            kept = (*range(first + 1), *(k for j in separators for k in (j, j + 1)))
            for base in parse(tuple(tokens[j] for j in kept)):
                outer = _map(base, kept)
                head = outer[first]
                if (head.case != case or head.lemma != lemma or head.role not in (
                        'predicative_complement', 'object', 'oblique', 'recipient')
                        or any(outer[j].head != first or outer[j].role != 'nominal_conjunct' for j in begins[1:])):
                    continue
                families = [_members(tokens[a:b], outer[a], budget) for a, b in zip(begins, stops)]
                if not all(families):
                    continue
                for begin, stop, trees_here in zip(begins, stops, families):
                    part = tokens[begin:stop]
                    plain = text[part[0].start:part[-1].end]
                    local = tuple(replace(t, start=t.start - part[0].start, end=t.end - part[0].start) for t in part)
                    while len(trees_here) > 1:
                        partition = _member_partition(trees_here, local, plain)
                        if partition is None:
                            break
                        selected = _choose(partition, part[0].start, choices)
                        trees_here = [tree for tree, retained in zip(trees_here, selected) if retained]
                    if len(trees_here) != 1:
                        break
                    links = _map(trees_here[0], range(begin, stop))
                    links[begin] = outer[begin]
                    outer.update(links)
                else:
                    verb = outer[head.head]
                    if (case == 'ablt' and head.role == 'oblique' and verb.lemma in _predicative_instrumentals()
                            and any(w == verb.lemma and t.transitivity == 'intr'
                                    for w, t in known_forms(tokens[head.head].surface))):
                        focus = tokens[first].surface
                        action = _span_label(tokens, head.head)
                        absent = 'нет такого слова'
                        question = f'Какое повторяющееся слово обозначает статус участника действия «{action}»?'
                        options = (focus, absent)
                        selected = _choose((Probe(question, options, text), options), tokens[first].start, choices)
                        if selected[0]:
                            subjects = [j for j, link in outer.items() if link.role == 'subject' and link.head == head.head]
                            controller = subjects[0] if len(subjects) == 1 else None
                            outer[first] = replace(head, role='predicative_complement', rule='V.XCOMP', controller=controller)
                            for j in begins[1:]:
                                outer[j] = replace(outer[j], controller=controller)
                    yield tuple(outer[j] for j in range(len(tokens)))
