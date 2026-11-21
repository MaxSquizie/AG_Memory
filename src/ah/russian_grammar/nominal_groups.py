from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files
from itertools import product

from .nominal_chart import NominalChart, agrees as _agree
from .numerals import Numeric, expressions
from .prepositions import FORMS, PREFIXES
from .rules import Reading, known_forms, name_continuations, name_type, readings


POSSESSIVES = frozenset(('мой', 'наш', 'твой', 'ваш', 'свой', 'его', 'её', 'их', 'ихний', 'чей'))


@cache
def _coordinators():
    table = files(__package__).joinpath('lexicon', 'nominal-connectives.tsv')
    markers = {}
    for row in table.read_text(encoding='utf-8').splitlines():
        form, relation, _ = row.split('\t')
        if relation == 'conj':
            words = tuple(form.split())
            markers.setdefault(words[0], []).append(words)
    return markers


def _markers(tokens, start):
    if start < len(tokens):
        for form in _coordinators().get(tokens[start].surface.casefold(), ()):
            stop = start + len(form)
            if tuple(token.surface.casefold() for token in tokens[start:stop]) == form:
                yield tuple(range(start, stop))


@dataclass(frozen=True)
class Group:
    start: int
    end: int
    preposition: str | None
    noun: int
    lemma: str
    case: str
    extra: tuple
    ordinal: Numeric | None = None


def _prepositions(tokens, start):
    phrase = ''
    for i in range(start, len(tokens)):
        word = tokens[i].surface.lower()
        phrase = (phrase + ' ' + word).lstrip()
        if phrase in FORMS:
            yield i + 1, FORMS[phrase]
        elif i == start:
            for lemma, tag in known_forms(word):
                if tag.POS == 'PREP':
                    yield i + 1, lemma
        if phrase not in PREFIXES:
            break


def _members(tokens, start, prep, case=None):
    from .parser import Link

    qualifiers = []
    for i in range(start, len(tokens)):
        forms = known_forms(tokens[i].surface)
        allowed = None
        if prep:
            allowed = {(r.lemma, r.case) for r in readings(tokens[i].surface, prep) if r.role == 'governed'}
        for lemma, noun in forms:
            if noun.POS not in ('NOUN', 'NPRO'):
                continue
            if qualifiers and noun.POS == 'NPRO':
                continue
            if case is not None and noun.case != case:
                continue
            if prep is None and 'Af-p' in noun:
                continue
            if allowed is not None and (lemma, noun.case) not in allowed and not (case is not None and noun.POS == 'NPRO' and noun.person == '3per'):
                continue
            choices = [tuple(dict.fromkeys(Link(role, adj, i, 'P.POSS' if role == 'possessive' else 'A1')
                                           for role, adj, tag in variants if _agree(tag, noun)))
                       for variants in qualifiers]
            for selected in product(*choices):
                yield i, lemma, noun.case, tuple(zip(range(start, i), selected))
        options = [('possessive' if lemma in POSSESSIVES else 'attribute', lemma, tag)
                   for lemma, tag in forms if tag.POS == 'ADJF' and ('Apro' not in tag or lemma in POSSESSIVES)]
        if not options:
            break
        qualifiers.append(options)


def _possessive_groups(tokens, start):
    from .parser import Link

    for noun, lemma, case, modifiers in _members(tokens, start, None):
        if any(link.role == 'possessive' for _, link in modifiers):
            yield Group(start, noun + 1, None, noun, lemma, case, modifiers)
        if noun + 1 == len(tokens):
            continue
        noun_forms = [tag for word, tag in known_forms(tokens[noun].surface)
                      if word == lemma and tag.case == case and tag.POS == 'NOUN']
        for modifier, tag in known_forms(tokens[noun + 1].surface):
            if modifier not in POSSESSIVES or tag.POS != 'ADJF' or not any(_agree(tag, n) for n in noun_forms):
                continue
            attached = Link('possessive', modifier, noun, 'P.POSS')
            yield Group(start, noun + 2, None, noun, lemma, case, (*modifiers, (noun + 1, attached)))


def _names(tokens, group):
    from .parser import Link

    noun = group.noun
    for lemma, tag in known_forms(tokens[noun].surface):
        kind = name_type(tag)
        if lemma != group.lemma or tag.case != group.case or tag.number != 'sing' or not kind:
            continue
        first = Reading(lemma, 'oblique', tag.case, tag.number, tag.gender, None, tag.animacy, False, kind)
        states = [(group, (first,))]
        while states:
            current, parts = states.pop()
            index = current.end
            if index < len(tokens):
                for part in name_continuations(tokens[index].surface, parts):
                    link = Link('name_part', part.lemma, noun, part.name_rule, case=part.case)
                    expanded = replace(current, end=index + 1, extra=(*current.extra, (index, link)))
                    yield expanded
                    states.append((expanded, (*parts, part)))


def _groups(tokens, start, budget, *, bare_cases=(), chart=None):
    from .parser import NominalBudgetExceeded, Link

    found = set()
    seeds = ((start, None, case) for case in sorted(bare_cases)) if bare_cases else (
        (first, prep, None) for first, prep in _prepositions(tokens, start))
    for first, prep, required_case in seeds:
        for noun, lemma, case, modifiers in _members(tokens, first, prep, required_case):
            initial = Group(start, noun + 1, prep, noun, lemma, case, modifiers)
            pending = [initial]
            if bare_cases:
                pending.extend(_names(tokens, initial))
            while pending:
                group = pending.pop()
                if group in found:
                    continue
                found.add(group)
                if len(found) > budget:
                    raise NominalBudgetExceeded('NOMINAL_GROUP_BUDGET')
                if bare_cases or any(link.role in ('nominal_conjunct', 'possessive') for _, link in group.extra):
                    yield group
                end = group.end
                if end >= len(tokens):
                    continue
                if chart is not None and group.noun in chart.steps[end].attribute_hosts and all(
                        link.role in ('attribute', 'possessive') for _, link in group.extra):
                    noun_tags = [tag for word, tag in known_forms(tokens[group.noun].surface)
                                 if word == group.lemma and tag.POS == 'NOUN' and tag.case == group.case]
                    for j, attached in group.extra:
                        adjective_tags = [tag for word, tag in known_forms(tokens[j].surface)
                                          if word == attached.lemma and tag.POS == 'ADJF']
                        noun_tags = [n for n in noun_tags if any(_agree(a, n) for a in adjective_tags)]
                    for adjective, tag in known_forms(tokens[end].surface):
                        if tag.POS == 'ADJF' and 'Apro' not in tag and any(_agree(tag, n) for n in noun_tags):
                            link = Link('attribute', adjective, group.noun, 'A1')
                            pending.append(replace(group, end=end + 1, extra=(*group.extra, (end, link))))
                comma = tokens[end].surface == ','
                next_word = end + int(comma)
                markers = list(_markers(tokens, next_word))
                if comma:
                    markers.append(())
                for marker in markers:
                    stop = next_word + len(marker)
                    for head, child, _, attrs in _members(tokens, stop, prep, case):
                        links = list(group.extra)
                        if comma:
                            links.append((end, Link('punctuation', ',', head, 'P.COORD')))
                        for i in marker:
                            parent = head if i == marker[0] else marker[0]
                            role = 'coordinator' if i == marker[0] else 'coordinator_part'
                            links.append((i, Link(role, tokens[i].surface.casefold(), parent, 'P.COORD')))
                        links.append((head, Link('nominal_conjunct', child, noun, 'P.COORD', case)))
                        pending.append(replace(group, end=head + 1, extra=(*links, *attrs)))
                        if bare_cases:
                            item = Group(stop, head + 1, prep, head, child, case, attrs)
                            for name in _names(tokens, item):
                                pending.append(replace(group, end=name.end, extra=(*links, *name.extra)))


def _restore_indices(link, kept):
    fields = ('head', 'controller', 'antecedent', 'coord_head', 'shared_agent', 'shared_object', 'ellipsis_source')
    return replace(link, **{field: kept[value] for field in fields if (value := getattr(link, field)) is not None})


def _open_heads(links, before, allowed, *, through_preposition=False):
    index = before - 1
    seen = set()
    while index in links and index not in seen:
        seen.add(index)
        link = links[index]
        if index in allowed:
            yield index
        if link.role not in ('genitive_modifier', 'attribute', 'possessive', 'name_part'):
            if not through_preposition or link.role not in ('governed', 'preposition'):
                break
        if link.head is None or link.head >= before:
            break
        index = link.head


def _extensions(links, groups, chart, budget):
    from .morphology import NOMINAL_ROLES
    from .parser import NominalBudgetExceeded, Link

    nominal_roles = NOMINAL_ROLES | {'genitive_modifier'}
    prepositions = tuple(sorted(i for i, link in links.items() if link.role == 'preposition'))
    total = len(groups) + len(prepositions)
    pending = [(0, links)]
    examined = 0
    while pending:
        position, current = pending.pop()
        if position == total:
            yield tuple(current[i] for i in range(len(current)))
            continue
        if position >= len(groups):
            i = prepositions[position - len(groups)]
            link = current[i]
            pending.append((position + 1, current))
            hosts = tuple(_open_heads(current, i, chart.steps[i].preposition_hosts, through_preposition=True))
            if link.head in hosts:
                for host in hosts[:hosts.index(link.head)]:
                    if current[host].role != 'genitive_modifier':
                        continue
                    examined += 1
                    if examined > budget:
                        raise NominalBudgetExceeded('NOMINAL_FRONTIER_BUDGET')
                    updated = dict(current)
                    updated[i] = replace(link, head=host)
                    pending.append((position + 1, updated))
            continue
        group = groups[position]
        hosts = (chart.steps[group.start - 1].right_edge if group.ordinal is not None or any(link.role == 'numeral' for _, link in group.extra)
                 else chart.steps[group.noun].genitive_hosts)
        for host in _open_heads(current, group.start, hosts):
            examined += 1
            if examined > budget:
                raise NominalBudgetExceeded('NOMINAL_FRONTIER_BUDGET')
            if current[host].role not in nominal_roles and current[host].rule != 'V2.PP':
                continue
            updated = dict(current)
            link = Link('genitive_modifier', group.lemma, host, 'N.GEN', case=group.case)
            if group.ordinal is not None:
                link = replace(link, morphology=group.ordinal.parts_for(group.case)[0][1],
                               quantity=group.ordinal.value, quantity_kind=group.ordinal.kind)
            updated[group.noun] = link
            updated.update(group.extra)
            pending.append((position + 1, updated))


def genitive_ordinals(tokens, start):
    return (expr for expr in expressions(tokens, start)
            if expr.kind == 'ordinal' and 'gent' in expr.cases and 'nomn' not in expr.cases)


def _genitives(tokens, start, chart, budget):
    from .quantity_groups import _groups as counted_groups
    from .parser import Link

    for group in _groups(tokens, start, budget, bare_cases=('gent', 'gen2'), chart=chart):
        if chart.steps[group.noun].genitive_hosts:
            yield group
    preceding = known_forms(tokens[start - 1].surface)
    if not any(tag.POS == 'PREP' for _, tag in preceding):
        for expr in expressions(tokens, start):
            if expr.kind != 'cardinal' or 'gent' not in expr.cases or 'nomn' in expr.cases:
                continue
            for counted in counted_groups(tokens, start, expr, budget):
                if counted.case == 'gent':
                    yield Group(start, counted.noun + 1, None, counted.noun, counted.lemma, 'gent', counted.links)
    for expr in genitive_ordinals(tokens, start):
        if next(counted_groups(tokens, start, expr, budget), None) is not None:
            continue
        parts = expr.parts_for('gent')
        if parts:
            extra = tuple((j, Link('numeral_part', lemma, start, 'NUM.PART', morphology=form))
                          for j, (lemma, form) in enumerate(parts[1:], start + 1))
            yield Group(start, expr.end, None, start, parts[0][0], 'gent', extra, expr)


def with_genitives(tokens, local, *, budget, chart=None):
    from . import collective_agreement
    from .parser import NominalBudgetExceeded

    lexical_members = set()
    for tree in local(tokens):
        for i, link in enumerate(tree):
            if link.role in ('prep_part', 'name_part', 'quantity_modifier', 'numeral_part'):
                lexical_members.add(i)
            if link.role == 'numeral' and link.quantity_kind == 'query':
                lexical_members.add(link.head)
        yield tree

    if chart is None:
        chart = NominalChart(budget)
        for token in tokens:
            chart.feed(token.surface)
    if chart.overflow:
        raise NominalBudgetExceeded('NOMINAL_FRONTIER_BUDGET')
    yield from collective_agreement.trees(tokens, local, budget=budget, chart=chart)
    spans = [group for start in range(1, len(tokens))
             if start - 1 not in lexical_members and chart.steps[start - 1].right_edge
             for group in _genitives(tokens, start, chart, budget)
             if lexical_members.isdisjoint(range(start, group.end))]
    pending = [(0, ())]
    examined = 0
    while pending:
        index, selected = pending.pop()
        for j in range(index, len(spans)):
            group = spans[j]
            if selected and selected[-1].end > group.start:
                continue
            examined += 1
            if examined > budget:
                raise NominalBudgetExceeded('GENITIVE_GROUP_BUDGET')
            groups = (*selected, group)
            hidden = {k for g in groups for k in range(g.start, g.end)}
            kept = tuple(k for k in range(len(tokens)) if k not in hidden)
            for tree in local(tuple(tokens[k] for k in kept)):
                links = {k: _restore_indices(link, kept) for k, link in zip(kept, tree)}
                yield from _extensions(links, groups, chart, budget)
            pending.append((j + 1, groups))


def _restore(tree, kept, groups):
    links = {i: _restore_indices(link, kept) for i, link in zip(kept, tree)}
    choices = []
    for group in groups:
        head = links[group.noun]
        if head.lemma != group.lemma:
            return
        if group.preposition is None:
            from .morphology import NOMINAL_ROLES, ROLE_CASE
            case = head.case or ROLE_CASE.get(head.role) or getattr(head.morphology, 'case', None)
            if head.role not in NOMINAL_ROLES or case != group.case:
                return
        elif (head.role != 'governed' or head.head != group.start or head.case != group.case
              or links[group.start].lemma != group.preposition):
            return
        links.update(group.extra)
        conjuncts = [i for i, link in group.extra if link.role == 'nominal_conjunct']
        if group.end in links and links[group.end].role == 'preposition' and links[group.end].head == group.noun and conjuncts:
            choices.append((group.end, (group.noun, conjuncts[-1])))
    for targets in product(*(options for _, options in choices)):
        for (i, _), target in zip(choices, targets):
            links[i] = replace(links[i], head=target)
        yield tuple(links[i] for i in range(len(links)))


def trees(tokens, local, *, budget=256):
    from .parser import NominalBudgetExceeded

    yield from local(tokens)
    possessives = any(lemma in POSSESSIVES and tag.POS == 'ADJF' for token in tokens
                      for lemma, tag in known_forms(token.surface))
    if not possessives and not any(token.surface.casefold() in _coordinators() or token.surface == ',' for token in tokens):
        return
    starts = []
    for i in range(len(tokens)):
        options = dict.fromkeys(_groups(tokens, i, budget))
        if possessives:
            options.update(dict.fromkeys(_possessive_groups(tokens, i)))
        if len(options) > budget:
            raise NominalBudgetExceeded('NOMINAL_GROUP_BUDGET')
        if options:
            starts.append((i, tuple(options)))

    @cache
    def reduced(kept):
        result = []
        for tree in local(tuple(tokens[i] for i in kept)):
            result.append(tree)
            if len(result) > budget:
                raise NominalBudgetExceeded('NOMINAL_GROUP_BUDGET')
        return tuple(result)

    count = 0
    pending = [(0, ())]
    while pending:
        index, picked = pending.pop()
        for j in range(index, len(starts)):
            pos, groups = starts[j]
            if picked and picked[-1].end > pos:
                continue
            for group in groups:
                selection = (*picked, group)
                count += 1
                if count > budget:
                    raise NominalBudgetExceeded('NOMINAL_GROUP_BUDGET')
                hidden = {i for block in selection for i, _ in block.extra}
                kept = tuple(i for i in range(len(tokens)) if i not in hidden)
                for tree in reduced(kept):
                    yield from _restore(tree, kept, selection)
                pending.append((j + 1, selection))
