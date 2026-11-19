from dataclasses import replace

from .morphology import from_tag
from .nominal_groups import _groups
from .parser import Link
from .rules import known_forms


def _nominals(word, case):
    return [(lemma, tag) for lemma, tag in known_forms(word)
            if tag.POS in ('NOUN', 'NPRO') and tag.case == case]


def _span(tokens, start, stop, case, budget):
    if start < stop:
        for group in _groups(tokens[:stop], start, budget, bare_cases=(case,)):
            if group.end == stop:
                yield group


def _place(tree, group, role, head, rule):
    tree[group.noun] = Link(role, group.lemma, head, rule, group.case)
    for index, link in group.extra:
        tree[index] = link


def _negative(tokens, words, budget):
    if words.count('нет') != 1 or words.count('у') != 1:
        return
    verb, prep = words.index('нет'), words.index('у')
    if prep + 1 >= len(tokens):
        return
    for owner in _groups(tokens, prep + 1, budget, bare_cases=('gent',)):
        occupied = {verb, *range(prep, owner.end)}
        remaining = sorted(set(range(len(tokens))) - occupied)
        if not remaining or remaining[-1] - remaining[0] + 1 != len(remaining):
            continue
        for entity in _span(tokens, remaining[0], remaining[-1] + 1, 'gent', budget):
            tree = [None] * len(tokens)
            tree[verb] = Link('predicate', 'нет', None, 'NEG.EXIST', scope='negated')
            tree[prep] = Link('preposition', 'у', verb, 'NEG.EXIST.PREP')
            _place(tree, owner, 'governed', prep, 'NEG.EXIST.OWNER')
            _place(tree, entity, 'object', verb, 'NEG.EXIST.ENTITY')
            yield tuple(tree)


def one_member(tokens, standalone, budget):
    words = tuple(token.surface.casefold() for token in tokens)
    yield from _negative(tokens, words, budget)
    if standalone and len(words) == 1:
        for lemma, tag in _nominals(words[0], 'nomn'):
            if tag.POS == 'NOUN' and 'Name' not in tag and 'Surn' not in tag:
                yield (Link('predicate', lemma, None, 'NOM.EXIST', 'nomn', morphology=from_tag(tag)),)


def gapped_leaves(tokens, start, stop, prefix, host, budget):
    dashes = [i for i in range(start, stop) if tokens[i].surface in ('—', '–', '-')]
    if len(dashes) != 1:
        return
    verb = prefix[host]
    form = verb.morphology
    if not form or form.pos != 'VERB' or form.mood != 'indc' or verb.scope:
        return
    roles = {link.role for link in prefix if link and link.head == host}
    if roles != {'subject', 'object'}:
        return
    root, = dashes
    for subject in _span(tokens, start, root, 'nomn', budget):
        for lemma, tag in _nominals(tokens[subject.noun].surface, 'nomn'):
            if lemma != subject.lemma or form.tense != 'past' and tag.POS == 'NPRO' and not tag.person:
                continue
            agreement = replace(form, number=tag.number,
                                gender=tag.gender if form.tense == 'past' and tag.number == 'sing' else None,
                                person=None if form.tense == 'past' else tag.person or '3per')
            for obj in _span(tokens, root + 1, stop, 'accs', budget):
                tree = [None] * stop
                _place(tree, subject, 'subject', root, 'GAP.SUBJ')
                _place(tree, obj, 'object', root, 'GAP.OBJ')
                tree[root] = Link('predicate', verb.lemma, None, 'GAP', morphology=agreement)
                yield tuple(tree[start:]), root
