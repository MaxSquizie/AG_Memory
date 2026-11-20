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
            'oblique', 'agent', 'instrument', 'governed', 'nominal_conjunct', 'predicate'}
_GAP_ROLES = _NOMINAL | {'auxiliary', 'copula', 'adverb'}
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
    gap: range = range(0)


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


def _groups(tokens, start, expression, budget, *, nominal_start=None):
    from .parser import AnalysisBudgetExceeded, Link

    qualifiers = []
    first = expression.end if nominal_start is None else nominal_start
    for noun in range(first, len(tokens)):
        forms = known_forms(tokens[noun].surface)
        for lemma, tag in forms:
            if tag.POS != 'NOUN' or not tag.number:
                continue
            for case in CASE_NAMES:
                if not expression.compatible(case, tag, lemma):
                    continue
                parts = expression.parts_for(case, tag)
                rule = 'NUM.GROUP' if first == expression.end else 'NUM.SPLIT'
                links = [(start, Link('numeral', parts[0][0], noun, rule,
                                      morphology=parts[0][1], quantity=expression.value,
                                      quantity_kind=expression.kind))]
                links.extend((i, Link('numeral_part', part, start, 'NUM.PART', morphology=morph))
                             for i, (part, morph) in enumerate(parts[1:], start + 1))
                sizes = 1
                options = []
                for k, candidates in enumerate(qualifiers, first):
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
                                    (*links, *selected), range(expression.end, first))
        adjectives = [(lemma, tag) for lemma, tag in forms
                      if tag.POS == 'ADJF' and ('Apro' not in tag or lemma in POSSESSIVES)
                      and 'Anum' not in tag]
        if not adjectives:
            break
        qualifiers.append(adjectives)


def _query_groups(tokens, start, expression, budget):
    yield from _groups(tokens, start, expression, budget)
    if expression.kind != 'query':
        return
    intervening_word = False
    for index in range(expression.end, len(tokens)):
        forms = known_forms(tokens[index].surface)
        if intervening_word and any(tag.POS in {'ADJF', 'NOUN'} for _, tag in forms):
            yield from _groups(tokens, start, expression, budget, nominal_start=index)
        if any(tag.POS in {'VERB', 'NOUN', 'NPRO', 'ADVB'} for _, tag in forms):
            intervening_word = True


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


def _restore(tree, kept, picked, fronted):
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
        if group.gap:
            if group.start in fronted and head.role != 'governed':
                return
            if head.role == 'governed' and head.head >= group.start:
                return
            if not any(i in links and links[i].role in _GAP_ROLES
                       for i in group.gap):
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
            for group in _query_groups(tokens, i, expression, budget):
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
    pending = [(0, (), frozenset())]
    results = set()
    examined = 0
    while pending:
        index, picked, occupied = pending.pop()
        while index < len(tokens) and (index not in starts or index in occupied):
            index += 1
        if index < len(tokens):
            if index in optional:
                pending.append((index + 1, picked, occupied))
            for group in starts[index]:
                members = {group.noun, *(k for k, _ in group.links)}
                if not occupied.intersection(members):
                    pending.append((index + 1, (*picked, group), occupied | members))
            continue
        examined += 1
        if examined > budget:
            raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
        heads = {g.noun: g for g in picked}
        hidden = {i for g in picked for i, _ in g.links}
        fronted = {g.start: g.noun for g in picked if g.gap and g.start > 0
                   and any(tag.POS == 'PREP' for _, tag in known_forms(tokens[g.start - 1].surface))}
        displaced = set(fronted.values())
        kept = tuple(fronted.get(i, i) for i in range(len(tokens))
                     if i in fronted or (i not in hidden and i not in displaced))
        words = tuple(replace(tokens[i], surface=heads[i].surface) if i in heads else tokens[i] for i in kept)
        for tree in reduced(words):
            restored = _restore(tree, kept, picked, fronted) if picked else tree
            if restored and restored not in results and not _ordinary_attribute(restored, groups):
                results.add(restored)
                if len(results) > budget:
                    raise AnalysisBudgetExceeded('QUANTITY_BUDGET')
                yield restored


def age_variants(tree, budget):
    from .adjuncts import _lexicon
    from .numerals import known_unit
    from .parser import AnalysisBudgetExceeded

    yield tree
    datives = [i for i, link in enumerate(tree)
               if link.role == 'oblique' and link.case == 'datv' and link.head is not None]
    if not datives:
        return
    temporal, _ = _lexicon()
    heads = {link.head for link in tree if link.role == 'numeral' and link.quantity is not None}
    subjects = {tree[i].head for i in heads if i is not None and tree[i].role == 'subject'
                and known_unit(tree[i].lemma) and ('nominal', 'когда', '-', tree[i].lemma) in temporal}
    candidates = []
    for i in datives:
        link = tree[i]
        host = tree[link.head]
        if host.lemma == 'быть' and (link.head in subjects or host.role == 'infinitive' and host.head in subjects):
            candidates.append(i)
    if 2 ** len(candidates) > budget:
        raise AnalysisBudgetExceeded('QUANTITY_ARGUMENT_BUDGET')
    for mask in range(1, 2 ** len(candidates)):
        result = list(tree)
        for bit, i in enumerate(candidates):
            if mask & (1 << bit):
                link = tree[i]
                rule = link.rule if link.antecedent is not None else 'NUM.AGE'
                result[i] = replace(link, role='experiencer', rule=rule, scope='age_holder')
        yield tuple(result)
