"""Dictionary evidence and agreement rules for the simple verbal clause."""
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.resources import files

from pymorphy3 import MorphAnalyzer

from .prepositions import CASE_NAMES, FORMS, GOVERNMENT, PREFIXES, STRESSED_VOWEL


# Lexical evidence for the bare accusative of duration. Extensible, not exhaustive.
TIME_UNITS = frozenset('секунда минута час сутки день ночь неделя месяц год век'.split())


def unaccented(surface):
    return STRESSED_VOWEL.sub('', surface)


class _RussianMorphology(MorphAnalyzer):
    def parse(self, word):
        return super().parse(unaccented(word))


@lru_cache(maxsize=1)
def dictionary():
    return _RussianMorphology()


@lru_cache(maxsize=2)
def _attested_nouns(resource_name='attested_nouns.tsv'):
    forms = {}
    resource = files(__package__).joinpath('lexicon', resource_name)
    for line in resource.read_text(encoding='utf-8').splitlines():
        surface, lemma, tag = line.split('\t')
        forms.setdefault(surface, []).append((lemma, dictionary().TagClass(tag)))
    return {surface: tuple(readings) for surface, readings in forms.items()}


def attested_name_parts(surface):
    return _attested_nouns('attested_name_parts.tsv').get(unaccented(surface).casefold(), ())


@lru_cache(maxsize=4096)
def known_forms(surface):
    from .lexical_parts import forms

    return forms(surface) or _attested_nouns().get(unaccented(surface).casefold(), ())


@lru_cache(maxsize=1024)
def plain_person_reference(surface: str) -> bool:
    nominatives = [tag for _, tag in known_forms(surface) if tag.case == 'nomn']
    return bool(nominatives) and all('Name' in tag or tag.POS == 'NPRO' for tag in nominatives)


@dataclass(frozen=True)
class Reading:
    lemma: str
    role: str
    case: str | None
    number: str | None
    gender: str | None
    person: str | None
    animacy: str | None
    transitive: bool
    name_type: str | None = None
    opaque: bool = False


def name_type(tag):
    return next((kind for kind in ('Name', 'Patr', 'Surn') if kind in tag), None)


def name_continuations(surface, parts):
    first = parts[0]
    order = tuple(part.name_type for part in parts)
    patterns = (('Name', 'Patr', 'Surn'), ('Name', 'Surn'), ('Surn', 'Name', 'Patr'))
    for lemma, tag in known_forms(surface):
        kind = name_type(tag)
        extended = (*order, kind)
        if tag.POS != 'NOUN' or not any(pattern[:len(extended)] == extended for pattern in patterns):
            continue
        if tag.case != first.case or tag.number != 'sing':
            continue
        if any(part.gender and tag.gender and part.gender != tag.gender for part in parts):
            continue
        yield Reading(lemma, 'name_part', tag.case, tag.number, tag.gender, None, tag.animacy, False, kind)


def preposition_reading(lemma: str, role: str) -> Reading:
    return Reading(lemma, role, None, None, None, None, None, False)


@lru_cache(maxsize=4096)
def readings(surface: str, preposition: str | None = None) -> tuple[Reading, ...]:
    result = []
    word = unaccented(surface).lower()
    if preposition is None:
        if word in PREFIXES:
            result.append(preposition_reading(word, 'prep_prefix'))
        if word in FORMS:
            result.append(preposition_reading(FORMS[word], 'preposition'))
    for lemma, tag in known_forms(surface):
        if preposition is not None:
            if tag.case not in (GOVERNMENT.get(preposition) or CASE_NAMES):
                continue
            # The nominative-shaped complement of в (идти в гости) is animate plural.
            if preposition == 'в' and tag.case == 'nomn' and (
                    tag.number != 'plur' or (tag.POS == 'NOUN' and tag.animacy != 'anim')):
                continue
            if tag.POS == 'ADJF' and 'Apro' not in tag:
                role = 'group_attribute'
            elif tag.POS in {'NOUN', 'NPRO'}:
                # Dative derivative prepositions can take the plain pronoun (благодаря ему).
                if (tag.POS == 'NPRO' and tag.person == '3per' and 'Af-p' not in tag
                        and (tag.case != 'datv' or preposition in {'к', 'по'})):
                    continue
                role = 'governed'
            else:
                continue
        elif tag.POS == 'PREP':
            prep = preposition_reading(FORMS.get(word, lemma), 'preposition')
            if prep not in result:
                result.append(prep)
            continue
        elif tag.POS in {'NOUN', 'NPRO'} and tag.case in ('nomn', 'accs'):
            role = 'subject' if tag.case == 'nomn' else 'object'
        elif tag.POS == 'VERB' and tag.mood == 'indc' and 'Impe' not in tag:
            role = 'predicate'
        elif tag.POS == 'ADJF' and tag.case in ('nomn', 'accs') and 'Apro' not in tag:
            role = 'attribute'
        elif tag.POS == 'CONJ' and surface.lower() == 'и':
            role = 'coordinator'
        else:
            continue
        person = tag.person
        if tag.POS == 'NOUN' or (tag.POS == 'NPRO' and tag.case == 'nomn' and person is None):
            person = '3per'
        reading = Reading(lemma, role, tag.case, tag.number, tag.gender,
                          person, tag.animacy, 'tran' in tag, name_type(tag),
                          'Abbr' in tag and not tag.number and lemma == surface)
        if reading not in result:
            result.append(reading)
            if role == 'object' and reading.lemma in TIME_UNITS:
                result.append(replace(reading, role='duration'))
    return tuple(result)


def subject_agrees(subject: Reading, verb: Reading) -> bool:
    if subject.number != verb.number and not subject.opaque:
        return False
    if verb.person and subject.person != verb.person:
        return False
    # First/second person personal pronouns do not specify the speaker's gender.
    return not (verb.gender and subject.gender and verb.gender != subject.gender)


def attribute_agrees(attribute: Reading, nominal: Reading) -> bool:
    case = {'loc2': 'loct', 'gen2': 'gent'}.get(nominal.case, nominal.case)
    if attribute.case != case:
        return False
    if nominal.opaque:
        return True
    if not attribute.number or attribute.number != nominal.number:
        return False
    if attribute.number == 'sing' and attribute.gender != nominal.gender:
        return False
    return not (attribute.animacy and nominal.animacy and attribute.animacy != nominal.animacy)
