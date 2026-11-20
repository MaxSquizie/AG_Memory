from functools import cache
from importlib.resources import files


@cache
def _dimensions():
    predicates = {}
    units = set()
    table = files(__package__).joinpath('lexicon/measure-questions.tsv')
    for line in table.read_text(encoding='utf8').splitlines():
        kind, lemma, dimension = line.split('\t')
        if kind == 'predicate':
            predicates[lemma] = dimension
        elif kind == 'unit':
            units.add((lemma, dimension))
    return predicates, units


def measure_unit(predicate, unit):
    predicates, units = _dimensions()
    return (unit, predicates.get(predicate)) in units


def _slot(tree):
    focus = tree[0]
    if focus.lemma != 'сколько' or focus.head is None:
        return None
    predicate = tree[focus.head]
    if predicate.role != 'predicate' or predicate.lemma not in _dimensions()[0]:
        return None
    arguments = [part.role for part in tree[1:] if part.head == focus.head and part.role != 'punctuation']
    if arguments != ['subject'] or focus.scope or focus.antecedent is not None:
        return None
    return focus.head, tree[1:]


def coalesce(analyses):
    if len(analyses) < 2:
        return analyses
    objects = {_slot(tree) for tree in analyses if tree[0].role == 'object' and tree[0].quantity_kind == 'query'}
    objects.discard(None)
    return tuple(tree for tree in analyses if tree[0].role != 'adverb' or _slot(tree) not in objects)
