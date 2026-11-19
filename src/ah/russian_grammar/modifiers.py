from bisect import bisect_left
from dataclasses import replace
from itertools import product

from .morphology import NOMINAL_ROLES
from .prepositions import FORMS, PREFIXES
from .rules import Reading, known_forms


def _remap(link, indices):
    return replace(link, head=None if link.head is None else indices[link.head],
                   controller=None if link.controller is None else indices[link.controller])


def _particles(words):
    groups = {}
    i = 0
    while i < len(words):
        end = i
        scope = None
        if words[i] in {'чуть', 'едва'}:
            end += 1
            if end < len(words) and words[end] == 'было':
                end += 1
            if end < len(words) and words[end] == 'не':
                scope = 'averted'
        if words[i] in {'только', 'лишь'}:
            scope = 'exclusive'
        if scope is None and words[i] == 'не':
            end = i
            scope = 'negated'
        if scope and end + 1 < len(words):
            groups[end + 1] = (range(i, end + 1), scope)
            i = end + 1
        else:
            i += 1
    return groups


def _apply_particles(words, links, groups, conditional):
    from .parser import Link

    for host, (positions, scope) in groups.items():
        if host not in links:
            return False
        if scope in {'negated', 'exclusive'} and links[host].role in NOMINAL_ROLES:
            links[host] = replace(links[host], scope='focus_' + scope)
            for i in positions:
                links[i] = Link('particle', words[i], host, 'F.NP')
            continue
        if links[host].role not in {'predicate', 'infinitive', 'converb', 'copula', 'auxiliary'}:
            return False
        target = links[host].head if links[host].role in {'copula', 'auxiliary'} else host
        enclosing = links[target].scope
        if enclosing and links[target].role != 'infinitive':
            return False
        links[target] = replace(links[target], scope=f'{enclosing}_{scope}' if enclosing else scope)
        for i in positions:
            links[i] = Link('particle', words[i], target, {'averted': 'N2', 'exclusive': 'F.V'}.get(scope, 'N1'))
    if conditional:
        carriers = [i for i, link in links.items() if link.role in {'predicate', 'copula'}
                    and any(lemma == link.lemma and tag.POS == 'VERB' and tag.tense == 'past'
                            for lemma, tag in known_forms(words[i]))]
        if len(carriers) != 1 or len(conditional) != 1:
            return False
        carrier, = carriers
        target = links[carrier].head if links[carrier].role == 'copula' else carrier
        scope = links[target].scope
        links[target] = replace(links[target], scope='conditional' + ('_' + scope if scope else ''))
        i, = conditional
        links[i] = Link('particle', words[i], target, 'N3')
    return True


def _decorate(tokens, base, budget):
    from .parser import AnalysisBudgetExceeded, Link

    words = [t.surface.casefold() for t in tokens]
    groups = _particles(words)
    conditional = {i for i, word in enumerate(words) if word in {'бы', 'б'}}
    if any(i and words[i - 1] in {'как', 'будто', 'словно', 'вроде', 'хотя'} for i in conditional):
        return
    particles = conditional | {i for positions, _ in groups.values() for i in positions}
    adverbs = {}
    optional = []
    for i, word in enumerate(words):
        if i in particles or i in groups:
            continue
        forms = known_forms(word)
        lemmas = tuple(dict.fromkeys(lemma for lemma, tag in forms if tag.POS == 'ADVB'))
        if lemmas:
            adverbs[i] = lemmas
            if word in FORMS or word in PREFIXES or any(tag.POS not in {'ADVB', 'CONJ'} for _, tag in forms):
                optional.append(i)
    if not particles and not adverbs:
        yield from base(tokens)
        return
    if (1 << len(optional)) > budget:
        raise AnalysisBudgetExceeded('MODIFIER_BUDGET')
    for retain in product((False, True), repeat=len(optional)):
        bare = adverbs.keys() - {i for i, keep in zip(optional, retain) if keep}
        kept = tuple(i for i in range(len(tokens)) if i not in particles and i not in bare)
        for tree in base(tuple(tokens[i] for i in kept)):
            links = {i: _remap(link, kept) for i, link in zip(kept, tree)}
            if not _apply_particles(words, links, groups, conditional):
                continue
            choices = []
            predicates = [j for j in kept if links[j].role == 'predicate']
            for i in sorted(bare):
                cut = bisect_left(kept, i)
                neighbors = kept[max(0, cut - 1):cut + 1]
                hosts = [j for j in neighbors if links[j].role in {'predicate', 'infinitive', 'attribute', 'converb'}]
                if not hosts:
                    hosts = predicates
                choices.append(tuple((i, Link('adverb', lemma, j, 'B1'))
                                     for j in hosts for lemma in adverbs[i]))
            for bindings in product(*choices):
                merged = links.copy()
                merged.update(bindings)
                yield tuple(merged[i] for i in range(len(tokens)))


def _converb_trees(tokens, budget):
    from .parser import AnalysisBudgetExceeded, Prefix

    subject = Reading('', 'subject', 'nomn', 'sing', None, None, None, False)
    states = {Prefix(words=(subject,), subject=0): None}
    for token in tokens:
        next_states = {}
        for state in states:
            forms = [Reading(lemma, 'predicate', None, 'sing', None, None, None, 'tran' in tag)
                     for lemma, tag in known_forms(token.surface) if tag.POS == 'GRND']
            forms.extend(r for r in state.next_readings(token.surface) if r.role not in {'predicate', 'subject'})
            for form in forms:
                candidate = state.extend(form)
                if candidate is not None:
                    next_states[candidate] = None
                    if len(next_states) > budget:
                        raise AnalysisBudgetExceeded('MODIFIER_BUDGET')
        states = next_states
        if not states:
            return
    for state in states:
        for tree in state.structures():
            if all(link.head != 0 for link in tree[1:]):
                yield tuple(replace(link, head=None if link.head is None else link.head - 1)
                            for link in tree[1:])


def _regions(tokens, pivot):
    left = pivot
    while left and tokens[left - 1].surface != ',':
        left -= 1
    right = pivot + 1
    while right < len(tokens) and tokens[right].surface != ',':
        right += 1
    if left or right < len(tokens):
        yield left, right
    else:
        for start in range(left, pivot + 1):
            for end in range(pivot + 1, right + 1):
                if start or end < len(tokens):
                    yield start, end


def _adjective_hosts(tokens, tree, left, tag):
    cases = {'subject': 'nomn', 'object': 'accs', 'duration': 'accs', 'experiencer': 'datv'}
    i = left
    while i is not None:
        link = tree[i]
        if link.role in cases or link.role == 'governed':
            case = link.case or cases.get(link.role)
            for lemma, noun in known_forms(tokens[i].surface):
                if (lemma == link.lemma and noun.POS in {'NOUN', 'NPRO'} and noun.case == case == tag.case
                        and noun.number == tag.number and (noun.number == 'plur' or noun.gender == tag.gender)
                        and (tag.animacy is None or noun.animacy is None or noun.animacy == tag.animacy)):
                    yield i
                    break
        elif link.role not in {'attribute', 'preposition'}:
            break
        i = link.head


def _with_attributes(tokens, base, budget, region_budget):
    from .parser import AnalysisBudgetExceeded, Link

    yield from _decorate(tokens, base, budget)
    commas = [i for i, token in enumerate(tokens) if token.surface == ',']
    for left, right in zip(commas, [*commas[1:], len(tokens)]):
        if not left or left + 1 >= right:
            continue
        adj = right - 1
        adjectives = [(lemma, tag) for lemma, tag in known_forms(tokens[adj].surface)
                      if tag.POS == 'ADJF' and 'Apro' not in tag]
        if not adjectives:
            continue
        choices = []
        for i in range(left + 1, adj):
            lemmas = {lemma for lemma, tag in known_forms(tokens[i].surface) if tag.POS == 'ADVB'}
            choices.append([(i, Link('adverb', lemma, host, 'B1')) for lemma in sorted(lemmas)
                            for host in range(i + 1, adj + 1)])
        if not all(choices):
            continue
        if next(region_budget, None) is None:
            raise AnalysisBudgetExceeded('MODIFIER_BUDGET')
        kept = tuple(i for i in range(len(tokens)) if i < left or i > right)
        outer = tuple(tokens[i] for i in kept)
        for tree in _with_attributes(outer, base, budget, region_budget):
            for lemma, tag in adjectives:
                for host in _adjective_hosts(outer, tree, left - 1, tag):
                    links = {i: _remap(link, kept) for i, link in zip(kept, tree)}
                    links[adj] = Link('attribute', lemma, kept[host], 'A2')
                    links[left] = Link('punctuation', ',', adj, 'A2')
                    if right < len(tokens):
                        links[right] = Link('punctuation', ',', adj, 'A2')
                    for bindings in product(*choices):
                        links.update(bindings)
                        yield tuple(links[i] for i in range(len(tokens)))


def structures(tokens, base_function, *, budget=256):
    return _structures(tokens, base_function, budget, iter(range(budget)))


def _converb_hosts(matrix, outer, start):
    for i, link in enumerate(matrix):
        if (link.role == 'subject' and link.head is not None and matrix[link.head].role == 'predicate'
                and matrix[link.head].head is None):
            yield outer[i], outer[link.head]
        if link.role == 'predicate' and link.head is None and link.implicit_subject:
            yield None, outer[i]
    cut = bisect_left(outer, start)
    if cut == 0:
        return
    visited = set()
    for j in (cut - 1, cut):
        while j is not None and j < len(matrix) and j not in visited:
            visited.add(j)
            link = matrix[j]
            if link.role == 'infinitive':
                yield None if link.controller is None else outer[link.controller], outer[j]
            j = link.head


def _neighboring_converbs(matrix, outer, start):
    cut = bisect_left(outer, start)
    neighbors = set()
    for i in range(max(0, cut - 1), min(len(matrix), cut + 1)):
        while matrix[i].role in {'adverb', 'governed', 'preposition', 'attribute', 'object', 'punctuation'}:
            i = matrix[i].head
            if i is None:
                break
        if i is not None and matrix[i].role == 'converb':
            neighbors.add(outer[i])
    return sorted(neighbors)


def _structures(tokens, base_function, budget, region_budget):
    from .parser import AnalysisBudgetExceeded, Link

    pivots = [i for i, token in enumerate(tokens) if any(tag.POS == 'GRND' for _, tag in known_forms(token.surface))]
    if not pivots:
        yield from _with_attributes(tokens, base_function, budget, region_budget)
        return
    if all(any(tag.POS != 'GRND' for _, tag in known_forms(tokens[i].surface)) for i in pivots):
        yield from _with_attributes(tokens, base_function, budget, region_budget)
    seen = set()
    required = [i for i in pivots if all(tag.POS == 'GRND' for _, tag in known_forms(tokens[i].surface))]
    for pivot in required[:1] or pivots:
        for start, end in _regions(tokens, pivot):
            if (start, end) in seen:
                continue
            seen.add((start, end))
            if next(region_budget, None) is None:
                raise AnalysisBudgetExceeded('MODIFIER_BUDGET')
            inner = tuple(range(start, end))
            commas = tuple(i for i in (start - 1, end) if 0 <= i < len(tokens) and tokens[i].surface == ',')
            outer = tuple(i for i in range(len(tokens)) if not start <= i < end and i not in commas)
            if not outer:
                continue
            for part in _converb_series(tuple(tokens[i] for i in inner), budget):
                converbs = [i for i, link in zip(inner, part) if link.role == 'predicate']
                converb = converbs[0]
                for matrix in _structures(tuple(tokens[i] for i in outer), base_function, budget, region_budget):
                    for controller, head in _converb_hosts(matrix, outer, start):
                        links = {i: _remap(link, outer) for i, link in zip(outer, matrix)}
                        links.update((i, _remap(link, inner)) for i, link in zip(inner, part))
                        for member in converbs:
                            links[member] = replace(links[member], role='converb', rule='D1',
                                                    head=head, controller=controller,
                                                    implicit_subject=links[head].implicit_subject if controller is None else None)
                        links.update((i, Link('punctuation', ',', converb, 'D1')) for i in commas)
                        tree = tuple(links[i] for i in range(len(tokens)))
                        yield tree
                        for neighbor in _neighboring_converbs(matrix, outer, start):
                            if tree[neighbor].head != head or tree[neighbor].controller != controller:
                                continue
                            for dependent, parent in ((converb, neighbor), (neighbor, converb)):
                                yield (*tree[:dependent], replace(tree[dependent], head=parent), *tree[dependent + 1:])

def _converb_series(tokens, budget):
    from .case_arguments import trees
    from .parser import AnalysisBudgetExceeded, Link

    def single(part):
        return _decorate(part, lambda ts: trees(ts, lambda bare: _converb_trees(bare, budget),
                                                budget=budget, verb_pos=('GRND',)), budget)

    yield from single(tokens)
    markers = [i for i, token in enumerate(tokens) if token.surface.casefold() == 'и']
    if not markers:
        return
    states = [()]
    for start, end in zip([0, *(i + 1 for i in markers)], [*markers, len(tokens)]):
        indices = tuple(range(start, end))
        if not any(tag.POS == 'GRND' for i in indices for _, tag in known_forms(tokens[i].surface)):
            return
        following = []
        for tree in single(tokens[start:end]):
            root = next(i for i, link in zip(indices, tree) if link.role == 'predicate')
            marker = (Link('coordinator', 'и', root, 'D.COORD'),) if start else ()
            extension = marker + tuple(_remap(link, indices) for link in tree)
            following.extend(state + extension for state in states)
            if len(following) > budget:
                raise AnalysisBudgetExceeded('MODIFIER_BUDGET')
        states = following
    yield from states
