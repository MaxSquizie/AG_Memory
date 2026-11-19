from collections import defaultdict
from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files

from .rules import known_forms


def _key(word):
    return word.casefold().replace('ё', 'е')


@cache
def _connectives():
    forms = defaultdict(lambda: defaultdict(set))
    table = files(__package__).joinpath('lexicon', 'clause-connectives.tsv')
    for row in table.read_text(encoding='utf-8').splitlines():
        form, relation, governor = row.split('\t')
        forms[tuple(form.split())][relation].add(governor)
    return forms, max(map(len, forms))


@dataclass(frozen=True)
class Boundary:
    start: int
    marker: int
    stop: int
    form: str
    relation: str
    governors: frozenset


def _boundaries(words):
    forms, width = _connectives()
    for index in range(len(words)):
        start = index - 1 if index and words[index - 1] == ',' else index
        if words[index] == 'что' and start > 0:
            yield Boundary(start, index, index + 1, 'что', 'relative', frozenset())
        for end in range(index + 1, min(len(words), index + width) + 1):
            phrase = words[index:end]
            for relation, governors in forms.get(phrase, {}).items():
                if relation == 'advcl' and phrase == ('что',):
                    continue
                yield Boundary(start, index, end, ' '.join(phrase), relation, frozenset(governors))


def _shift(link, offset):
    return replace(link, head=None if link.head is None else link.head + offset,
                   controller=None if link.controller is None else link.controller + offset,
                   antecedent=None if link.antecedent is None else link.antecedent + offset)


def _scope(boundary):
    if boundary.relation == 'ccomp':
        return 'embedded'
    if boundary.relation == 'advcl':
        return 'condition' if boundary.form == 'если' else 'adverbial'
    return 'alternative' if boundary.form in ('или', 'либо') else None


def _markers(boundary, root, words):
    from .parser import Link

    markers = []
    stop = boundary.marker if boundary.relation == 'relative' else boundary.stop
    for index in range(boundary.start, stop):
        if index < boundary.marker:
            link = Link('punctuation', words[index], root, 'CL.PUNCT')
        else:
            scope = _scope(boundary) if index == boundary.marker else None
            link = Link('clause_marker', words[index], root, 'CL.MARK', scope=scope)
        markers.append(link)
    return tuple(markers)


def _attachments(prefix, levels, boundary, leaf, root, words):
    relative = boundary.relation == 'relative'
    marker_links = _markers(boundary, root, words)
    for level in range(len(levels) - 1, -1, -1):
        anchor, current = levels[level]
        relation = boundary.relation
        host = anchor if relation == 'conj' else current
        if relation == 'ccomp':
            if _key(prefix[host].lemma) not in boundary.governors:
                continue
            if any(link and link.role == 'clause_complement' and link.head == host for link in prefix):
                continue
        own = leaf[root - (boundary.marker if relative else boundary.stop)]
        if relation == 'conj':
            role, rule = 'clause_conjunct', 'CL.CONJ'
            next_levels = levels[:level] + ((anchor, root),)
        elif relative:
            role, rule = 'clause_relative', 'CL.REL'
            next_levels = levels[:level + 1] + ((root, root),)
        else:
            role, rule = ('clause_complement', 'CL.COMP') if relation == 'ccomp' else ('clause_adverbial', 'CL.ADV')
            next_levels = levels[:level + 1] + ((root, root),)
        scope = _scope(boundary)
        joined = list(prefix + marker_links + leaf)
        joined[root] = replace(own, role=role, rule=rule, head=host, scope=own.scope or scope)
        host_scope = {'condition': 'conditional', 'alternative': 'alternative'}.get(scope)
        if host_scope and not joined[host].scope:
            joined[host] = replace(joined[host], scope=host_scope)
        if relative:
            reference = leaf[0]
            views = ('situation', 'event') if 'averted' in (prefix[host].scope or '').split('_') else ('situation',)
            for view in views:
                joined[boundary.marker] = replace(reference, rule='CL.REF', antecedent=host, event_view=view)
                yield tuple(joined), next_levels
        else:
            yield tuple(joined), next_levels


def trees(tokens, local, *, budget=256):
    from .parser import AnalysisBudgetExceeded, Link

    words = tuple(_key(token.surface) for token in tokens)
    yield from local(tokens)
    boundaries = tuple(_boundaries(words))
    if not boundaries:
        return
    size = len(words)
    remaining = budget

    def spend():
        nonlocal remaining
        if remaining <= 0:
            raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
        remaining -= 1

    @cache
    def leaves(start, stop):
        spend()
        result = []
        for tree in local(tokens[start:stop]):
            roots = [i for i, link in enumerate(tree) if link.role == 'predicate' and link.head is None]
            if len(roots) == 1:
                result.append((tuple(_shift(link, start) for link in tree), roots[0] + start))
                if len(result) > budget:
                    raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
        return tuple(result)

    def relative_leaves(marker, stop):
        state_roots = set()
        for leaf, root in leaves(marker.stop, stop):
            state = leaf[root - marker.stop]
            if state.rule != 'V3':
                continue
            if not any(tag.POS == 'ADJS' and tag.gender == 'neut' for _, tag in known_forms(tokens[root].surface)):
                continue
            if any(link.role == 'infinitive' and link.head == root for link in leaf):
                continue
            reference = Link('event_argument', 'что', root, 'CL.REF')
            state_roots.add(root)
            yield (reference, *leaf), root
        for leaf, root in leaves(marker.marker, stop):
            if leaf[0].lemma != 'что' or leaf[0].role not in ('subject', 'object'):
                continue
            predicate = leaf[root - marker.marker]
            if leaf[0].role == 'subject' and leaf[0].head == root:
                if root in state_roots and predicate.rule == 'V2':
                    continue
                if predicate.lemma == 'быть' and any(leaf[i - marker.marker].role == 'adverb'
                        and leaf[i - marker.marker].head == root for i in state_roots):
                    continue
            yield leaf, root

    ends = tuple(sorted({b.start for b in boundaries if b.start > 0} | {size}))
    starts = defaultdict(list)
    for boundary in boundaries:
        starts[boundary.start].append(boundary)

    def parse_region(lo, hi):
        finishes = [i for i in ends if lo < i < hi] + [hi]
        pending = []
        for stop in finishes:
            if lo == 0 and stop == size:
                continue
            for leaf, root in leaves(lo, stop):
                if stop == hi:
                    yield leaf, root
                else:
                    pending.append((stop, (None,) * lo + leaf, ((root, root),)))
        while pending:
            spend()
            offset, prefix, levels = pending.pop()
            for marker in starts[offset]:
                for stop in finishes:
                    if stop <= marker.stop:
                        continue
                    candidates = relative_leaves(marker, stop) if marker.relation == 'relative' else leaves(marker.stop, stop)
                    for leaf, root in candidates:
                        for tree, scopes in _attachments(prefix, levels, marker, leaf, root, words):
                            if stop == hi:
                                yield tree[lo:], scopes[0][0]
                            else:
                                pending.append((stop, tree, scopes))
                                if len(pending) > budget:
                                    raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')

    for tree, _ in parse_region(0, size):
        yield tree
    for marker in starts[0]:
        if marker.form != 'если' or marker.relation != 'advcl':
            continue
        for stop in range(marker.stop + 1, size):
            split = stop + (words[stop] == ',')
            main = split + (split < size and words[split] == 'то')
            if main >= size or (stop > 0 and words[stop - 1] == ','):
                continue
            for condition, child in parse_region(marker.stop, stop):
                for consequence, root in parse_region(main, size):
                    joined = list(_markers(marker, child, words) + condition)
                    joined.extend(Link('punctuation' if i < split else 'clause_marker', words[i], root, 'CL.COND',
                                       scope='conditional' if i >= split else None)
                                  for i in range(stop, main))
                    joined.extend(consequence)
                    joined[child] = replace(joined[child], role='clause_adverbial', head=root, rule='CL.ADV',
                                            scope=joined[child].scope or 'condition')
                    joined[root] = replace(joined[root], scope=joined[root].scope or 'conditional')
                    yield tuple(joined)
