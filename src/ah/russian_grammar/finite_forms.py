from dataclasses import replace
from functools import lru_cache

from .rules import dictionary, known_forms


@lru_cache(maxsize=2048)
def _personal_form(surface, lemma, tag, person, number):
    grammemes = {'VERB', 'indc', person, number}
    for variant in dictionary().parse(surface):
        if not variant.is_known or variant.normal_form != lemma or variant.tag != tag:
            continue
        finite = variant.inflect(grammemes)
        if finite is not None and grammemes <= finite.tag.grammemes:
            return finite.word
    return None


def _agreement_subject(person, number, gender):
    if person == '1per':
        return ('мы', 'speaker_group') if number == 'plur' else ('я', 'speaker')
    if person == '2per':
        return ('вы', 'addressee_group') if number == 'plur' else ('ты', 'addressee')
    if number == 'plur':
        return 'они', 'unresolved'
    return {'femn': 'она', 'neut': 'оно'}.get(gender, 'он'), 'unresolved'


def _restore(tree, indices, tokens, root, lemma, morphology, rule, implicit, auxiliary):
    from .parser import Link

    predicate = tree[root]
    if predicate.rule != 'V1' or predicate.head is not None or predicate.lemma != lemma:
        return
    if morphology.transitivity == 'intr' and any(link.head == root and link.rule == 'O1' for link in tree):
        return
    if auxiliary is not None:
        left, right = sorted((indices[root], auxiliary[0]))
        if any(index is not None and left < index < right and link.role == 'infinitive'
               for index, link in zip(indices, tree)):
            return
    if implicit and (tree[0].role != 'subject' or tree[0].head != root):
        return
    restored = [None] * len(tokens)
    for i, (link, index) in enumerate(zip(tree, indices)):
        if index is None:
            continue
        if implicit and (link.head == 0 or link.antecedent == 0):
            return
        head = None if link.head is None else indices[link.head]
        controller = None if link.controller is None else indices[link.controller]
        antecedent = None if link.antecedent is None else indices[link.antecedent]
        implicit_actor = implicit if i == root or (implicit and link.controller == 0) else link.implicit_subject
        restored[index] = replace(link, head=head, controller=controller, antecedent=antecedent,
                                  implicit_subject=implicit_actor)
    index = indices[root]
    restored[index] = replace(restored[index], rule=rule, morphology=morphology)
    if auxiliary is not None:
        aux_index, aux_morphology = auxiliary
        restored[aux_index] = Link('auxiliary', 'быть', index, 'V.FUT.AUX', morphology=aux_morphology)
    yield tuple(restored)


def _project(tokens, base, root, lemma, surface, morphology, rule, person, number, gender,
             auxiliary=None, explicit=True):
    excluded = None if auxiliary is None else auxiliary[0]
    kept = tuple(i for i in range(len(tokens)) if i != excluded)
    words = tuple(replace(tokens[i], surface=surface) if i == root else tokens[i] for i in kept)
    at = kept.index(root)
    if explicit and (auxiliary is not None or rule == 'V.IMP'):
        for tree in base(words):
            yield from _restore(tree, kept, tokens, at, lemma, morphology, rule, None, auxiliary)
    pronoun, implicit = _agreement_subject(person, number, gender)
    subject = replace(tokens[root], surface=pronoun, end=tokens[root].start)
    indices = (None, *kept)
    for tree in base((subject, *words)):
        yield from _restore(tree, indices, tokens, at + 1, lemma, morphology, rule, implicit, auxiliary)


def trees(tokens, base, *, budget=256):
    from .morphology import from_tag
    from .parser import AnalysisBudgetExceeded

    overt = set()
    for tree in base(tokens):
        for link in tree:
            if link.role == 'subject' and link.head is not None and tree[link.head].rule == 'V1':
                overt.add((link.head, tree[link.head].lemma))
        yield tree
    infinitives = []
    finite = []
    for i, token in enumerate(tokens):
        for lemma, tag in known_forms(token.surface):
            if tag.POS == 'INFN' and tag.aspect == 'impf':
                infinitives.append((i, lemma, tag))
            if tag.POS == 'VERB' and tag.mood in ('indc', 'impr') and tag.number and 'Impe' not in tag:
                finite.append((i, lemma, tag))
    attempts = 0
    for i, lemma, tag in finite:
        attempts += 1
        if attempts > budget:
            raise AnalysisBudgetExceeded('FINITE_BUDGET')
        morph = from_tag(tag)
        if tag.mood == 'indc':
            yield from _project(tokens, base, i, lemma, tokens[i].surface, morph, 'V1',
                                tag.person, tag.number, tag.gender)
        else:
            inclusive = 'incl' in tag
            person = '1per' if inclusive else '2per'
            number = 'plur' if inclusive else tag.number
            surface = _personal_form(tokens[i].surface, lemma, tag, person, number)
            if surface:
                mood = replace(morph, person=person, number=number)
                yield from _project(tokens, base, i, lemma, surface, mood, 'V.IMP', person, number, None,
                                    explicit=not (inclusive and tag.number == 'sing' and (i, lemma) in overt))
        if lemma != 'быть' or tag.tense != 'futr' or tag.mood != 'indc':
            continue
        for j, action, inf in infinitives:
            attempts += 1
            if attempts > budget:
                raise AnalysisBudgetExceeded('FINITE_BUDGET')
            surface = _personal_form(tokens[j].surface, action, inf, tag.person, tag.number)
            if surface is None:
                continue
            future = replace(from_tag(inf), tense='futr', mood='indc', person=tag.person, number=tag.number)
            yield from _project(tokens, base, j, action, surface, future, 'V.FUT', tag.person, tag.number,
                                None, auxiliary=(i, morph))
