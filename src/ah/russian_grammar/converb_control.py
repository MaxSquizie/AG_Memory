from dataclasses import replace
from functools import cache
from importlib.resources import files

from .morphology import from_tag
from .rules import known_forms


@cache
def _object_adjectives():
    table = files(__package__).joinpath('lexicon/object-predicative-adjectives.tsv')
    return frozenset(table.read_text(encoding='utf-8').splitlines())


def object_properties(tokens, parse):
    from .modifiers import _remap
    from .parser import Link

    if not any(lemma in _object_adjectives() and tag.POS == 'GRND' for token in tokens
               for lemma, tag in known_forms(token.surface)):
        return
    for i, token in enumerate(tokens):
        modifiers = [(lemma, tag) for lemma, tag in known_forms(token.surface)
                     if tag.POS == 'ADJF' and tag.case == 'ablt']
        if not modifiers:
            continue
        kept = tuple(j for j in range(len(tokens)) if j != i)
        for tree in parse(tuple(tokens[j] for j in kept)):
            root = next((j for j, link in enumerate(tree) if link.role == 'predicate' and link.head is None), None)
            if root is None or tree[root].lemma not in _object_adjectives():
                continue
            objects = [j for j, link in enumerate(tree) if link.role == 'object' and link.head == root]
            if len(objects) != 1:
                continue
            obj = kept[objects[0]]
            for lemma, adjective in modifiers:
                if not any(noun == tree[objects[0]].lemma and nominal.case == 'accs'
                           and nominal.number == adjective.number
                           and (nominal.number == 'plur' or noun_genders_agree(nominal, adjective))
                           for noun, nominal in known_forms(tokens[obj].surface)):
                    continue
                links = {j: _remap(link, kept) for j, link in zip(kept, tree)}
                links[i] = Link('predicative_complement', lemma, kept[root], 'D.RESULT', 'ablt',
                                controller=obj, morphology=from_tag(adjective))
                built = tuple(links[j] for j in range(len(tokens)))
                yield built
                next_prep = i + 1
                if next_prep < len(built) and built[next_prep].role == 'preposition' and built[next_prep].head == kept[root]:
                    yield (*built[:next_prep], replace(built[next_prep], head=i), *built[next_prep + 1:])


def noun_genders_agree(nominal, adjective):
    return nominal.gender == adjective.gender or not nominal.gender or not adjective.gender or 'Ms-f' in nominal


def needs_confirmation(tree, index):
    link = tree[index]
    if link.role != 'converb' or link.head is None or link.controller is None:
        return False
    host = tree[link.head]
    if host.rule not in {'V2', 'V2.PASS'}:
        return False
    participant = tree[link.controller]
    form = participant.morphology
    return form is None or form.animacy != 'anim'
