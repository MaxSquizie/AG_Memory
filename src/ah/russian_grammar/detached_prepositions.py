from dataclasses import replace

from .homogeneous import _restore
from .nominal_groups import _prepositions
from .morphology import PREDICATE_ROLES


def trees(tokens, parse):
    from .parser import Link

    commas = [i for i, token in enumerate(tokens) if token.surface == ',']
    for left, right in zip(commas, commas[1:]):
        if not left or right + 1 == len(tokens) or right < left + 3:
            continue
        start = left + 1
        if not any(_prepositions(tokens[:right], start)):
            continue
        kept = tuple(i for i in range(len(tokens)) if i not in (left, right))
        for tree in parse(tuple(tokens[i] for i in kept)):
            links = _restore(tree, kept, len(tokens))
            prep = links[start]
            if prep.role != 'preposition' or prep.head is None or left < prep.head < right:
                continue
            if any(link and link.head is not None and left < link.head < right
                   for j, link in enumerate(links) if not left < j < right):
                continue
            if any(links[j].head is None or not left < links[j].head < right
                   for j in range(start + 1, right)):
                continue
            heads = [j for j in range(start + 1, right) if links[j].role == 'governed' and links[j].head == start]
            if len(heads) != 1:
                continue
            for j in (left, right):
                links[j] = Link('punctuation', ',', heads[0], 'PP.DETACHED.COMMA')
            links[start] = replace(prep, rule='PP.DETACHED')
            yield tuple(links)
            if links[prep.head].role in PREDICATE_ROLES:
                links[start] = replace(links[start], scope='qualification')
                yield tuple(links)
