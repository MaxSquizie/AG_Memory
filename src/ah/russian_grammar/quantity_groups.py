from collections import defaultdict
from dataclasses import dataclass, replace
from functools import cache, lru_cache
from itertools import product

from .case_arguments import _lexicon as _case_lexicon
from .morphology import Morphology, from_tag
from .nominal_groups import POSSESSIVES
from .prepositions import CASE_NAMES
from .rules import dictionary, known_forms


_EXTERNAL_CASE = {'subject': 'nomn', 'object': 'accs', 'duration': 'accs', 'experiencer': 'datv'}
_NOMINAL = {'subject', 'object', 'duration', 'experiencer', 'recipient', 'beneficiary', 'stimulus',
            'oblique', 'instrument', 'governed', 'nominal_conjunct', 'predicate'}
_SUBJECT = {'masc': 'он', 'femn': 'она', 'neut': 'оно'}


@dataclass(frozen=True)
class Group:
    start: int
    noun: int
    lemma: str
    morphology: Morphology
    case: str
    surface: str
    subject_only: bool
    links: tuple


@lru_cache(maxsize=4096)
def _inflect(surface, lemma, original, case, number):
    required = {case, number}
    for variant in dictionary().parse(surface):
        if variant.normal_form == lemma and variant.tag == original:
            form = variant.inflect(required)
            if form and required <= form.tag.grammemes:
                return form.word
    return None


def _surfaces(token, lemma, tag, expression, case):
    if case != 'nomn':
        surface = _inflect(token.surface, lemma, tag, case, tag.number)
        if surface:
            yield surface, False
        return
    for number, gender in expression.agreement(case, tag):
        if number == 'sing' and gender in _SUBJECT and tag.gender != gender:
            yield _SUBJECT[gender], True
        else:
            surface = _inflect(token.surface, lemma, tag, case, number)
            if surface:
                yield surface, False
            elif number == 'sing' and gender in _SUBJECT:
                yield _SUBJECT[gender], True


def _attributes(variants, noun, expression, case):
    if expression.kind == 'fraction' and noun.number == 'sing' and noun.case == 'gent':
        return [(lemma, tag) for lemma, tag in variants if tag.case == 'gent'
                and (tag.number == 'plur' or tag.gender in (None, noun.gender))]
    if expression.kind == 'ordinal' or (noun.number == 'sing' and noun.case == case):
        return [(lemma, tag) for lemma, tag in variants if tag.number == noun.number and tag.case == case
                and (tag.number == 'plur' or tag.gender in (None, noun.gender))
                and (not tag.animacy or tag.animacy == noun.animacy)]
    if case in ('nomn', 'accs') and noun.case == 'gent':
        cases = {'gent'}
        if noun.number == 'sing' and noun.gender == 'femn':
            cases.add(case)
    else:
        cases = {case}
    return [(lemma, tag) for lemma, tag in variants if tag.number == 'plur' and tag.case in cases
            and (not tag.animacy or tag.animacy == noun.animacy)]


def _groups(tokens, start, expression, budget):
    from .parser import AnalysisBudgetExceeded, Link

    qualifiers = []
    for noun in range(expression.end, len(tokens)):
        forms = known_forms(tokens[noun].surface)
        for lemma, tag in forms:
            if tag.POS != 'NOUN' or not tag.number:
                continue
            for case in CASE_NAMES:
                if not expression.compatible(case, tag, lemma):
                    continue
                parts = expression.parts_for(case, tag)
                links = [(start, Link('numeral', parts[0][0], noun, 'NUM.GROUP',
                                      morphology=parts[0][1], quantity=expression.value,
                                      quantity_kind=expression.kind))]
                links.extend((i, Link('numeral_part', part, start, 'NUM.PART', morphology=morph))
                             for i, (part, morph) in enumerate(parts[1:], start + 1))
                sizes = 1
                options = []
                for k, candidates in enumerate(qualifiers, expression.end):
                    allowed = []
                    for adj, form in _attributes(candidates, tag, expression, case):
                        role = 'possessive' if adj in POSSESSIVES else 'attribute'
                        allowed.append((k, Link(role, adj, noun, 'P.POSS' if role == 'possessive' else 'A1',
                                                morphology=from_tag(form))))
                    options.append(tuple(dict.fromkeys(allowed)))
                    sizes *= len(options[-1])
                if sizes > budget:
                    raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
                for surface, subject_only in _surfaces(tokens[noun], lemma, tag, expression, case):
                    for selected in product(*options):
                        yield Group(start, noun, lemma, from_tag(tag), case, surface, subject_only,
                                    (*links, *selected))
        adjectives = [(lemma, tag) for lemma, tag in forms
                      if tag.POS == 'ADJF' and ('Apro' not in tag or lemma in POSSESSIVES)
                      and 'Anum' not in tag]
        if not adjectives:
            break
        qualifiers.append(adjectives)


def _ordinary_attribute(tree, groups):
    for group in groups:
        first = tree[group.start]
        numeric = group.links[0][1]
        if first.lemma != numeric.lemma:
            continue
        if first.role == 'attribute' and first.head == group.noun:
            return True
        if (first.role == 'adverb' and numeric.quantity_kind in {'indefinite', 'query'}
                and tree[group.noun].lemma == group.lemma and tree[group.noun].role in _NOMINAL):
            return True
    return False


def _case_licensed(group, head, governor):
    from .numerals import known_unit

    if head.rule != 'V.GOV':
        return True
    if head.role in {'recipient', 'beneficiary'} and group.case == 'datv' and known_unit(group.lemma):
        return False
    if group.case in {'gent', 'gen2'} and head.role == 'object' and group.links[0][1].quantity is not None:
        _, roles = _case_lexicon()
        if roles.get((governor.lemma, 'gen2')) == 'object' and 'negated' not in (governor.scope or ''):
            return False
    return True


def _restore(tree, kept, picked):
    links = {i: replace(link, **{key: kept[value] for key in ('head', 'controller', 'antecedent')
                                 if (value := getattr(link, key)) is not None})
             for i, link in zip(kept, tree)}
    for group in picked:
        head = links[group.noun]
        if head.role not in _NOMINAL or (group.subject_only and head.role != 'subject'):
            return
        if head.lemma != (group.surface if group.subject_only else group.lemma):
            return
        case = head.case or _EXTERNAL_CASE.get(head.role)
        if head.role == 'predicate' and head.rule == 'V2':
            if group.case == 'nomn' or (group.case == 'ablt' and any(link.role == 'copula'
                    and link.head == group.noun for link in links.values())):
                case = group.case
        if case != group.case:
            return
        if head.head is not None and not _case_licensed(group, head, links[head.head]):
            return
        links[group.noun] = replace(head, lemma=group.lemma, case=case, morphology=group.morphology)
        links.update(group.links)
    return tuple(links[i] for i in range(len(links)))


def trees(tokens, local, *, budget=256):
    from .numerals import expressions
    from .parser import AnalysisBudgetExceeded

    starts = defaultdict(list)
    for i in range(len(tokens)):
        longest = None
        for expression in sorted(expressions(tokens, i), key=lambda x: x.end, reverse=True):
            if longest is not None and expression.end < longest:
                break
            for group in _groups(tokens, i, expression, budget):
                longest = expression.end
                if group not in starts[i]:
                    starts[i].append(group)
                    if len(starts[i]) > budget:
                        raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
    if not starts:
        yield from local(tokens)
        return

    @cache
    def reduced(words):
        result = []
        for tree in local(words):
            result.append(tree)
            if len(result) > budget:
                raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
        return result

    groups = [g for choices in starts.values() for g in choices]
    optional = {i for i in starts if any(tag.POS in ('NOUN', 'ADJF', 'NPRO', 'ADVB', 'VERB', 'CONJ')
                                        for _, tag in known_forms(tokens[i].surface))}
    pending = [(0, ())]
    results = set()
    examined = 0
    while pending:
        index, picked = pending.pop()
        while index < len(tokens) and index not in starts:
            index += 1
        if index < len(tokens):
            if index in optional:
                pending.append((index + 1, picked))
            pending.extend((g.noun + 1, (*picked, g)) for g in starts[index])
            continue
        examined += 1
        if examined > budget:
            raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
        heads = {g.noun: g for g in picked}
        hidden = {i for g in picked for i in range(g.start, g.noun)}
        kept = tuple(i for i in range(len(tokens)) if i not in hidden)
        words = tuple(replace(tokens[i], surface=heads[i].surface) if i in heads else tokens[i] for i in kept)
        for tree in reduced(words):
            restored = _restore(tree, kept, picked) if picked else tree
            if restored and restored not in results and not _ordinary_attribute(restored, groups):
                results.add(restored)
                if len(results) > budget:
                    raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
                yield restored
