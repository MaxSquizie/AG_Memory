from dataclasses import replace
from functools import cache
from itertools import product

from . import event_counts
from .adjuncts import _lexicon
from .morphology import CASE_EQUIVALENTS, Morphology, PREDICATE_ROLES, from_tag
from .nominal_groups import _prepositions
from .numerals import expressions
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .predicative_groups import _nominals
from .prepositions import GOVERNMENT
from .probe import Probe
from .rules import dictionary, known_forms
from .utterances import _map


def _unit(lemma):
    entries, _ = _lexicon()
    return ('nominal', 'когда', '-', lemma) in entries


@cache
def _month_lemmas():
    from .dated_clauses import _months

    return frozenset(lemma for surface in _months() for lemma, tag in known_forms(surface)
                     if tag.POS == 'NOUN' and tag.case == 'gent' and tag.number == 'sing' and tag.animacy == 'inan')


def _calendar_note(tokens, parse, budget):
    from .quantity_groups import _groups

    for year in range(2, len(tokens)):
        digits = tokens[year].surface
        if len(digits) != 4 or not digits.isdecimal() or not int(digits):
            continue
        enclosed = (tokens[year - 1].surface == '(' and year + 1 < len(tokens)
                    and tokens[year + 1].surface == ')')
        start, stop = year - int(enclosed), year + 1 + int(enclosed)
        unit = start - 1
        words = {lemma for lemma, tag in known_forms(tokens[unit].surface) if tag.POS == 'NOUN'}
        month = bool(words & _month_lemmas())
        if not month and (stop != len(tokens) or not any(_unit(word) for word in words)):
            continue
        if stop < len(tokens) and any(lemma == 'год' for lemma, _ in known_forms(tokens[stop].surface)):
            continue
        positions = (*range(start), *range(stop, len(tokens)))
        possible_counts = set()
        if month and not enclosed and year + 1 < len(tokens):
            for number in expressions(tokens, year):
                if number.kind == 'cardinal' and number.end == year + 1:
                    possible_counts.update(group.noun for group in _groups(tokens, year, number, budget))
        witnessed_counts = set()
        if possible_counts:
            for tree in parse(tokens):
                link = tree[year]
                if link.quantity_kind == 'cardinal' and link.head in possible_counts:
                    witnessed_counts.add(link.head)
                    yield tree
        for tree in parse(tuple(tokens[j] for j in positions)):
            links = _map(tree, positions)
            host = links[unit]
            if host.role != 'governed':
                continue
            if host.lemma not in _month_lemmas() and not (
                    _unit(host.lemma) and any(l.head == unit and l.role == 'numeral' for l in links.values())):
                continue
            if any(links[j].head == unit and links[j].role == 'genitive_modifier' for j in witnessed_counts):
                continue
            links[year] = Link('apposition', digits, unit, 'DATE.APPOS', quantity=digits, quantity_kind='ordinal')
            if enclosed:
                for j in (start, stop - 1):
                    links[j] = Link('punctuation', tokens[j].surface, year, 'DATE.PAREN')
            yield tuple(links[j] for j in range(len(tokens)))


def _unknown_forms(surface):
    forms = known_forms(surface)
    if forms:
        return forms
    if not surface.isalpha() or not surface.islower():
        return ()
    return tuple((p.normal_form, p.tag) for p in dictionary().parse(surface) if p.tag.POS == 'NOUN')


def _unlisted_complement(tokens, parse):
    if not any(t.surface.isalpha() and not known_forms(t.surface) for t in tokens):
        return
    for i in range(1, len(tokens) - 1):
        if not any(tag.POS in {'VERB', 'INFN', 'GRND', 'PRTF', 'PRTS'} for _, tag in known_forms(tokens[i - 1].surface)):
            continue
        for first, prep in _prepositions(tokens, i):
            cases = GOVERNMENT.get(prep, ())
            for noun, parts in _nominals(tokens, first, cases, i, 'governed', noun_forms=_unknown_forms):
                if known_forms(tokens[noun].surface) or not any(parts[j].rule == 'A1' for j in range(first, noun)):
                    continue
                group = {**parts, noun: replace(parts[noun], rule='OPAQUE.GOVERNED.COMMON')}
                group.update((j, Link('prep_part', tokens[j].surface.casefold(), i, 'P1')) for j in range(i + 1, first))
                if noun + 1 == len(tokens):
                    tails = ({},)
                else:
                    tails = [links for end, links in _nominals(tokens, noun + 1, {'gent', 'gen2'}, noun, 'genitive_modifier')
                             if end + 1 == len(tokens)]
                if not tails:
                    continue
                for prefix in parse(tokens[:i]):
                    if prefix[-1].role not in PREDICATE_ROLES | {'infinitive', 'converb', 'participle'}:
                        continue
                    for tail in tails:
                        completed = {**group, **tail, i: Link('preposition', prep, i - 1, 'P2')}
                        yield (*prefix, *(completed[j] for j in range(i, len(tokens))))


def _ordinal_sites(tokens):
    for i in range(1, len(tokens) - 1):
        if not tokens[i].surface.isdecimal():
            continue
        forms = tuple((lemma, tag) for lemma, tag in known_forms(tokens[i + 1].surface)
                      if tag.POS == 'NOUN' and tag.case in ('loct', 'loc2') and tag.number == 'sing')
        if forms and any(first == i and 'loct' in GOVERNMENT.get(prep, ()) for first, prep in _prepositions(tokens, i - 1)):
            yield i, forms


def trees(tokens, parse, budget):
    yield from event_counts.trees(tokens, parse, budget)
    yield from _calendar_note(tokens, parse, budget)
    sites = dict(_ordinal_sites(tokens))
    if not sites:
        yield from _unlisted_complement(tokens, parse)
        return
    positions = tuple(i for i in range(len(tokens)) if i not in sites)
    reduced = tuple(tokens[i] for i in positions)
    generated = 0
    for source in (parse(reduced), _unlisted_complement(reduced, parse)):
        for tree in source:
            links = _map(tree, positions)
            variants = []
            for i, forms in sites.items():
                noun = links[i + 1]
                if noun.role != 'governed' or noun.head != i - 1 or noun.case not in ('loct', 'loc2'):
                    break
                from .measured_series import _symbols
                from .distribution_questions import measure_unit

                symbol = _symbols().get(tokens[i + 1].surface)
                prep = links[noun.head]
                if symbol and prep.lemma == 'по' and prep.head is not None and measure_unit(links[prep.head].lemma, symbol):
                    break
                tags = [tag for lemma, tag in forms if lemma == noun.lemma]
                if not tags:
                    break
                digits = tokens[i].surface
                form = Morphology(pos='ADJF', case=CASE_EQUIVALENTS.get(noun.case, noun.case),
                                  number='sing', gender=tags[0].gender)
                ordinal = Link('attribute', digits, i + 1, 'NUM.UNMARKED.ORDINAL', morphology=form,
                               quantity=digits, quantity_kind='ordinal')
                readings = [ordinal]
                nominal = replace(from_tag(tags[0]), case=form.case)
                for expression in expressions(tokens, i):
                    if (expression.end == i + 1 and expression.kind == 'cardinal'
                            and expression.compatible(form.case, nominal, noun.lemma)):
                        lemma, morph = expression.parts_for(form.case, nominal)[0]
                        readings.append(Link('numeral', lemma, i + 1, 'NUM.GROUP', morphology=morph,
                                             quantity=expression.value, quantity_kind='cardinal'))
                variants.append(readings)
            else:
                for selection in product(*variants):
                    generated += 1
                    if generated > budget:
                        raise AnalysisBudgetExceeded('TEMPORAL_GROUP_BUDGET')
                    links.update(zip(sites, selection))
                    yield tuple(links[k] for k in range(len(tokens)))


def confirmation(tokens, tree, i, text):
    link = tree[i]
    if link.rule == 'DATE.APPOS':
        focus = _span_label(tokens, i)
        return Probe('Какое число указывает календарный год, уточняющий названное время?', (focus,), text)
    if link.rule == 'OPAQUE.GOVERNED.COMMON':
        prep = _span_label(tokens, link.head)
        question = f'Какое слово управляется предлогом «{prep}» и является формой существительного «{link.lemma}»?'
        return Probe(question, (_span_label(tokens, i),), text)
    return None


def partitions(trees, tokens, text):
    for i in range(len(tokens) - 1):
        links = [tree[i] for tree in trees]
        host = links[0].head
        if (host is None or host <= i or not all(link.head == host for link in links)
                or {link.rule for link in links} != {'NUM.UNMARKED.ORDINAL', 'NUM.GROUP'}
                or any(t.surface != ',' for t in tokens[i + 1:host])):
            continue
        number = _span_label(tokens, i)
        group = _span_label(tokens, i, host + 1).replace(' ,', ',')
        question = (f'Что обозначает «{number}»? Если это порядковый номер, выберите сочетание '
                    'с существительным. Если указано количество, выберите само число.')
        yield Probe(question, (group, number), text), [group if link.quantity_kind == 'ordinal' else number for link in links]
