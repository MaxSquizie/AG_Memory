from functools import cache
from importlib.resources import files

from .clauses import _connectives, _key
from .nominal_groups import _coordinators


@cache
def _lexicon():
    table = files(__package__).joinpath('lexicon/participle-connectives.tsv')
    meanings = {}
    for line in table.read_text(encoding='utf-8').splitlines():
        word, categories = line.split('\t')
        meanings[_key(word)] = () if categories == 'paired' else tuple(categories.split())
    clausal, _ = _connectives()
    phrases = {phrase for phrase, uses in clausal.items() if 'conj' in uses}
    phrases.update(phrase for variants in _coordinators().values() for phrase in variants)
    phrases.update(tuple(word.split()) for word in meanings)
    starts = {}
    for phrase in sorted(phrases):
        starts.setdefault(phrase[0], []).append(phrase)
    return meanings, starts


def markers(tokens, start):
    if start < len(tokens):
        _, starts = _lexicon()
        for phrase in starts.get(_key(tokens[start].surface), ()):
            end = start + len(phrase)
            if tuple(_key(token.surface) for token in tokens[start:end]) == phrase:
                yield tuple(range(start, end))


def relations(word):
    meanings, _ = _lexicon()
    return meanings.get(_key(word), ())
