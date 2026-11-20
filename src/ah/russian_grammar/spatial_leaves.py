from .ellipsis import one_member
from .morphology import from_tag
from .parser import Link
from .participle_connectives import relations
from .rules import known_forms
from .spatial_prefix import deictic_role
from .utterances import _map


def _states(tokens):
    for root, token in enumerate(tokens):
        forms = known_forms(token.surface)
        if not any(tag.POS == 'ADVB' for _, tag in forms):
            continue
        if any(not deictic_role(t.surface) for i, t in enumerate(tokens) if i != root):
            continue
        for lemma, tag in forms:
            if tag.POS == 'ADJS' and 'Qual' in tag and tag.number == 'sing' and tag.gender == 'neut':
                yield tuple(Link('predicate', lemma, None, 'V2', morphology=from_tag(tag)) if i == root
                            else Link('adverb', t.surface.casefold(), root, 'B1') for i, t in enumerate(tokens))


def trees(tokens, local, budget):
    yield from local(tokens)
    yield from _states(tokens)
    if len(tokens) == 1:
        yield from one_member(tokens, True, budget)
    for i, token in enumerate(tokens[:-1]):
        if i and not deictic_role(tokens[i - 1].surface):
            continue
        if (not any(tag.POS == 'PRCL' for _, tag in known_forms(token.surface))
                or set(relations(token.surface)) != {'addition'}):
            continue
        positions = (*range(i), *range(i + 1, len(tokens)))
        for tree in local(tuple(tokens[j] for j in positions)):
            if tree[i].role != 'predicate':
                continue
            links = _map(tree, positions)
            links[i] = Link('particle', token.surface.casefold(), i + 1, 'PART.FOCUS', scope='focus')
            yield tuple(links[j] for j in range(len(tokens)))
