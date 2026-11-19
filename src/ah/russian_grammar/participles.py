from dataclasses import replace
from functools import cache, lru_cache

from . import clauses, morphology, participle_coordination, participle_forms
from .nominal_groups import _groups
from .rules import dictionary, known_forms


_NOMINAL = {'subject', 'object', 'recipient', 'stimulus', 'beneficiary', 'experiencer', 'instrument',
            'oblique', 'governed', 'nominal_conjunct', 'genitive_modifier', 'agent'}
_INSIDE_NOUN = {'attribute', 'possessive', 'name_part', 'numeral', 'numeral_part', 'preposition'}
_REFERENCE = ('head', 'controller', 'antecedent', 'coord_head', 'shared_agent')


def _remap(link, indices):
    return replace(link, **{field: indices[value] for field in _REFERENCE
                            if (value := getattr(link, field)) is not None})


def _hosts(outer, tree, start, end):
    left = sum(i < start for i in outer)
    for after, index in ((True, left - 1), (False, left)):
        while 0 <= index < len(tree):
            link = tree[index]
            if link.role in _NOMINAL:
                yield index, after
                if not after:
                    break
            elif link.role not in _INSIDE_NOUN:
                break
            parent = link.head
            if parent is None or (after and outer[parent] >= start) or (not after and outer[parent] < end):
                break
            index = parent


@lru_cache(maxsize=2048)
def _finite(surface, lemma, tense):
    target = {'VERB', 'indc', 'sing', 'pres', '3per'} if tense == 'pres' else {'VERB', 'indc', 'sing', 'past', 'masc'}
    for parse in dictionary().parse(surface):
        if parse.is_known and parse.normal_form == lemma and parse.tag.POS == 'PRTF':
            word = parse.inflect(target)
            if word and target <= word.tag.grammemes:
                return word.word
    return None


def _regions(tokens, pivot, series):
    size = len(tokens)
    forms = [known_forms(token.surface) for token in tokens]
    commas = {i for i, token in enumerate(tokens) if token.surface == ','}
    finite = {i for i, variants in enumerate(forms) if any(tag.POS == 'VERB' for _, tag in variants)}
    forced = {i for i in finite if all(tag.POS == 'VERB' for _, tag in forms[i])}
    modifiers = {i for i, variants in enumerate(forms) if any(tag.POS == 'PRTF' for _, tag in variants)}
    nominal = {i for i, variants in enumerate(forms) if tokens[i].surface[0].isdigit() or
               any(tag.POS in {'NOUN', 'NPRO', 'ADJF', 'NUMR', 'PRTF'} for _, tag in variants)}
    lo = max((i + 1 for i in forced if i < pivot), default=0)
    hi = min((i for i in forced if i > pivot), default=size)
    if hi < size:
        words = tuple(clauses._key(token.surface) for token in tokens)
        governors = {lemma for i in modifiers if lo <= i < hi for lemma, tag in forms[i] if tag.POS == 'PRTF'}
        if any(pivot < b.marker < hi and (b.relation == 'advcl' or
               (b.relation == 'ccomp' and governors.intersection(b.governors))) for b in clauses._boundaries(words)):
            hi = size
    for start in range(series[0], lo - 1, -1):
        if start in commas:
            continue
        left = start - 1 in commas
        for end in range(series[-1] + 1, hi + 1):
            if end - 1 in commas:
                continue
            right = end in commas
            if start - 1 - left not in nominal and end + right not in nominal:
                continue
            if left and end < size and not right:
                until = next((i for i in range(end, size) if i in commas), size)
                if not any(end <= i < until for i in finite):
                    continue
            outer = (*range(start - left), *range(end + right, size))
            if len(forced.intersection(outer)) > 1 and not modifiers.intersection(outer):
                continue
            yield start, end, outer, left, right


def _bare_instrumentals(tokens, pivot, budget):
    for start in range(len(tokens)):
        for group in _groups(tokens, start, budget, bare_cases={'ablt'}):
            if not group.start <= pivot < group.end:
                yield group


def _inner(tokens, pivot, form, local, budget):
    from .parser import Link
    from .short_participles import instrumental_roles

    finite = _finite(tokens[pivot].surface, form.lemma, form.morphology.tense)
    if not finite:
        return
    if len(tokens) == 1:
        yield (Link('predicate', form.lemma, None, 'V1'),)
        return
    dummy = replace(tokens[pivot], surface='он', end=tokens[pivot].start)
    passive = form.morphology.voice == 'pssv'
    agents = tuple(_bare_instrumentals(tokens, pivot, budget)) if passive else ()
    for agent in (None, *agents):
        kept = tuple(i for i in range(len(tokens)) if agent is None or not agent.start <= i < agent.end)
        indices = (-1, *kept)
        words = (dummy, *(replace(tokens[i], surface=finite) if i == pivot else tokens[i] for i in kept))
        root = indices.index(pivot)
        candidates = clauses.trees(words, local, budget=budget)
        for tree in candidates:
            if tree[root].role != 'predicate' or tree[root].lemma != form.lemma or tree[root].head is not None:
                continue
            if tree[0].role != 'subject' or tree[0].head != root or any(link.head == 0 for link in tree[1:]):
                continue
            if passive and any(link.role == 'object' and link.head == root for link in tree):
                continue
            if passive and any(link.case == 'ablt' and link.head == root and link.role == 'oblique'
                               for link in tree):
                continue
            links = {i: _remap(link, indices) for i, link in zip(kept, tree[1:])}
            if agent is None:
                yield tuple(links[i] for i in range(len(tokens)))
                continue
            if any(link.role == 'governed' and link.head < agent.start < i for i, link in links.items()):
                continue
            for role in instrumental_roles(tokens, agent, form.lemma):
                if role == 'oblique' and any(tag.POS == 'ADVB' for _, tag in known_forms(tokens[agent.noun].surface)):
                    continue
                links[agent.noun] = Link(role, agent.lemma, pivot, 'PART.ARG', case='ablt')
                links.update(agent.extra)
                yield tuple(links[i] for i in range(len(tokens)))


def trees(tokens, local, *, budget=256):
    from .parser import AnalysisBudgetExceeded, Link

    remaining = budget

    def bounded(candidates):
        found = {}
        for tree in candidates:
            found[tree] = None
            if len(found) > budget:
                raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
        return tuple(found)

    @cache
    def parse(part):
        return bounded(derive(part))

    linked = cache(participle_coordination.linked_members)

    @cache
    def inside(part, pivot, form):
        if pivot in linked(part):
            return ()
        return bounded(_inner(part, pivot, form, parse, budget))

    def branches(region, position, matches):
        for form in matches[position]:
            for tree in inside(region, position, form):
                root = participle_coordination.as_modifier(tree[position], form)
                yield (*tree[:position], root, *tree[position + 1:])
        yield from participle_coordination.branches(region, position, matches, inside, _remap, budget)

    def derive(part):
        nonlocal remaining
        pivots = [i for i, token in enumerate(part) if participle_forms.readings(token.surface)]
        required = [i for i in pivots if all(tag.POS == 'PRTF' for _, tag in known_forms(part[i].surface))]
        if not required:
            yield from local(part)
        for pivot in required[:1] or pivots:
            for start, end, outer, left, right in _regions(part, pivot, linked(part).get(pivot, (pivot,))):
                remaining -= 1
                if remaining < 0:
                    raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
                outside = tuple(part[i] for i in outer)
                for raw in parse(outside):
                    matrix = morphology.annotate(outside, raw)
                    for host, after in _hosts(outer, matrix, start, end):
                        noun = matrix[host]
                        quantity = next((i for i, link in enumerate(matrix)
                                         if link.role == 'numeral' and link.head == host), None)
                        region = part[start:end]
                        position = pivot - start
                        matches = {i: participle_forms.matching(
                            word.surface, noun, quantity=matrix[quantity] if quantity is not None else None,
                            external_case=noun.case, after=after, detached=left or right,
                            before_quantity=quantity is not None and start + i < outer[quantity])
                                   for i, word in enumerate(region) if participle_forms.readings(word.surface)}
                        matches = {i: choices for i, choices in matches.items() if choices}
                        if position not in matches:
                            continue
                        for branch in branches(region, position, matches):
                            anchors = {i: start + i for i in range(len(branch))}
                            anchors[-1] = outer[host]
                            links = {i: _remap(link, outer) for i, link in zip(outer, raw)}
                            links.update((start + i, _remap(link, anchors)) for i, link in enumerate(branch))
                            if left:
                                links[start - 1] = Link('punctuation', ',', pivot, 'PART.PUNCT')
                            if right:
                                links[end] = Link('punctuation', ',', pivot, 'PART.PUNCT')
                            yield tuple(links[i] for i in range(len(part)))

    for tree in derive(tokens):
        if participle_coordination.complete(tree):
            yield tree
