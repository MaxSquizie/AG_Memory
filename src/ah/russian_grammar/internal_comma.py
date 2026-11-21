from .homogeneous import _restore
from .nominal_groups import _agree, genitive_ordinals
from .prepositions import FORMS
from .rules import known_forms, readings, subject_agrees


class BoundaryChoice(Exception):
    def __init__(self, sites, tokens, text):
        from .parser import _span_label
        from .probe import Probe

        self.part = tokens
        self.options = {_span_label(tokens, i - 1, i + 2).replace(' ,', ','): tokens[i].start for i in sites}
        self.options['сохранить все запятые'] = None
        question = 'В каком сочетании слова связаны напрямую, несмотря на запятую между ними?'
        if any(tree[i].head not in (i - 1, i + 1) for i, variants in sites.items() for tree in variants):
            question = 'В каком сочетании запятая разрывает единую группу слов?'
        if any(tree[i - 1].role == 'genitive_modifier' and tree[i - 1].head is not None
               and tree[tree[i - 1].head].rule == 'S.COLLECTIVE' and tree[tree[i - 1].head].head == i + 1
               for i, variants in sites.items() for tree in variants):
            question = 'В каком месте запятая разделяет связанные между собой члены предложения?'
        if any(_predicative_neighbors(tree[i - 1], tree[i + 1], tree)
               for i, variants in sites.items() for tree in variants):
            question = 'В каком месте запятая разделяет слова, относящиеся к одному сказуемому?'
        self.probe = Probe(question, tuple(self.options), text)


def _compatible(left, right):
    from .adjuncts import QUESTIONS
    from .clause_series import ordinal_abbreviation
    from .modal_regions import adverbial_modifiers
    from .predication import IMPERSONAL_INFINITIVES, _copula_agrees
    from .speech_particles import DOUBT, JUSSIVE
    from .spatial_prefix import deictic_role, relative_role
    from .unlisted_attributes import predicted_attributes

    def nominal(surface):
        return tuple(tag for _, tag in known_forms(surface) if tag.POS in {'NOUN', 'NPRO'})
    def adjective(surface):
        known = known_forms(surface)
        return tuple(tag for _, tag in known or predicted_attributes(surface) if tag.POS in {'ADJF', 'PRTF'})
    if (left.casefold(), right.casefold()) in DOUBT or left.casefold() in JUSSIVE and nominal(right):
        return True
    left_forms = known_forms(left)
    right_forms = known_forms(right)
    _, postpositive = adverbial_modifiers()
    if (right.casefold() in postpositive and any(tag.POS == 'ADJF' for _, tag in left_forms)
            or left.casefold() in postpositive and nominal(right)):
        return True
    if left.casefold() == 'не' and right.casefold() in FORMS:
        return True
    if any(any(lemma in IMPERSONAL_INFINITIVES or 'Impe' in tag or tag.POS == 'PRED'
               for lemma, tag in governor) and any(tag.POS == 'INFN' for _, tag in complement)
           for governor, complement in ((left_forms, right_forms), (right_forms, left_forms))):
        return True
    if left.casefold() in QUESTIONS and right.casefold() == 'ни':
        return True
    if any(tag.POS == 'NUMR' for _, tag in left_forms) and any(tag.case == 'gent' for tag in nominal(right)):
        return True
    if (any(tag.POS == 'NOUN' and tag.number == 'plur' and tag.case == 'gent' for _, tag in left_forms)
            and any(tag.POS == 'VERB' and tag.number == 'plur' for _, tag in right_forms)):
        return True
    spatial = relative_role(left) or deictic_role(left)
    if (spatial or any(tag.POS == 'PRCL' for _, tag in left_forms)) and any(
            tag.POS in {'VERB', 'ADJS', 'PRED'} for _, tag in right_forms):
        return True
    if deictic_role(right) and any(tag.POS in {'VERB', 'ADJS', 'PRED'} for _, tag in left_forms):
        return True
    if spatial and any(tag.POS == 'PRCL' for _, tag in right_forms):
        return True
    if nominal(left) and (any(tag.case in ('gent', 'gen2') for tag in nominal(right))
                          or any(genitive_ordinals((right,), 0))):
        return True
    if (any(tag.case == 'ablt' for tag in nominal(left))
            and any(tag.case == 'nomn' for tag in nominal(right))):
        return True
    if ordinal_abbreviation(left, right) or left.isdecimal() and nominal(right):
        return True
    if left.casefold() in FORMS and (nominal(right) or adjective(right)):
        return True
    for subject, verb in ((left, right), (right, left)):
        if any(part.POS == 'PRTF' and part.case == 'nomn' and v.POS == 'VERB' and _copula_agrees(v, part)
               for _, part in known_forms(subject) for _, v in known_forms(verb)):
            return True
        if (any(lemma == 'кто' and tag.case == 'nomn' for lemma, tag in known_forms(subject))
                and any(tag.POS in ('VERB', 'ADJS', 'PRTS') for _, tag in known_forms(verb))):
            return True
        if any(a.role == 'subject' and v.role == 'predicate' and subject_agrees(a, v)
               for a in readings(subject) for v in readings(verb)):
            return True
    return any(_agree(adj, noun) for a, n in ((left, right), (right, left))
               for adj in adjective(a) for noun in nominal(n))


def _predicative_neighbors(left, right, tree):
    from .short_participles import _predicative_instrumentals

    return (left.case == 'ablt' and left.rule in {'V.XCOMP', 'V.GOV'} and right.role == 'subject'
            and right.head is not None and left.head == right.head
            and tree[left.head].lemma in _predicative_instrumentals())


def _government(left, right):
    from .case_arguments import _lexicon

    forms = (known_forms(left), known_forms(right))
    government = _lexicon()[0]
    return {(i, lemma, tag.case) for i in (0, 1)
            for lemma, verb in forms[i] if verb.POS in ('VERB', 'INFN', 'PRTS')
            for _, tag in forms[1 - i] if tag.POS in ('NOUN', 'NPRO') or 'Subx' in tag
            if tag.case in government.get(lemma, ())
            or (tag.case == 'accs' and verb.transitivity == 'tran')}


def _governed_dependency(tree, left, candidates):
    from .morphology import ROLE_CASE

    for offset, lemma, case in candidates:
        governor = left + offset
        nominal = tree[left + 1 - offset]
        actual_case = nominal.case or ROLE_CASE.get(nominal.role) or getattr(nominal.morphology, 'case', None)
        if nominal.head == governor and tree[governor].lemma == lemma and actual_case == case:
            return True
    return False


def coordinate_genitive(tokens, tree, i):
    if not (0 < i < len(tree) - 1 and tree[i].rule == 'P.COORD'):
        return False
    right = tree[i + 1]
    return (right.role == 'nominal_conjunct' and right.head == i - 1
            and any(tag.POS == 'NOUN' and tag.case in ('gent', 'gen2')
                    for _, tag in known_forms(tokens[i + 1].surface)))


def ignored_inside_group(tree, i):
    if tree[i].rule != 'PUNCT' or i == 0 or i + 1 == len(tree):
        return False
    left, right = tree[i - 1], tree[i + 1]
    return (left.head == i + 1 and left.role in {'attribute', 'possessive', 'numeral'}
            or right.head == i - 1 and right.role in {'governed', 'possessive'})


def repairs(tokens, parse, budget, *, sites=None):
    from .parser import AnalysisBudgetExceeded, Link

    from . import collective_agreement, paired_coordination

    alternatives = {}
    count = 0
    for i in range(1, len(tokens) - 1):
        if sites is not None and i not in sites:
            continue
        if tokens[i].surface != ',':
            continue
        kept = (*range(i), *range(i + 1, len(tokens)))
        joined = tuple(tokens[j] for j in kept)
        adjacent = (tokens[i - 1].surface, tokens[i + 1].surface)
        government = None
        paired_only = False
        if not _compatible(*adjacent):
            government = _government(*adjacent)
            if not government:
                if not paired_coordination.has_opening(joined):
                    continue
                paired_only = True
        for tree in parse(joined):
            left, right = i - 1, i
            collective = collective_agreement.comma_governor(tree, left, right)
            pair = paired_coordination.comma_head(tree, left, right)
            if paired_only and pair is None:
                continue
            if government and collective is None and pair is None and not _governed_dependency(tree, left, government):
                continue
            if pair is not None:
                head = pair
            elif collective is not None:
                head = collective
            elif tree[left].head == right:
                head = right
            elif tree[right].head == left:
                head = left
            elif (tree[left].rule == 'NEG.PRON' and tree[left].head is not None and
                  tree[tree[left].head].head == right):
                head = tree[left].head
            elif (tree[left].rule == 'F.NP' and tree[left].head is not None and
                  tree[tree[left].head].role in ('attribute', 'possessive') and tree[tree[left].head].head == right):
                head = tree[left].head
            elif _predicative_neighbors(tree[left], tree[right], tree):
                head = tree[left].head
            elif (tree[left].rule == 'UTT.PARTICLE' and tree[right].role == 'subject'
                  and tree[left].head == tree[right].head):
                head = tree[left].head
            elif (tree[left].role == 'adverb' and tree[right].rule == 'PART.FOCUS'
                  and tree[left].head is not None and tree[left].head == tree[right].head):
                head = tree[left].head
            else:
                continue
            links = _restore(tree, kept, len(tokens))
            links[i] = Link('punctuation', ',', kept[head], 'PUNCT.INTRAGROUP')
            group = alternatives.setdefault(i, {})
            option = tuple(links)
            if option not in group:
                group[option] = None
                count += 1
                if count > budget:
                    raise AnalysisBudgetExceeded('COMMA_REPAIR_BUDGET')
    return alternatives
