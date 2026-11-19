"""Dictionary evidence and agreement rules for the simple verbal clause."""
from dataclasses import dataclass, replace
from functools import lru_cache

from pymorphy3 import MorphAnalyzer

from .prepositions import GOVERNMENT


# Lexical evidence for the bare accusative of duration. Extensible, not exhaustive.
TIME_UNITS = frozenset('секунда минута час сутки день ночь неделя месяц год век'.split())


@lru_cache(maxsize=1)
def dictionary():
    return MorphAnalyzer()


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


@lru_cache(maxsize=4096)
def readings(surface: str, preposition: str | None = None) -> tuple[Reading, ...]:
    result = []
    for parse in dictionary().parse(surface):
        tag = parse.tag
        if not parse.is_known or 'Abbr' in tag:
            continue
        if preposition is not None:
            if tag.case not in GOVERNMENT[preposition]:
                continue
            if tag.POS == 'ADJF' and 'Apro' not in tag:
                role = 'group_attribute'
            elif tag.POS in {'NOUN', 'NPRO'}:
                if tag.POS == 'NPRO' and tag.person == '3per' and 'Af-p' not in tag:
                    continue
                role = 'governed'
            else:
                continue
        elif tag.POS == 'PREP' and parse.normal_form in GOVERNMENT:
            role = 'preposition'
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
        if tag.POS == 'NOUN':
            person = '3per'
        reading = Reading(parse.normal_form, role, tag.case, tag.number, tag.gender,
                          person, tag.animacy, 'tran' in tag)
        if reading not in result:
            result.append(reading)
            if role == 'object' and reading.lemma in TIME_UNITS:
                result.append(replace(reading, role='duration'))
    return tuple(result)


def subject_agrees(subject: Reading, verb: Reading) -> bool:
    if not subject.number or subject.number != verb.number:
        return False
    if verb.person and subject.person != verb.person:
        return False
    # First/second person personal pronouns do not specify the speaker's gender.
    return not (verb.gender and subject.gender and verb.gender != subject.gender)


def attribute_agrees(attribute: Reading, nominal: Reading) -> bool:
    case = {'loc2': 'loct', 'gen2': 'gent'}.get(nominal.case, nominal.case)
    if attribute.case != case or not attribute.number or attribute.number != nominal.number:
        return False
    if attribute.number == 'sing' and attribute.gender != nominal.gender:
        return False
    return not (attribute.animacy and nominal.animacy and attribute.animacy != nominal.animacy)
