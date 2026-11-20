from dataclasses import replace
from functools import cache
from itertools import product

from .converb_control import _object_adjectives
from .morphology import _common, from_tag
from .nominal_groups import _agree, _markers, _prepositions
from .parser import AnalysisBudgetExceeded, Link
from .participle_connectives import relations
from .prepositions import DASHES, GOVERNMENT
from .rules import dictionary, known_forms
from .utterances import _map


def _attributes(word):
    forms = known_forms(word)
    if forms:
        return [(lemma, tag, 'A1') for lemma, tag in forms if tag.POS in {'ADJF', 'PRTF'}]
    if not word or not all(c.isalpha() or c in '-‐‑' for c in word):
        return ()
    return [(p.normal_form, p.tag, 'OPAQUE.ATTRIBUTE') for p in dictionary().parse(word)
            if p.tag.POS == 'ADJF']


def _nominals(tokens, start, cases, head, role):
    modifiers = []
    for index in range(start, len(tokens)):
        surface = tokens[index].surface
        for lemma, tag in known_forms(surface):
            if tag.POS not in {'NOUN', 'NPRO'} or tag.case not in cases:
                continue
            attrs = []
            for offset, variants in enumerate(modifiers, start):
                matching = {}
                for adj, form, rule in variants:
                    if _agree(form, tag):
                        matching.setdefault((adj, rule), []).append(from_tag(form))
                attrs.append(tuple((offset, Link('attribute', adj, index, rule, morphology=_common(tags)))
                                   for (adj, rule), tags in matching.items()))
            for selected in product(*attrs):
                yield index, {**dict(selected), index: Link(role, lemma, head, 'P1' if role == 'governed' else 'N.GEN',
                                                            str(tag.case), morphology=from_tag(tag))}
        choices = _attributes(surface)
        if not choices:
            break
        modifiers.append(choices)


def _groups(tokens, start):
    for first, prep in _prepositions(tokens, start):
        cases = GOVERNMENT.get(prep, ())
        for noun, nominal in _nominals(tokens, first, cases, start, 'governed'):
            parts = {k: Link('prep_part', tokens[k].surface.casefold(), start, 'P1')
                     for k in range(start + 1, first)}
            group = {start: Link('preposition', prep, None, 'P2'), **parts, **nominal}
            yield noun + 1, noun, group
            for end, genitive in _nominals(tokens, noun + 1, {'gent', 'gen2'}, noun, 'genitive_modifier'):
                yield end + 1, end, {**group, **genitive}


def _passive(tokens, parse, budget):
    finite = [i for i, token in enumerate(tokens)
              if any(tag.POS == 'PRTS' and tag.voice == 'pssv' for _, tag in known_forms(token.surface))]
    if len(finite) != 1:
        return
    root, = finite
    start = root + 1
    if start == len(tokens) or not any(_prepositions(tokens, start)):
        return
    if not any(tag.case == 'gent' for token in tokens[start:] for _, tag in known_forms(token.surface)):
        return
    groups = cache(lambda at: tuple(_groups(tokens, at)))
    yielded = 0
    for tree in parse(tokens[:start]):
        if tree[root].rule != 'V2.PASS' or tree[root].head is not None:
            continue
        pending = [(start, dict(enumerate(tree)), (root,), False)]
        while pending:
            index, links, spine, expanded = pending.pop()
            if index == len(tokens):
                if expanded:
                    yielded += 1
                    if yielded > budget:
                        raise AnalysisBudgetExceeded('PREDICATIVE_GROUP_BUDGET')
                    yield tuple(links[i] for i in range(len(tokens)))
                continue
            comma = tokens[index].surface == ','
            at = index + int(comma)
            if at >= len(tokens):
                continue
            for end, last, group in groups(at):
                for slot, host in enumerate(spine):
                    attached = {**links, **group, at: replace(group[at], head=host)}
                    if comma:
                        attached[index] = Link('punctuation', ',', at, 'PP.BOUNDARY')
                    noun = next(j for j, l in group.items() if l.role == 'governed')
                    branch = (noun, last) if last != noun else (noun,)
                    pending.append((end, attached, (*spine[:slot + 1], *branch), expanded or last != noun))
                if len(pending) > budget:
                    raise AnalysisBudgetExceeded('PREDICATIVE_GROUP_BUDGET')


def _adverbs(token):
    return sorted({lemma for lemma, tag in known_forms(token.surface) if tag.POS == 'ADVB'})


def _qualifiers(tokens, start, stop, head, budget):
    choices = []
    count = 1
    for i in range(start, stop):
        readings = _adverbs(tokens[i])
        if not readings:
            return
        targets = (head,) if i + 1 == stop else (i + 1, head)
        variants = [(i, Link('adverb', lemma, target, 'ADV.MOD')) for lemma in readings for target in targets]
        count *= len(variants)
        if count > budget:
            raise AnalysisBudgetExceeded('ADVERB_ATTACHMENT_BUDGET')
        choices.append(variants)
    for selected in product(*choices):
        yield dict(selected)


def _property_ends(tokens, start, obj, governor, number, gender, budget):
    def properties(i):
        return [(lemma, tag) for lemma, tag in known_forms(tokens[i].surface) if tag.POS == 'ADJF'
                and tag.case == 'ablt' and tag.number == number and (number == 'plur' or tag.gender == gender)]

    for i in range(start, len(tokens)):
        adjectives = properties(i)
        if adjectives:
            for prefix in _qualifiers(tokens, start, i, i, budget):
                for lemma, tag in adjectives:
                    first = Link('predicative_complement', lemma, governor, 'D.RESULT', 'ablt',
                                 controller=obj, morphology=from_tag(tag))
                    pending = [(i + 1, {**prefix, i: first}, (i,))]
                    while pending:
                        stop, links, heads = pending.pop()
                        yield stop, links, heads
                        for marker in _markers(tokens, stop):
                            adj = marker[-1] + 1
                            if adj >= len(tokens):
                                continue
                            marks = {k: Link('coordinator' if k == stop else 'coordinator_part',
                                             tokens[k].surface.casefold(), adj if k == stop else stop, 'A.COORD')
                                     for k in marker}
                            for word, form in properties(adj):
                                conjunct = Link('nominal_conjunct', word, i, 'A.COORD', 'ablt',
                                                controller=obj, morphology=from_tag(form))
                                pending.append((adj + 1, {**links, **marks, adj: conjunct}, (*heads, adj)))
        if not _adverbs(tokens[i]):
            break


def _initial_groups(tokens, last, budget):
    front = [{}]
    start = 0
    if tokens and relations(tokens[0].surface):
        front = [{0: Link('coordinator', tokens[0].surface.casefold(), None, 'CL.COORD', scope=reading)}
                 for reading in relations(tokens[0].surface)]
        start = 1
    for prefix in front:
        yield start, prefix, None
        for i in range(start, last):
            for end, _, group in _groups(tokens[:last], i):
                noun = next(k for k, link in group.items() if link.role == 'governed')
                for qualifiers in _qualifiers(tokens, start, i, noun, budget):
                    yield end, {**prefix, **qualifiers, **group}, i
            if not _adverbs(tokens[i]):
                break


def _supplement(tokens, start, hosts):
    from .clauses import _boundaries, _scope

    if start == len(tokens):
        yield {}
        return
    enclosed = tokens[start].surface == '(' and tokens[-1].surface == ')'
    first = start + int(enclosed)
    last = len(tokens) - 1 - int(enclosed)
    if first >= last:
        return
    words = tuple(t.surface.casefold() for t in tokens[first:last])
    readings = [marker for marker in _boundaries(words) if marker.marker == 0 and marker.relation == 'advcl']
    for marker, lemma in product(readings, _adverbs(tokens[last])):
        modifiers = {}
        for i in range(first + marker.stop, last):
            if tokens[i].surface in DASHES:
                modifiers[i] = Link('punctuation', tokens[i].surface, last, 'PUNCT')
                continue
            adverbs = _adverbs(tokens[i])
            particles = [l for l, tag in known_forms(tokens[i].surface) if tag.POS == 'PRCL']
            if adverbs:
                modifiers[i] = Link('adverb', adverbs[0], last, 'ADV.MOD')
            elif particles:
                modifiers[i] = Link('particle', particles[0], last, 'PART')
            else:
                break
        else:
            modifiers[first] = Link('clause_marker', marker.form, last, 'CL.MARK', scope=_scope(marker))
            for k in range(first + 1, first + marker.stop):
                modifiers[k] = Link('marker_part', tokens[k].surface.casefold(), first, 'CL.MARK')
            if enclosed:
                for i in (start, last + 1):
                    modifiers[i] = Link('punctuation', tokens[i].surface, last, 'PUNCT')
            for host in hosts:
                yield {**modifiers, last: Link('adverb', lemma, host, 'PAREN.EXPL', scope='qualification')}


def _resultative(tokens, parse, budget):
    governors = [i for i, token in enumerate(tokens) if any(tag.POS == 'INFN' and lemma in _object_adjectives()
                 for lemma, tag in known_forms(token.surface))]
    if len(governors) != 1:
        return
    inf, = governors
    if not any(tag.POS == 'ADJF' and tag.case == 'ablt' for token in tokens[inf + 1:]
               for _, tag in known_forms(token.surface)):
        return
    yielded = 0
    for core, prefix, prep in _initial_groups(tokens, inf, budget):
        for tree in parse(tokens[core:inf + 1]):
            if tree[-1].role != 'infinitive' or tree[-1].lemma not in _object_adjectives():
                continue
            actions = [j + core for j, link in enumerate(tree) if link.role in ('predicate', 'infinitive')]
            root = next(j + core for j, link in enumerate(tree) if link.head is None)
            for j, obj in enumerate(tree):
                if obj.role != 'object' or obj.head != inf - core or (obj.case and obj.case != 'accs'):
                    continue
                forms = {(tag.number, tag.gender) for lemma, tag in known_forms(tokens[core + j].surface)
                         if lemma == obj.lemma and tag.case == 'accs'}
                for number, gender in forms:
                    for end, properties, heads in _property_ends(tokens, inf + 1, core + j, inf, number, gender, budget):
                        for qualifier in _supplement(tokens, end, (*heads, *actions)):
                            for host in (actions if prep is not None else (None,)):
                                links = {**prefix, **_map(tree, range(core, inf + 1)), **properties, **qualifier}
                                for k in prefix:
                                    if links[k].head is None:
                                        links[k] = replace(links[k], head=host if k == prep else root)
                                yielded += 1
                                if yielded > budget:
                                    raise AnalysisBudgetExceeded('RESULTATIVE_BUDGET')
                                yield tuple(links[i] for i in range(len(tokens)))


def trees(tokens, parse, budget):
    yield from _passive(tokens, parse, budget)
    yield from _resultative(tokens, parse, budget)
