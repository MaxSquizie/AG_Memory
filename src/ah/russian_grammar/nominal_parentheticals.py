from functools import cache
from importlib.resources import files

from .morphology import PREDICATE_ROLES
from .probe import Probe
from .utterances import _map, _root


@cache
def _phrases():
    resource = files(__package__).joinpath('lexicon/nominal-parentheticals.tsv')
    return {tuple(phrase.split()): (prep, noun) for phrase, prep, noun in
            (line.split('\t') for line in resource.read_text(encoding='utf8').splitlines())}


def trees(tokens, parse):
    from .parser import Link

    for i in range(len(tokens) - 1):
        entry = _phrases().get((tokens[i].surface.casefold(), tokens[i + 1].surface.casefold()))
        if not entry:
            continue
        before = i > 0 and tokens[i - 1].surface == ','
        after = i + 2 < len(tokens) and tokens[i + 2].surface == ','
        kept = tuple(j for j in range(len(tokens)) if j < i - before or j >= i + 2 + after)
        if not kept:
            continue
        for tree in parse(tuple(tokens[j] for j in kept)):
            root = _root(tree)
            if tree[root].role != 'predicate' or any(link.role in PREDICATE_ROLES for j, link in enumerate(tree) if j != root):
                continue
            links = _map(tree, kept)
            links[i] = Link('case', entry[0], i + 1, 'UTT.PARENT.CASE')
            links[i + 1] = Link('parenthetical', entry[1], kept[root], 'UTT.PARENT.GROUP')
            for j in range(i - before, i + 2 + after):
                if j not in links:
                    links[j] = Link('punctuation', ',', i + 1, 'UTT.PUNCT')
            yield tuple(links[j] for j in range(len(tokens)))


def confirmation(tokens, tree, i, text):
    if tree[i].rule != 'UTT.PARENT.GROUP':
        return None
    from .parser import _span_label
    phrase = _span_label(tokens, i - 1, i + 1)
    return Probe(f'Выберите «{phrase}», если это вводное замечание рассказчика ко всему сообщению.', (phrase,), text)


def partitions(trees, tokens, text):
    for i in range(1, len(tokens)):
        marked = [tree[i].rule == 'UTT.PARENT.GROUP' for tree in trees]
        if any(marked) and not all(marked):
            probe = confirmation(tokens, trees[marked.index(True)], i, text)
            word, = probe.options
            other = 'сочетание входит в состав предложения как обычный член'
            yield Probe(probe.question, (word, other), text), [word if yes else other for yes in marked]
