from dataclasses import dataclass, replace
from functools import cache, lru_cache
from itertools import product

from . import participle_forms
from .participle_connectives import PAIRS, markers, openers, relations
from .rules import known_forms


@dataclass(frozen=True)
class Join:
    start: int
    end: int
    marker: tuple
    words: str


def _joins(tokens):
    for i, token in enumerate(tokens):
        comma = token.surface == ','
        if not comma and i and tokens[i - 1].surface == ',':
            continue
        options = tuple(markers(tokens, i + int(comma)))
        if options:
            positions = max(options, key=len)
            yield Join(i, positions[-1] + 1, positions, ' '.join(tokens[j].surface.casefold() for j in positions))
        elif comma:
            yield Join(i, i + 1, (), '')


def _can_share(first, second):
    return any(a.morphology.number == b.morphology.number and
               (a.morphology.number == 'plur' or a.morphology.gender == b.morphology.gender) and
               (a.morphology.case == b.morphology.case or
                (a.morphology.number == 'plur' and {a.morphology.case, b.morphology.case} <= {'nomn', 'accs', 'gent'}))
               for a in first for b in second)


@lru_cache(maxsize=2048)
def _full_only(surface):
    return bool(participle_forms.readings(surface)) and all(tag.POS == 'PRTF' for _, tag in known_forms(surface))


def _possible_host(tokens, participles):
    for token in tokens:
        forms = known_forms(token.surface)
        if forms and all(tag.POS == 'VERB' for _, tag in forms):
            return False
        if any(participle_forms.agrees(part, tag) for _, tag in forms if tag.POS in {'NOUN', 'NPRO'}
               for part in participles):
            return True
    return False


def linked_members(tokens):
    pivots = [i for i, word in enumerate(tokens) if participle_forms.readings(word.surface)]
    joins = tuple(_joins(tokens)) if len(pivots) > 1 else ()
    links = {}
    for left, right in zip(pivots, pivots[1:]):
        if not _full_only(tokens[left].surface) or not _full_only(tokens[right].surface):
            continue
        if not any(left < j.start and j.end <= right for j in joins):
            continue
        first = participle_forms.readings(tokens[left].surface)
        second = participle_forms.readings(tokens[right].surface)
        if not _can_share(first, second):
            continue
        if _possible_host(reversed(tokens[:left]), first) and _possible_host(tokens[right + 1:], second):
            continue
        for token in tokens[left + 1:right]:
            forms = known_forms(token.surface)
            if token.surface[0].isdigit() or any(tag.POS in {'NUMR', 'VERB'} for _, tag in forms):
                break
            if any(participle_forms.agrees(part, tag) for _, tag in forms if tag.POS in {'NOUN', 'NPRO'}
                   for part in (*first, *second)):
                break
        else:
            series = links.get(left)
            if series is None:
                series = [left]
                links[left] = series
            series.append(right)
            links[right] = series
    return {i: tuple(series) for i, series in links.items()}


def _relations(joins, terms, opener, budget):
    from .parser import AnalysisBudgetExceeded

    names = [join.words for join in joins]
    paired = PAIRS.get(opener, {})
    if opener and not paired.keys() & set(names):
        return
    options = []
    for i, word in enumerate(names):
        if not word:
            choices = ('addition',)
        elif word in paired:
            choices = (paired[word],)
        elif word == 'а' and 'negated' in (terms[i][1][terms[i][0]].scope or '').split('_'):
            choices = ('correction',)
        else:
            choices = relations(word)
        if not choices:
            return
        options.append(choices)
    qualified = {'alternative', 'comparison', 'negative_coordination'}
    remaining = budget
    for scope in sorted(qualified):
        if any(scope in choices for choices in options) and all(
                not name or scope in choices for name, choices in zip(names, options)):
            remaining -= 1
            if remaining < 0:
                raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
            yield (scope,) * len(options)
    ordinary = [tuple(value for value in choices if value not in qualified) for choices in options]
    if not all(ordinary):
        return
    size = 1
    for choices in ordinary:
        size *= len(choices)
        if size > remaining:
            raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
    yield from product(*ordinary)


def as_modifier(link, form):
    return replace(link, role='participle', head=-1, rule='PART.ATTR', case=form.morphology.case,
                   controller=-1 if form.morphology.voice == 'actv' else None, morphology=form.morphology, implicit_subject=None)


def _joined(tokens, terms, joins, opener, first_word, relations):
    from .parser import Link

    first = terms[0][0]
    links = {}
    for i, (root, branch) in enumerate(terms):
        links.update(branch)
        participle = links[root]
        qualification = relations[0] if relations[0] in {'alternative', 'comparison', 'negative_coordination'} else None
        scope = participle.scope
        if qualification:
            scope = qualification + ('_' + scope if scope else '')
        links[root] = replace(participle, coord_head=first if i else None, scope=scope)
    if opener:
        first_marker = 0
        links[first_marker] = Link('coordinator', tokens[first_marker].surface.casefold(), first,
                                   'PART.COORD.OPEN', scope=relations[0])
        for i in range(1, first_word):
            links[i] = Link('coordinator_part', tokens[i].surface.casefold(), first_marker, 'PART.COORD')
    for join, relation, (root, _) in zip(joins, relations, terms[1:]):
        if tokens[join.start].surface == ',':
            links[join.start] = Link('punctuation', ',', root, 'PART.COORD', scope=None if join.marker else relation)
        if join.marker:
            lead = join.marker[0]
            links[lead] = Link('coordinator', tokens[lead].surface.casefold(), root, 'PART.COORD', scope=relation)
            for i in join.marker[1:]:
                links[i] = Link('coordinator_part', tokens[i].surface.casefold(), lead, 'PART.COORD')
    return tuple(links[i] for i in range(len(tokens)))


def branches(tokens, pivot, forms, inside, remap, budget):
    from .parser import AnalysisBudgetExceeded

    if len(forms) < 2:
        return
    joins = tuple(j for j in _joins(tokens) if min(forms) < j.start and j.end <= max(forms))
    if not joins:
        return

    @cache
    def arguments(start, end):
        out = []
        for root, readings in forms.items():
            if not start <= root < end:
                continue
            indices = {-1: -1, **{j: start + j for j in range(end - start)}}
            for form in readings:
                for tree in inside(tokens[start:end], root - start, form):
                    links = {start + j: remap(link, indices) for j, link in enumerate(tree)}
                    links[root] = as_modifier(links[root], form)
                    out.append((root, links))
                    if len(out) > budget:
                        raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
        return out

    count = 0
    for opener, first in openers(tokens):
        states = [(first, (), ())]
        while states:
            start, terms, separators = states.pop()
            if terms:
                for term in arguments(start, len(tokens)):
                    selected = (*terms, term)
                    if any(root == pivot for root, _ in selected):
                        for meanings in _relations(separators, selected, opener, budget - count):
                            count += 1
                            if count > budget:
                                raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
                            yield _joined(tokens, selected, separators, opener, first, meanings)
            for join in joins:
                if join.start <= start:
                    continue
                for term in arguments(start, join.start):
                    count += 1
                    if count > budget:
                        raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
                    states.append((join.end, (*terms, term), (*separators, join)))


def complete(tree):
    siblings = {}
    for i, link in enumerate(tree):
        if link.role == 'participle':
            siblings.setdefault(link.head, []).append(i)
    for host, members in siblings.items():
        for left, right in zip(members, members[1:]):
            if left < host < right or tree[right].coord_head == left or (
                    tree[left].coord_head is not None and tree[right].coord_head == tree[left].coord_head):
                continue
            separated = any(tree[i].role == 'punctuation' and tree[i].lemma == ','
                            and tree[i].head in {left, right} for i in range(left + 1, right))
            if not separated:
                continue
            for i in range(left + 1, right):
                j = i
                while j not in {left, right, host, None}:
                    j = tree[j].head
                if j not in {left, right}:
                    break
            else:
                return False
    return True
