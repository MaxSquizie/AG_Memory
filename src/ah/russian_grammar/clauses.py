from collections import defaultdict
from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files

from . import degree_clauses
from .ellipsis import competing_leaves, gapped_leaves
from .rules import known_forms
from .spatial_prefix import relative_role


def _key(word):
    return word.casefold().replace('ё', 'е')


@cache
def _connectives():
    forms = defaultdict(lambda: defaultdict(set))
    table = files(__package__).joinpath('lexicon', 'clause-connectives.tsv')
    for row in table.read_text(encoding='utf-8').splitlines():
        form, relation, governor = row.split('\t')
        forms[tuple(form.split())][relation].add(governor)
    forms[('что',)]['ccomp'].add('знать')
    forms[('даже', 'если')]['advcl'].add('*')
    return forms, max(map(len, forms))


@cache
def _preposed():
    table = files(__package__).joinpath('lexicon', 'preposed-connectives.tsv')
    return frozenset(line.split('\t')[0] for line in table.read_text(encoding='utf-8').splitlines())


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
        if relative_role(words[index]) and 'advcl' not in forms.get((words[index],), {}):
            yield Boundary(start, index, index + 1, words[index], 'advcl', frozenset())
        if words[index] in degree_clauses.PAIRS and words[index] != 'когда':
            if any(word in degree_clauses.PAIRS[words[index]][1] for word in words[:index]):
                yield Boundary(start, index, index + 1, words[index], 'correlative', frozenset())
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
                   ellipsis_source=None if link.ellipsis_source is None else link.ellipsis_source + offset,
                   coord_head=None if link.coord_head is None else link.coord_head + offset,
                   shared_agent=None if link.shared_agent is None else link.shared_agent + offset,
                   shared_object=None if link.shared_object is None else link.shared_object + offset,
                   controller=None if link.controller is None else link.controller + offset,
                   antecedent=None if link.antecedent is None else link.antecedent + offset)


def _preposed_splits(words, body_start):
    for end in range(body_start + 1, len(words)):
        main = end + (words[end] == ',')
        if main < len(words) and words[end - 1] != ',':
            yield end, main


def _scope(boundary):
    if boundary.relation == 'ccomp':
        return 'embedded'
    if boundary.relation == 'advcl':
        if boundary.form in ('потому что', 'так как'):
            return 'cause'
        if boundary.form == 'даже если':
            return 'concessive_condition'
        if boundary.form == 'если':
            return 'condition'
        if boundary.form in ('хотя', 'несмотря на то что'):
            return 'concession'
        if boundary.form in ('когда', 'как только', 'пока'):
            return 'temporal'
        return 'adverbial'
    return 'alternative' if boundary.form in ('или', 'либо') else None


def _allows_mood(boundary, predicate):
    if boundary.relation != 'advcl' or boundary.form not in {'если', 'даже если', 'хотя', 'когда', 'как только', 'пока'}:
        return True
    return predicate.morphology is None or predicate.morphology.mood != 'impr'


def _markers(boundary, root, words):
    from .parser import Link

    markers = []
    if boundary.form == 'даже если':
        markers.extend(Link('punctuation', words[i], root, 'CL.PUNCT')
                       for i in range(boundary.start, boundary.marker))
        markers.append(Link('particle', words[boundary.marker], boundary.marker + 1, 'CL.FOCUS', scope='concessive'))
        markers.append(Link('clause_marker', words[boundary.marker + 1], root, 'CL.MARK', scope=_scope(boundary)))
        return tuple(markers)
    stop = boundary.marker if boundary.relation == 'relative' else boundary.stop
    for index in range(boundary.start, stop):
        if index < boundary.marker:
            link = Link('punctuation', words[index], root, 'CL.PUNCT')
        elif index > boundary.marker:
            link = Link('fixed', words[index], boundary.marker, 'CL.FIXED')
        else:
            scope = _scope(boundary)
            link = Link('clause_marker', words[index], root, 'CL.MARK', scope=scope)
        markers.append(link)
    return tuple(markers)


def _level_attachments(prefix, levels, boundary, leaf, root, words):
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
        if not _allows_mood(boundary, own):
            continue
        if relation == 'conj':
            role, rule = 'clause_conjunct', own.rule if own.rule in ('GAP', 'GAP.REMNANT') else 'CL.CONJ'
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
        host_scope = {'condition': 'conditional', 'concessive_condition': 'conditional', 'alternative': 'alternative', 'adverbial': 'adverbial'}.get(scope)
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


def _attachments(prefix, levels, boundary, leaf, root, words, *, tokens=None, spatial_prefix=None):
    if boundary.relation == 'advcl' and relative_role(boundary.form):
        from .spatial_clauses import attachments

        yield from attachments(prefix, levels, boundary, leaf, root, words, tokens, spatial_prefix)
        return
    paired = boundary.relation == 'correlative'
    if paired or (boundary.form == 'когда' and boundary.relation == 'advcl'):
        amount = paired and boundary.form == 'сколько'
        markers = _markers(boundary, root, words)
        links = prefix + (markers[:-1] if amount else markers) + leaf
        found = False
        for level, (_, governor) in enumerate(levels):
            for anchor in degree_clauses.anchors(prefix, boundary.form, governor):
                if amount and (leaf[0].lemma != boundary.form or
                               (prefix[anchor].role == 'numeral' and leaf[0].quantity_kind != 'query')):
                    continue
                found = True
                yield degree_clauses.bind(links, boundary.marker, root, anchor, boundary.form), (
                    levels[:level + 1] + ((root, root),))
        if paired or found:
            return
    for joined, domains in _level_attachments(prefix, levels, boundary, leaf, root, words):
        yield joined, domains
        if boundary.relation != 'advcl':
            continue
        host = joined[root].head
        edge = len(prefix) - 1
        infinitives = []
        while edge is not None and edge != host and prefix[edge] is not None:
            if prefix[edge].role == 'infinitive':
                infinitives.append(edge)
            edge = prefix[edge].head
        if edge != host:
            continue
        for target in infinitives:
            links = list(joined)
            links[root] = replace(links[root], head=target)
            if links[host].scope != prefix[host].scope:
                links[target] = replace(links[target], scope=links[target].scope or links[host].scope)
                links[host] = prefix[host]
            yield tuple(links), domains


def trees(tokens, local, *, budget=256, spatial_prefix=None):
    from .parser import AnalysisBudgetExceeded, Link

    words = tuple(_key(token.surface) for token in tokens)
    yield from local(tokens)
    boundaries = tuple(_boundaries(words))
    if not boundaries:
        return
    size = len(words)
    if any(relative_role(b.form) for b in boundaries) and spatial_prefix is None:
        from .spatial_prefix import SpatialPrefix

        spatial_prefix = SpatialPrefix.from_tokens(tokens)
    remaining = budget

    def spend():
        nonlocal remaining
        if remaining <= 0:
            raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
        remaining -= 1

    @cache
    def leaves(start, stop, spatial=False):
        spend()
        result = []
        if spatial:
            from .spatial_leaves import trees as spatial_leaves

            candidates = spatial_leaves(tokens[start:stop], local, budget)
        else:
            candidates = local(tokens[start:stop])
        for tree in candidates:
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
                    if marker.relation == 'relative':
                        candidates = relative_leaves(marker, stop)
                    elif marker.relation == 'correlative' and marker.form == 'сколько':
                        candidates = leaves(marker.marker, stop)
                    else:
                        candidates = leaves(marker.stop, stop, spatial=bool(relative_role(marker.form)))
                    if marker.relation == 'conj' and len(levels) == 1:
                        anchor = levels[0][0]
                        parallel = [anchor, *(i for i, link in enumerate(prefix) if link and
                                              link.role == 'clause_conjunct' and link.head == anchor)]
                        gaps = tuple(dict.fromkeys(gap for host in parallel for gap in
                                                   gapped_leaves(tokens, marker.stop, stop, prefix, host, budget)))
                        if gaps:
                            candidates = (*gaps, *competing_leaves(candidates, marker.stop, gaps))
                    for leaf, root in candidates:
                        for tree, scopes in _attachments(prefix, levels, marker, leaf, root, words,
                                                        tokens=tokens, spatial_prefix=spatial_prefix):
                            if stop == hi:
                                yield tree[lo:], scopes[0][0]
                            else:
                                pending.append((stop, tree, scopes))
                                if len(pending) > budget:
                                    raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')

    yield from degree_clauses.proportional(tokens, local, spend)
    for tree, _ in parse_region(0, size):
        yield tree
    for marker in starts[0]:
        if relative_role(marker.form):
            from .spatial_reverse import trees as reverse_trees

            def components(part):
                return trees(part, local, budget=budget, spatial_prefix=spatial_prefix)
            yield from reverse_trees(tokens, components, budget, spatial_prefix, _preposed_splits(words, marker.stop))
            continue
        if marker.relation != 'advcl' or (marker.form not in _preposed() and marker.form != 'даже если'):
            continue
        for stop, split in _preposed_splits(words, marker.stop):
            conditional = _scope(marker) in ('condition', 'concessive_condition')
            main = split + (conditional and split < size and words[split] == 'то')
            if main >= size:
                continue
            for subordinate, child in parse_region(marker.stop, stop):
                if not _allows_mood(marker, subordinate[child - marker.stop]):
                    continue
                for matrix, root in parse_region(main, size):
                    joined = list(_markers(marker, child, words) + subordinate)
                    joined.extend(Link('punctuation' if i < split else 'clause_marker', words[i], root, 'CL.COND',
                                       scope='conditional' if i >= split else None)
                                  for i in range(stop, main))
                    joined.extend(matrix)
                    if marker.form == 'когда':
                        anchors = tuple(i for i, link in enumerate(matrix) if link.lemma == 'тогда'
                                        and link.role == 'adverb' and link.head == root)
                        if anchors:
                            for anchor in anchors:
                                yield degree_clauses.bind(joined, marker.marker, child, main + anchor, marker.form)
                            continue
                    joined[child] = replace(joined[child], role='clause_adverbial', head=root, rule='CL.ADV',
                                            scope=joined[child].scope or _scope(marker))
                    qualification = {'condition': 'conditional', 'concessive_condition': 'conditional', 'adverbial': 'adverbial'}.get(_scope(marker))
                    joined[root] = replace(joined[root], scope=joined[root].scope or qualification)
                    yield tuple(joined)
