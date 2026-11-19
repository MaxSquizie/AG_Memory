from dataclasses import dataclass, replace
from functools import cache

from .nominal_groups import _markers
from .prepositions import CASE_NAMES
from .quantity_groups import _groups
from .rules import known_forms


@dataclass(frozen=True)
class Standalone:
    start: int
    end: int
    case: str
    kind: str
    value: str | None
    parts: tuple
    surface: str
    case_marked: bool


_ARGUMENT_CASE = {'subject': 'nomn', 'object': 'accs', 'experiencer': 'datv'}
_ARGUMENT_ROLES = {'subject', 'object', 'beneficiary', 'recipient', 'stimulus', 'oblique', 'experiencer', 'governed'}
_OBLIQUE_FORMS = {'accs': 'книгу', 'datv': 'людям', 'gent': 'людей', 'ablt': 'людьми', 'loct': 'людях'}
_SINGULAR = {'masc': 'он', 'femn': 'она', 'neut': 'оно'}


def _surfaces(expression, case, form):
    if case != 'nomn':
        if expression.kind == 'collective' and case == 'accs' and form.animacy == 'inan':
            return ()
        return (_OBLIQUE_FORMS[case],) if case in _OBLIQUE_FORMS else ()
    if expression.kind == 'both' or form.number == 'plur':
        return ('они',)
    if expression.kind == 'ordinal' or form.number == 'sing' or expression.value == '1':
        if form.gender in _SINGULAR:
            return (_SINGULAR[form.gender],)
        return tuple(_SINGULAR.values())
    return ('они', 'оно')


def _longest(tokens, start):
    from .numerals import expressions

    options = tuple(expressions(tokens, start))
    end = max((expr.end for expr in options), default=start)
    return tuple(expr for expr in options if expr.end == end)


def _expects_unit(tokens, expressions):
    from .numerals import known_unit

    if not any(expr.kind == 'fraction' for expr in expressions):
        return False
    for token in tokens[expressions[0].end:]:
        forms = known_forms(token.surface)
        if any(tag.POS == 'NOUN' and known_unit(lemma) for lemma, tag in forms):
            return True
        if not any(tag.POS == 'ADJF' for _, tag in forms):
            break
    return False


def _slots(tokens, budget):

    slots = {}
    counted = set()
    cursor = 0
    while cursor < len(tokens):
        start = cursor
        longest = _longest(tokens, start)
        if not longest:
            cursor += 1
            continue
        cursor = longest[0].end
        if any(next(_groups(tokens, start, expr, budget), None) for expr in longest):
            counted.add(start)
            continue
        if _expects_unit(tokens, longest):
            continue
        options = []
        for expression in longest:
            for case in CASE_NAMES:
                if case not in expression.cases:
                    continue
                parts = expression.parts_for(case)
                if not parts:
                    continue
                for surface in _surfaces(expression, case, parts[-1][1]):
                    marked = not tokens[start].surface[0].isdigit() or 'nomn' not in expression.cases
                    option = Standalone(start, cursor, case, expression.kind, expression.value, parts, surface, marked)
                    if option not in options:
                        options.append(option)
        if options:
            slots[start] = tuple(options)
    for start in reversed(tuple(slots)):
        end = slots[start][0].end
        markers = _markers(tokens, end + 1 if end < len(tokens) and tokens[end].surface == ',' else end)
        if any(marker[-1] + 1 in counted for marker in markers):
            counted.add(start)
            del slots[start]
    return slots


def _remap(tree, kept):
    return {i: replace(link, **{field: kept[value] for field in ('head', 'controller', 'antecedent')
                               if (value := getattr(link, field)) is not None}) for i, link in zip(kept, tree)}


def _restore(tree, kept, groups):
    from .parser import Link

    links = _remap(tree, kept)
    for group in groups:
        head = links[group.start]
        if head.role not in _ARGUMENT_ROLES or (head.case or _ARGUMENT_CASE.get(head.role)) != group.case:
            return
        if head.role == 'oblique' and not group.case_marked:
            return
        dependents = [(i, link.role) for i, link in links.items() if link.head == group.start]
        if head.quantity_kind or any(role in {'name_part', 'numeral'} for _, role in dependents):
            return
        for i, role in dependents:
            left, right = sorted((i, group.start))
            if role == 'attribute' and any(left < j < right and link.role == 'coordinator' for j, link in links.items()):
                return
        lemma, morphology = group.parts[0]
        links[group.start] = replace(head, lemma=lemma, morphology=morphology, case=group.case,
                                     quantity=group.value, quantity_kind=group.kind, rule='NUM.ARG')
        for i, (lemma, morphology) in enumerate(group.parts[1:], group.start + 1):
            links[i] = Link('numeral_part', lemma, group.start, 'NUM.PART', morphology=morphology)
    return tuple(links[i] for i in range(len(links)))


def _single_trees(tokens, local, budget):
    from .parser import AnalysisBudgetExceeded

    yield from local(tokens)
    slots = _slots(tokens, budget)
    if not slots:
        return

    @cache
    def parse(words):
        output = []
        for tree in local(words):
            output.append(tree)
            if len(output) > budget:
                raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
        return output

    seen = set()
    starts = tuple(slots)
    pending = [(0, ())]
    count = 0
    while pending:
        at, groups = pending.pop()
        if at < len(starts):
            start = starts[at]
            pending.append((at + 1, groups))
            pending.extend((at + 1, (*groups, choice)) for choice in slots[start])
            continue
        if not groups:
            continue
        count += 1
        if count > budget:
            raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
        hidden = {i for group in groups for i in range(group.start + 1, group.end)}
        kept = tuple(i for i in range(len(tokens)) if i not in hidden)
        heads = {group.start: group.surface for group in groups}
        words = tuple(replace(tokens[i], surface=heads[i]) if i in heads else tokens[i] for i in kept)
        for tree in parse(words):
            restored = _restore(tree, kept, groups)
            if restored and restored not in seen:
                seen.add(restored)
                if len(seen) > budget:
                    raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
                yield restored


@dataclass(frozen=True)
class Nominative:
    start: int
    end: int
    head: int
    links: tuple
    counted: bool


def _nominatives(tokens, start, budget):
    from .parser import Link

    expressions_here = _longest(tokens, start)
    if not expressions_here:
        return ()
    end = expressions_here[0].end
    standalone = []
    counted = []
    has_noun = False
    for expression in expressions_here:
        for group in _groups(tokens, start, expression, budget):
            has_noun = True
            if group.case == 'nomn':
                noun = Link('subject', group.lemma, None, 'S1', case='nomn', morphology=group.morphology)
                counted.append(Nominative(start, group.noun + 1, group.noun,
                                          ((group.noun, noun), *group.links), True))
        parts = expression.parts_for('nomn')
        if parts:
            lemma, form = parts[0]
            head = Link('subject', lemma, None, 'NUM.ARG', case='nomn', morphology=form,
                        quantity=expression.value, quantity_kind=expression.kind)
            children = ((i, Link('numeral_part', word, start, 'NUM.PART', morphology=morph))
                        for i, (word, morph) in enumerate(parts[1:], start + 1))
            standalone.append(Nominative(start, end, start, ((start, head), *children), False))
    return tuple(dict.fromkeys(counted if has_noun or _expects_unit(tokens, expressions_here) else standalone))


def _coordinated_subjects(tokens, local, budget):
    from .parser import AnalysisBudgetExceeded, Link

    markers = {i: tuple(_markers(tokens, i)) for i in range(len(tokens))}
    markers = {i: choices for i, choices in markers.items() if choices}
    if not markers:
        return

    @cache
    def groups_at(start):
        return _nominatives(tokens, start, budget) if start < len(tokens) else ()

    states = [(group, group.end, group.links, False) for i in range(max(markers)) for group in groups_at(i)]
    visited = 0
    while states:
        first, end, links, has_marker = states.pop()
        comma = end < len(tokens) and tokens[end].surface == ','
        next_word = end + int(comma)
        joins = markers.get(next_word, ()) or (((),) if comma else ())
        for marker in joins:
            for group in groups_at(next_word + len(marker)):
                if group.counted != first.counted:
                    continue
                visited += 1
                if visited > budget:
                    raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
                extension = [(i, replace(link, role='nominal_conjunct', head=first.head)
                              if i == group.head else link) for i, link in group.links]
                for i in marker:
                    role, head = ('coordinator', group.head) if i == marker[0] else ('coordinator_part', marker[0])
                    extension.append((i, Link(role, tokens[i].surface.casefold(), head, 'P.COORD')))
                if comma:
                    extension.append((end, Link('punctuation', ',', group.head, 'P.COORD')))
                joined = (*links, *extension)
                stated = has_marker or bool(marker)
                states.append((first, group.end, joined, stated))
                if not stated:
                    continue
                kept = (*range(first.start), first.head, *range(group.end, len(tokens)))
                words = tuple(replace(tokens[i], surface='они') if i == first.head else tokens[i] for i in kept)
                for outer in _single_trees(words, local, budget):
                    subject = outer[first.start]
                    if subject.role != 'subject' or subject.lemma != 'они':
                        continue
                    restored = _remap(outer, kept)
                    restored.update(joined)
                    restored[first.head] = replace(restored[first.head], head=kept[subject.head])
                    yield tuple(restored[i] for i in range(len(tokens)))


def trees(tokens, local, *, budget=256):
    yield from _single_trees(tokens, local, budget)
    yield from _coordinated_subjects(tokens, local, budget)
