from functools import cache
from importlib.resources import files
from itertools import chain

from .morphology import PREDICATE_ROLES
from .numerals import expressions
from .parser import Link
from .quantity_groups import _groups
from .rules import known_forms
from .utterances import _map


@cache
def _units():
    path = files(__package__).joinpath('lexicon/frequency-units.txt')
    return frozenset(path.read_text(encoding='utf8').splitlines())


def _counted(tokens, parse, budget):
    nouns = {i for i, token in enumerate(tokens) if any(lemma in _units() and tag.POS == 'NOUN'
             for lemma, tag in known_forms(token.surface))}
    if not nouns:
        return
    for start in range(max(nouns)):
        if start and any(tag.POS in {'PREP', 'PRCL'} for _, tag in known_forms(tokens[start - 1].surface)):
            continue
        for expression in expressions(tokens, start):
            if expression.kind != 'cardinal' or expression.end not in nouns:
                continue
            for group in _groups(tokens, start, expression, budget):
                if group.case != 'accs' or group.noun != expression.end or group.lemma not in _units():
                    continue
                kept = (*range(start), *range(group.noun + 1, len(tokens)))
                for tree in parse(tuple(tokens[j] for j in kept)):
                    events = [j for j, link in enumerate(tree)
                              if link.role in PREDICATE_ROLES | {'infinitive', 'converb', 'participle'}]
                    if len(events) != 1:
                        continue
                    root = events[0]
                    verb = tree[root]
                    if (verb.role != 'predicate' or verb.scope or not verb.morphology
                            or verb.morphology.pos not in {'VERB', 'PRTS'}):
                        continue
                    if (verb.morphology.transitivity == 'tran'
                            and not any(link.head == root and link.role == 'object' for link in tree)):
                        continue
                    links = _map(tree, kept)
                    links.update(group.links)
                    links[group.noun] = Link('frequency', group.lemma, kept[root], 'EVENT.COUNT', case='accs',
                                            morphology=group.morphology)
                    yield tuple(links[j] for j in range(len(tokens)))


def trees(tokens, parse, budget):
    counted = _counted(tokens, parse, budget)
    first = next(counted, None)
    if first is not None:
        yield from chain((first,), counted)
        yield from parse(tokens)
