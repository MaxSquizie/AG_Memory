from dataclasses import dataclass
from functools import lru_cache

from .morphology import CASE_EQUIVALENTS, Morphology, _common, from_tag
from .rules import known_forms


@dataclass(frozen=True)
class ParticipleForm:
    lemma: str
    morphology: Morphology


@lru_cache(maxsize=2048)
def readings(surface):
    return tuple(dict.fromkeys(ParticipleForm(lemma, from_tag(tag))
                               for lemma, tag in known_forms(surface) if tag.POS == 'PRTF'))


def _nominal(noun):
    if isinstance(noun, Morphology):
        return noun
    if hasattr(noun, 'morphology'):
        return noun.morphology
    return from_tag(noun)


def _same_case(left, right):
    return CASE_EQUIVALENTS.get(left, left) == CASE_EQUIVALENTS.get(right, right)


def _ordinary(form, noun):
    if form.number != noun.number or not _same_case(form.case, noun.case):
        return False
    return form.number == 'plur' or not noun.gender or form.gender == noun.gender


def agrees(form, noun, *, quantity=None, external_case=None, detached=False, after=True, before_quantity=False):
    head = _nominal(noun)
    if head is None or head.pos not in {'NOUN', 'NPRO'}:
        return False
    word = form.morphology
    if word.animacy and head.animacy and word.animacy != head.animacy:
        return False
    kind = getattr(quantity, 'quantity_kind', None) or getattr(quantity, 'kind', None)
    if kind is None or kind == 'ordinal':
        return _ordinary(word, head)
    case = external_case or getattr(noun, 'case', None) or head.case
    if case not in {'nomn', 'accs'} or head.case != 'gent':
        return _ordinary(word, head)
    if kind in {'fraction', 'query', 'indefinite'} and _ordinary(word, head):
        return True
    if word.number != 'plur':
        return False
    if before_quantity:
        return word.case == case
    if word.case == 'gent':
        return True
    if after or detached:
        return word.case == case
    return head.number == 'sing' and head.gender == 'femn' and word.case == case


def matching(surface, noun, **position):
    groups = {}
    for form in readings(surface):
        if agrees(form, noun, **position):
            word = form.morphology
            key = form.lemma, word.voice, word.tense, word.aspect, word.transitivity
            groups.setdefault(key, []).append(word)
    return tuple(ParticipleForm(key[0], _common(forms)) for key, forms in groups.items())
