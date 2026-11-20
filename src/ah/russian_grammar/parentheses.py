from dataclasses import replace
from itertools import combinations, product

from .morphology import NOMINAL_ROLES
from .nominal_groups import _agree, _groups, _members, _prepositions
from .numerals import expressions
from .parser import AnalysisBudgetExceeded, Link
from .rules import known_forms
from .utterances import _map, _root


_PROPORTION_SIGNS = frozenset('%‰‱')


def _pairs(tokens):
    stack = []
    pairs = []
    for i, token in enumerate(tokens):
        if token.surface == '(':
            stack.append(i)
        if token.surface == ')':
            if not stack:
                return ()
            start = stack.pop()
            if not stack:
                pairs.append((start, i))
    return () if stack else tuple(pairs)


def _nominal_hosts(tokens, links, index):
    while index in links:
        link = links[index]
        if link.role == 'preposition':
            index = link.head
            continue
        if link.role not in NOMINAL_ROLES | {'genitive_modifier'}:
            break
        if any(lemma == link.lemma and tag.POS in ('NOUN', 'NPRO') for lemma, tag in known_forms(tokens[index].surface)):
            yield index
        elif link.quantity_kind in ('cardinal', 'ordinal'):
            yield index
        index = link.head


def nominal_modifiers(tokens, parse, budget):
    modifiers = {}
    for i, token in enumerate(tokens[:-1]):
        fixed = [(lemma, tag) for lemma, tag in known_forms(token.surface)
                 if tag.POS == 'ADJF' and {'Fixd', 'Apro', 'Anph'} <= tag.grammemes]
        if fixed and any(tag.POS == 'NOUN' for _, tag in known_forms(tokens[i + 1].surface)):
            modifiers[i] = 'possessive'
        if (token.surface.isdecimal() and i > 0
                and any(lemma == 'год' and tag.case == 'gent' and tag.number == 'sing'
                        for lemma, tag in known_forms(tokens[i + 1].surface))):
            modifiers[i] = 'calendar'
    if 2 ** len(modifiers) - 1 > budget:
        raise AnalysisBudgetExceeded('NOMINAL_MODIFIER_BUDGET')
    for size in range(1, len(modifiers) + 1):
        for selected in combinations(modifiers.items(), size):
            yield from _reattach_modifiers(tokens, parse, selected)


def _reattach_modifiers(tokens, parse, selected):
    hidden = {i for i, _ in selected} | {i + 1 for i, kind in selected if kind == 'calendar'}
    kept = tuple(i for i in range(len(tokens)) if i not in hidden)
    if not kept:
        return
    for tree in parse(tuple(tokens[i] for i in kept)):
        links = _map(tree, kept)
        alternatives = []
        for i, kind in selected:
            if kind == 'calendar':
                alternatives.append([{
                    i: Link('numeral', tokens[i].surface, i + 1, 'CAL.YEAR', quantity=tokens[i].surface, quantity_kind='ordinal'),
                    i + 1: Link('genitive_modifier', 'год', host, 'N.GEN', 'gent'),
                } for host in _nominal_hosts(tokens, links, i - 1)])
            elif i + 1 in links:
                noun = links[i + 1]
                if noun.role not in NOMINAL_ROLES | {'genitive_modifier', 'comparison_standard'}:
                    break
                if noun.morphology and noun.morphology.pos not in (None, 'NOUN'):
                    break
                forms = {(lemma, tag) for lemma, tag in known_forms(tokens[i + 1].surface)
                         if lemma == noun.lemma and tag.POS == 'NOUN' and (not noun.case or noun.case == tag.case)}
                adjectives = {lemma for lemma, tag in known_forms(tokens[i].surface)
                              if tag.POS == 'ADJF' and {'Fixd', 'Apro', 'Anph'} <= tag.grammemes
                              and any(_agree(tag, form) for _, form in forms)}
                alternatives.append([{i: Link('possessive', lemma, i + 1, 'P.POSS')} for lemma in sorted(adjectives)])
            else:
                break
        else:
            for additions in product(*alternatives):
                result = links.copy()
                for words in additions:
                    result.update(words)
                yield tuple(result[i] for i in range(len(tokens)))


def _quantity(tokens, hosts):
    surfaces = tuple(t.surface for t in tokens)
    if len(tokens) >= 2 and surfaces[-1] in _PROPORTION_SIGNS:
        for number in expressions(surfaces[:-1]):
            if number.end == len(tokens) - 1 and number.value is not None and number.kind in ('cardinal', 'fraction'):
                j = number.end - 1
                root = j + 1
                for host in hosts:
                    links = {i: Link('numeral_part', w, j, 'NUM.PART') for i, w in enumerate(surfaces[:j])}
                    links[j] = Link('numeral', surfaces[j], root, 'Q1', quantity=number.value, quantity_kind=number.kind)
                    links[root] = Link('apposition', surfaces[root], host, 'PAREN.EXPL')
                    yield links, root
        return
    for stop, prep in _prepositions(tokens, 0):
        for noun, lemma, case, modifiers in _members(tokens, stop, prep):
            pivot = noun + 1
            while pivot < len(tokens) and surfaces[pivot] in ('—', '–', '-', '--'):
                pivot += 1
            if pivot == noun + 1 or pivot >= len(tokens):
                continue
            if pivot - noun - 1 != 1 and not (pivot - noun == 3 and surfaces[noun + 1:pivot] == ('-', '-')
                    and tokens[noun + 1].end == tokens[noun + 2].start):
                continue
            for number in expressions(surfaces, pivot):
                if number.end != len(tokens) or number.value is None or number.kind != 'cardinal':
                    continue
                root = len(tokens) - 1
                links = dict(modifiers)
                links[0] = Link('preposition', prep, root, 'P2')
                for i in range(1, stop):
                    links[i] = Link('prep_part', surfaces[i].casefold(), 0, 'P1')
                links[noun] = Link('governed', lemma, 0, 'P1', case)
                for i in range(noun + 1, pivot):
                    links[i] = Link('punctuation', surfaces[i], root, 'PAREN.SEP')
                for i in range(pivot, root):
                    links[i] = Link('numeral_part', surfaces[i].casefold(), root, 'NUM.PART')
                for host in hosts:
                    yield {**links, root: Link('apposition', surfaces[root], host, 'PAREN.EXPL',
                                              quantity=number.value, quantity_kind=number.kind)}, root


def _description(tokens, hosts, parse, budget):
    for comma in range(1, len(tokens) - 1):
        if tokens[comma].surface != ',':
            continue
        kept = tuple(i for i in range(len(tokens)) if i != comma)
        for tree in parse(tuple(tokens[i] for i in kept)):
            links = _map(tree, kept)
            verb = kept[_root(tree)]
            subjects = [i for i in range(comma) if links[i].role == 'subject' and links[i].head == verb]
            action = links[verb].morphology
            if (len(subjects) != 1 or verb != comma + 1 or action is None
                    or action.pos != 'VERB' or action.mood != 'indc'):
                continue
            subject, = subjects
            if any(link.head is not None and link.head > comma for i, link in links.items() if i < comma and i != subject):
                continue
            links[comma] = Link('punctuation', ',', verb, 'PAREN.SEP')
            links[verb] = replace(links[verb], role='clause_conjunct', head=subject, rule='PAREN.PRED',
                                  controller=subject)
            for host in hosts:
                yield {**links, subject: replace(links[subject], role='apposition', head=host, rule='PAREN.EXPL')}, subject
    for group in _groups(tokens, 0, budget, bare_cases=('nomn',)):
        if group.end == len(tokens):
            for host in hosts:
                yield {**dict(group.extra), group.noun: Link('apposition', group.lemma, host, 'PAREN.EXPL', group.case)}, group.noun


def _coordinated_objects(tree):
    links = list(tree)
    for i, marker in enumerate(tree):
        if marker.role != 'coordinator' or marker.head is None or marker.head <= i:
            continue
        second = tree[marker.head]
        if second.role != 'object':
            continue
        previous = next((j for j in range(i - 1, -1, -1)
                         if tree[j].role == 'object' and tree[j].head == second.head), None)
        if previous is not None:
            first = links[previous]
            head = first.head if first.role == 'nominal_conjunct' else previous
            links[marker.head] = replace(second, role='nominal_conjunct', head=head, rule='P.COORD')
    return tuple(links)


def trees(tokens, parse, budget):
    pairs = _pairs(tokens)
    if not pairs or pairs[0][0] == 0 or any(end <= start + 1 for start, end in pairs):
        return
    hidden = {i for start, end in pairs for i in range(start, end + 1)}
    kept = tuple(i for i in range(len(tokens)) if i not in hidden)
    matrix = tuple(tokens[i] for i in kept)
    for tree in parse(matrix):
        links = _map(_coordinated_objects(tree), kept)
        alternatives = []
        for start, end in pairs:
            hosts = tuple(_nominal_hosts(tokens, links, start - 1))
            if not hosts:
                break
            part = tokens[start + 1:end]
            numeric_hosts = [host for host in hosts if links[host].quantity is not None or any(
                link.role == 'numeral' and link.head == host for link in links.values())]
            hosts_for_quantity = hosts if part[-1].surface in _PROPORTION_SIGNS else numeric_hosts
            quantity = tuple(_quantity(part, hosts_for_quantity))
            expansions = quantity or _description(part, hosts, parse, budget)
            additions = []
            for body, root in expansions:
                host = body[root].head
                positions = range(start + 1, end)
                local = tuple(replace(body[i], head=None) if i == root else body[i] for i in range(len(part)))
                remapped = _map(local, positions)
                remapped[positions[root]] = replace(remapped[positions[root]], head=host)
                for i in (start, end):
                    remapped[i] = Link('punctuation', tokens[i].surface, positions[root], 'PAREN.BOUND')
                additions.append(remapped)
                if len(additions) > budget:
                    raise AnalysisBudgetExceeded('PARENTHETICAL_BUDGET')
            alternatives.append(additions)
        else:
            for additions in product(*alternatives):
                result = links.copy()
                for words in additions:
                    result.update(words)
                yield tuple(result[i] for i in range(len(tokens)))
