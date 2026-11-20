from dataclasses import replace

from .morphology import CASE_EQUIVALENTS, from_tag
from .nominal_groups import _agree, _prepositions
from .prepositions import GOVERNMENT, group_heads
from .rules import known_forms


def _opaque(surface):
    return surface.istitle() and surface.isalpha() and not known_forms(surface)


def _subject(tokens, index, predicate):
    from .parser import Link

    surface = tokens[index].surface
    if _opaque(surface):
        yield Link('subject', surface, None, 'OPAQUE.SUBJECT', 'nomn')
    for lemma, tag in known_forms(surface):
        if tag.POS in ('NOUN', 'NPRO') and tag.case == 'nomn' and tag.number == predicate.number:
            if not tag.gender or not predicate.gender or tag.gender == predicate.gender or 'Ms-f' in tag:
                yield Link('subject', lemma, None, 'S1', morphology=from_tag(tag))


def _phrases(tokens, start):
    from .parser import Link

    for first, prep in _prepositions(tokens, start):
        allowed = GOVERNMENT.get(prep)
        if not allowed:
            continue
        parts = {i: Link('prep_part', tokens[i].surface.casefold(), start, 'P1') for i in range(start + 1, first)}
        parts[start] = Link('preposition', prep, None, 'P2')
        attrs = []
        for i in range(first, len(tokens)):
            word = tokens[i].surface
            if i == first and _opaque(word):
                cases = {CASE_EQUIVALENTS.get(case, case) for case in allowed}
                if len(cases) == 1:
                    case, = cases
                    yield i, {**parts, i: Link('governed', word, start, 'OPAQUE.GOVERNED', case)}
            forms = known_forms(word)
            for lemma, tag in forms:
                if tag.POS not in ('NOUN', 'NPRO') and 'Subx' not in tag:
                    continue
                if tag.case not in allowed and CASE_EQUIVALENTS.get(tag.case) not in allowed:
                    continue
                readings = [next(((l, t) for l, t in choices if _agree(t, tag)), None) for choices in attrs]
                if any(r is None for r in readings):
                    continue
                links = {j: Link('attribute', l, i, 'A1', morphology=from_tag(t))
                         for j, (l, t) in enumerate(readings, first)}
                yield i, {**parts, **links, i: Link('governed', lemma, start, 'P1', str(tag.case), morphology=from_tag(tag))}
            adjectives = [(l, t) for l, t in forms if t.POS in ('ADJF', 'PRTF')]
            if not adjectives:
                break
            attrs.append(adjectives)


def _layouts(tokens, root, aux, predicate, budget):
    from .parser import AnalysisBudgetExceeded

    remaining = budget * max(1, len(tokens))
    start = (0, {}, (), None, False)
    pending = [start]
    while pending:
        remaining -= 1
        if remaining < 0:
            raise AnalysisBudgetExceeded('PASSIVE_BUDGET')
        i, links, groups, actor, extended = pending.pop()
        if i == len(tokens):
            if actor is not None and extended:
                yield links, groups
            continue
        if i in (root, aux):
            pending.append((i + 1, links, groups, actor, extended))
            continue
        if actor is None:
            for subject in _subject(tokens, i, predicate):
                pending.append((i + 1, {**links, i: replace(subject, head=root)}, groups, i,
                                extended or subject.rule == 'OPAQUE.SUBJECT'))
        for end, phrase in _phrases(tokens, i):
            pending.append((end + 1, {**links, **phrase}, (*groups, (i, end)), actor, True))


def trees(tokens, *, budget):
    from .parser import AnalysisBudgetExceeded, Link

    forms = [known_forms(token.surface) for token in tokens]
    auxiliaries = [(i, tag) for i, vals in enumerate(forms) for lemma, tag in vals
                   if lemma == 'быть' and tag.POS == 'VERB' and tag.mood == 'indc']
    participles = [(i, lemma, tag) for i, vals in enumerate(forms) for lemma, tag in vals
                   if tag.POS == 'PRTS' and tag.voice == 'pssv']
    if len({i for i, _ in auxiliaries}) != 1 or len({i for i, _, _ in participles}) != 1:
        return
    produced = set()
    for aux, tense in auxiliaries:
        for root, lemma, passive in participles:
            if passive.number != tense.number or (passive.gender and tense.gender and passive.gender != tense.gender):
                continue
            aux_form = from_tag(tense)
            pred = replace(from_tag(passive), tense=aux_form.tense, mood=aux_form.mood)
            for links, groups in _layouts(tokens, root, aux, passive, budget):
                links[root] = Link('predicate', lemma, None, 'V2.PASS', morphology=pred)
                links[aux] = Link('copula', 'быть', root, 'V2.COP', morphology=aux_form)
                words = tuple(links[i] for i in range(len(tokens)))
                heads = {i: link.head for i, link in links.items() if link.head is not None}
                for assignments in group_heads(groups, words, root, heads):
                    tree = tuple(replace(link, head=assignments.get(i, link.head)) for i, link in enumerate(words))
                    if tree in produced:
                        continue
                    produced.add(tree)
                    if len(produced) > budget:
                        raise AnalysisBudgetExceeded('PASSIVE_BUDGET')
                    yield tree
