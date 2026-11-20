from dataclasses import replace

from . import clauses
from .parser import Link, _span_label
from .passive_arguments import _phrases
from .probe import Probe
from .utterances import _map, _root


def trees(tokens, parse, budget):
    for end, phrase in _phrases(tokens, 0):
        marker = end + 1
        comma = marker < len(tokens) and tokens[marker].surface == ','
        marker += int(comma)
        words = tuple(clauses._key(t.surface) for t in tokens[marker:])
        if not any(b.start == 0 and b.relation == 'advcl' and b.form in clauses._preposed()
                   for b in clauses._boundaries(words)):
            continue
        for tree in parse(tokens[marker:]):
            if tree[0].role != 'clause_marker' or tree[tree[0].head].role != 'clause_adverbial':
                continue
            main, dependent = marker + _root(tree), marker + tree[0].head
            links = _map(tree, range(marker, len(tokens)))
            links.update(phrase)
            if comma:
                links[end + 1] = Link('punctuation', ',', end, 'CL.INTRO.PUNCT')
            for host in (main, dependent):
                for scope in (None, 'qualification'):
                    links[0] = replace(phrase[0], head=host, scope=scope)
                    yield tuple(links[i] for i in range(len(tokens)))


def confirmation(tokens, tree, i, text):
    if tree[i].rule == 'APP.FOREIGN':
        return Probe(f'Какое иноязычное обозначение поясняет слово «{_span_label(tokens, tree[i].head)}»?',
                     (_span_label(tokens, i),), text)
    return None
