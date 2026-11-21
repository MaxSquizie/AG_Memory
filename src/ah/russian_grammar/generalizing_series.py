from dataclasses import replace

from .determiners import SCOPES
from .morphology import NOMINAL_ROLES, ROLE_CASE, from_tag
from .nominal_groups import _groups
from .participle_connectives import relations
from .partitive_domains import _proxy
from .prepositions import DASHES
from .rules import known_forms
from .utterances import _map


def _hosts(surface, marked):
    for lemma, form in known_forms(surface):
        if form.POS == 'NOUN' and marked:
            yield lemma, form, None
        elif form.POS == 'ADJF' and 'Subx' in form and SCOPES.get(lemma) == 'universal':
            proxy = _proxy(form.case, form.number, form.gender)
            if proxy:
                yield lemma, form, proxy


def _additive(group, tokens):
    for i, link in group.extra:
        if link.role == 'coordinator':
            parts = [j for j, part in group.extra if part.role == 'coordinator_part' and part.head == i]
            marker = ' '.join(tokens[j].surface.casefold() for j in (i, *parts))
            if 'addition' not in relations(marker):
                return False
    return any(link.role == 'nominal_conjunct' for _, link in group.extra)


def _series(tokens, start, case, budget):
    for group in _groups(tokens, start, budget, bare_cases=(case,), unmarked_series=True):
        if _additive(group, tokens):
            yield group


def _following(tokens, host, case, budget):
    opening = host + 1
    marked = tokens[opening].surface == ':'
    start = opening + int(marked)
    for group in _series(tokens, start, case, budget):
        end = group.end
        closing = end < len(tokens) and tokens[end].surface in DASHES
        if end < len(tokens) and not closing and not any(t.POS == 'VERB' for _, t in known_forms(tokens[end].surface)):
            continue
        kept = (*range(opening), *range(end + int(closing), len(tokens)))
        marks = (*range(opening, start), *range(end, end + int(closing)))
        yield group, kept, marks


def _preceding(tokens, host, case, budget):
    stop = host - int(tokens[host - 1].surface in DASHES)
    for start in range(stop - 1):
        for group in _series(tokens[:stop], start, case, budget):
            if group.end == stop:
                yield group, (*range(start), *range(host, len(tokens))), range(stop, host)


def _matrices(tokens, host, token, budget):
    for eligible, marked, regions in (
        (host + 2 < len(tokens), host + 1 < len(tokens) and tokens[host + 1].surface == ':', _following),
        (host >= 2, host > 0 and tokens[host - 1].surface in DASHES, _preceding),
    ):
        if eligible:
            for lemma, form, proxy in _hosts(token.surface, marked):
                for group, kept, marks in regions(tokens, host, form.case, budget):
                    yield lemma, form, proxy, group, kept, marks


def trees(tokens, parse, budget, *, gap_boundaries=None):
    from .parser import AnalysisBudgetExceeded, Link

    attempts = 0
    for host, token in enumerate(tokens):
        if gap_boundaries is not None and host - 1 not in gap_boundaries:
            continue
        for lemma, form, proxy, group, kept, marks in _matrices(tokens, host, token, budget):
            if gap_boundaries is not None and host - 1 not in marks:
                continue
            attempts += 1
            if attempts > budget:
                raise AnalysisBudgetExceeded('NOMINAL_SERIES_BUDGET')
            matrix = tuple(replace(tokens[j], surface=proxy) if j == host and proxy else tokens[j] for j in kept)
            for tree in parse(matrix):
                head = tree[kept.index(host)]
                case = head.case or ROLE_CASE.get(head.role) or getattr(head.morphology, 'case', None)
                if case != group.case or (head.role not in NOMINAL_ROLES and head.rule != 'V.GOV'):
                    continue
                if not proxy and head.lemma != lemma:
                    continue
                links = _map(tree, kept)
                if proxy:
                    links[host] = replace(links[host], lemma=lemma, case=case, rule='NP.GENERALIZER',
                                          morphology=from_tag(form), scope=SCOPES[lemma])
                else:
                    links[host] = replace(links[host], rule='NP.GENERALIZER')
                for i, link in group.extra:
                    links[i] = replace(link, scope='addition') if link.role == 'coordinator' else link
                links[group.noun] = Link('apposition', group.lemma, host, 'NP.ENUM', case)
                for i in marks:
                    links[i] = Link('punctuation', tokens[i].surface, group.noun, 'NP.ENUM.BOUND')
                yield tuple(links[i] for i in range(len(tokens)))


def confirmation(tokens, tree, i, text):
    from .parser import _span_label
    from .probe import Probe

    if tree[i].rule == 'NP.ENUM.JUXT':
        first = tree[i].head
        generalizer = tree[first].head
        word = _span_label(tokens, i)
        return Probe(f'Какое слово после «{_span_label(tokens, first)}» называет отдельный пункт '
                     f'перечисления при «{_span_label(tokens, generalizer)}»?', (word,), text)


def listed_members(rows, children, head):
    if rows[head].get('rule') != 'NP.GENERALIZER':
        return ()
    lists = [j for j in children[head] if rows[j].get('rule') == 'NP.ENUM']
    if len(lists) != 1:
        return ()
    first, = lists
    return (first, *(j for j in children[first] if rows[j]['role'] == 'nominal_conjunct'))


def gap_boundaries(tokens, analyses):
    return {i for i, token in enumerate(tokens[:-1]) if token.surface in DASHES and
            any(tree[i].rule == 'GAP' for tree in analyses)}


def gap_partitions(analyses, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i in gap_boundaries(tokens, analyses):
        roles = {tree[i].rule for tree in analyses}
        if roles != {'GAP', 'NP.ENUM.BOUND'}:
            continue
        if not all(tree[i].rule == 'GAP' or tree[tree[i].head].head == i + 1 for tree in analyses):
            continue
        head = _span_label(tokens, i + 1)
        answers = [head if tree[i].rule == 'NP.ENUM.BOUND'
                   else _span_label(tokens, tree[i].ellipsis_source) for tree in analyses]
        options = tuple(dict.fromkeys(answers))
        if len(options) > 1:
            question = (f'Как понимать «{head}» после тире? Если это общее название перечисленного, '
                        f'выберите «{head}». Если после тире подразумевается действие, выберите его слово.')
            yield Probe(question, options, text), answers
