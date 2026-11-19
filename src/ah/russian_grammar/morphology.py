from dataclasses import dataclass, fields, replace
from functools import lru_cache
from itertools import product

from .prepositions import CASE_NAMES
from .rules import known_forms


@dataclass(frozen=True)
class Morphology:
    pos: str | None = None
    case: str | None = None
    number: str | None = None
    gender: str | None = None
    person: str | None = None
    tense: str | None = None
    aspect: str | None = None
    mood: str | None = None
    voice: str | None = None
    animacy: str | None = None
    transitivity: str | None = None


FEATURES = tuple(item.name for item in fields(Morphology))


@lru_cache(maxsize=8192)
def from_tag(tag):
    if tag.POS == 'ADJF' and {'Fixd', 'Apro'} <= tag.grammemes:
        return Morphology(pos='ADJF')
    return Morphology(**{key: str(value) for key in FEATURES
                         if (value := getattr(tag, 'POS' if key == 'pos' else key)) is not None})


def _common(forms):
    if not forms:
        return None
    if len(forms) == 1:
        return forms[0]
    shared = {}
    for key in FEATURES:
        values = {getattr(form, key) for form in forms}
        if len(values) == 1:
            shared[key] = values.pop()
    return Morphology(**shared)


NOMINAL_ROLES = {'subject', 'object', 'duration', 'recipient', 'experiencer', 'governed',
                 'nominal_conjunct', 'event_argument', 'agent', 'instrument', 'oblique'}
PREDICATE_ROLES = {'predicate', 'clause_complement', 'clause_conjunct', 'clause_relative', 'clause_adverbial'}
ROLE_POS = {
    'copula': {'VERB'}, 'auxiliary': {'VERB'}, 'attribute': {'ADJF'}, 'possessive': {'ADJF'},
    'infinitive': {'INFN'}, 'converb': {'GRND'}, 'adverb': {'ADVB'}, 'coordinator': {'CONJ'},
    'clause_marker': {'CONJ', 'PRCL'}, 'particle': {'PRCL', 'ADVB'}, 'preposition': {'PREP'},
}
ROLE_CASE = {'subject': 'nomn', 'object': 'accs', 'duration': 'accs', 'experiencer': 'datv'}
CASE_EQUIVALENTS = {'loc2': 'loct', 'gen2': 'gent'}


def _allows(link, tag):
    pos = tag.POS
    if link.role in PREDICATE_ROLES:
        if link.rule == 'V2.PASS':
            return pos == 'PRTS'
        if link.rule == 'V2':
            return pos in {'NOUN', 'ADJF', 'ADJS', 'PRTS'} and tag.case in (None, 'nomn', 'ablt')
        if link.rule == 'V3':
            return pos == 'PRED' or 'Prdx' in tag or 'Impe' in tag
        if link.rule == 'V.FUT':
            return pos == 'INFN' and tag.aspect == 'impf'
        if link.rule in ('V1', 'V.IMP'):
            return pos == 'VERB' and tag.mood == ('impr' if link.rule == 'V.IMP' else 'indc')
        return pos in {'VERB', 'PRED', 'ADJF', 'ADJS', 'PRTS', 'NOUN'} or 'Prdx' in tag
    if link.role == 'name_part':
        return pos == 'ADJF' if link.rule == 'NAME.EPITHET' else pos == 'NOUN'
    if link.role in ROLE_POS:
        return pos in ROLE_POS[link.role] and (link.role != 'auxiliary' or tag.mood == 'indc')
    if link.case or link.role in NOMINAL_ROLES:
        case = link.case or ROLE_CASE.get(link.role)
        return pos in {'NOUN', 'NPRO'} and (case is None or tag.case == case)
    return True


def _domains(tokens, tree):
    domains = []
    for token, link in zip(tokens, tree):
        if link.morphology is not None:
            domains.append((link.morphology,))
            continue
        surface = link.recovery.corrected if link.recovery else token.surface
        choices = (from_tag(tag) for lemma, tag in known_forms(surface) if lemma == link.lemma and _allows(link, tag))
        domains.append(tuple(dict.fromkeys(choices)))
    return domains


def _agree(role, child, head):
    if child.number and head.number and child.number != head.number:
        return False
    if child.number == 'sing' and child.gender and head.gender and child.gender != head.gender:
        return False
    if role in ('attribute', 'possessive', 'name_part'):
        if child.animacy and head.animacy and child.animacy != head.animacy:
            return False
        return CASE_EQUIVALENTS.get(child.case, child.case) == CASE_EQUIVALENTS.get(head.case, head.case)
    if role == 'subject':
        person = '3per' if child.pos == 'NOUN' else child.person
        return not (person and head.person and person != head.person)
    return True


def _restrict(tree, domains):
    dependencies = []
    for i, link in enumerate(tree):
        if link.head is None:
            continue
        if link.role in ('subject', 'attribute', 'name_part', 'possessive'):
            if link.role == 'subject' and any(form.pos == 'NOUN' for form in domains[link.head]):
                continue
            dependencies.append((i, link.head, link.role))
    changed = True
    while changed:
        changed = False
        for i, head, role in dependencies:
            left, right = domains[i], domains[head]
            if not left or not right or (len(left) == len(right) == 1):
                continue
            pairs = [(a, b) for a in left for b in right if _agree(role, a, b)]
            if not pairs:
                continue
            updated_left, updated_right = (tuple(dict.fromkeys(parts)) for parts in zip(*pairs))
            if len(updated_left) < len(left) or len(updated_right) < len(right):
                changed = True
                domains[i], domains[head] = updated_left, updated_right


def _decorate(tree, morphs):
    result = list(morphs)
    for link, form in zip(tree, morphs):
        if link.role != 'auxiliary' or form is None:
            continue
        i = link.head
        if i is not None and result[i] is not None:
            result[i] = replace(result[i], tense=form.tense, person=form.person, number=form.number, mood=form.mood)
    for link in tree:
        if link.rule == 'N3' and link.head is not None and result[link.head] is not None:
            i = link.head
            result[i] = replace(result[i], mood='cond')
    return tuple(replace(link, morphology=form) for link, form in zip(tree, result))


def annotate(tokens, tree):
    domains = _domains(tokens, tree)
    _restrict(tree, domains)
    return _decorate(tree, [_common(forms) for forms in domains])


def variants(tokens, tree, *, budget=256):
    from .parser import AnalysisBudgetExceeded

    domains = _domains(tokens, tree)
    for link in tree:
        if link.role == 'object' and link.head is not None and link.case in (None, 'accs', 'acc2'):
            forms = domains[link.head]
            if forms:
                compatible = tuple(form for form in forms if form.transitivity != 'intr')
                if not compatible:
                    return
                domains[link.head] = compatible
    _restrict(tree, domains)
    slots = []
    size = 1
    for forms in domains:
        if len(forms) > 1 and all(form.pos in {'VERB', 'INFN', 'GRND', 'PRTS'} for form in forms):
            by_meaning = {}
            for form in forms:
                by_meaning.setdefault((form.tense, form.aspect, form.mood, form.transitivity), []).append(form)
            options = tuple(_common(group) for group in by_meaning.values())
        else:
            options = (_common(forms),)
        slots.append(options)
        size *= len(options)
        if size > budget:
            raise AnalysisBudgetExceeded('MORPHOLOGY_BUDGET')
    for selection in product(*slots):
        yield _decorate(tree, selection)


MEANINGS = {
    'tense': {'past': 'it is in the past tense', 'pres': 'it is in the present tense',
              'futr': 'it is in the future tense'},
    'mood': {'cond': 'it describes a hypothetical situation', 'impr': 'it asks someone to act',
             'indc': 'it describes an action in the indicative mood'},
    'aspect': {'perf': 'the verb presents the action as a bounded whole',
               'impf': 'the verb uses the imperfective aspect'},
    'number': {'sing': 'it is singular', 'plur': 'it is plural'},
    'person': {'1per': 'it is first person', '2per': 'it is second person', '3per': 'it is third person'},
    'transitivity': {'tran': 'this sense of the verb can take a direct object («кого?» or «что?»)',
                     'intr': 'this sense of the verb cannot take a direct object'},
    'case': {code: f'it is in the {name} case' for code, name in {
        **CASE_NAMES, 'voct': 'vocative', 'gen1': 'first genitive',
        'acc2': 'second accusative', 'loc1': 'first prepositional'}.items()},
    'gender': {'masc': 'it is masculine', 'femn': 'it is feminine', 'neut': 'it is neuter'},
    'animacy': {'anim': 'it takes animate agreement', 'inan': 'it takes inanimate agreement'},
    'voice': {'actv': 'the participle describes someone or something performing the action',
              'pssv': 'the participle describes someone or something undergoing the action'},
    'pos': {code: f'it functions as {name}' for code, name in {
        'NOUN': 'a noun', 'NPRO': 'a pronoun', 'ADJF': 'a full adjective', 'ADJS': 'a short adjective',
        'COMP': 'a comparative', 'VERB': 'a finite verb', 'INFN': 'an infinitive',
        'PRTF': 'a full participle', 'PRTS': 'a short participle', 'GRND': 'a converb',
        'NUMR': 'a numeral', 'ADVB': 'an adverb', 'PRED': 'a predicative',
        'PREP': 'a preposition', 'CONJ': 'a conjunction', 'PRCL': 'a particle',
        'INTJ': 'an interjection'}.items()},
}


def feature_choices(morphologies):
    for key, meanings in MEANINGS.items():
        values = [getattr(form, key, None) for form in morphologies]
        if len(set(values)) < 2:
            continue
        for value, text in meanings.items():
            if value in values:
                yield text, [x == value for x in values]
