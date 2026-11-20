from .homogeneous import _restore
from .nominal_groups import _agree
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
        self.probe = Probe(question, tuple(self.options), text)


def _compatible(left, right):
    from .clause_series import ordinal_abbreviation
    from .spatial_prefix import deictic_role, relative_role
    from .unlisted_attributes import predicted_attributes

    def nominal(surface):
        return tuple(tag for _, tag in known_forms(surface) if tag.POS in {'NOUN', 'NPRO'})
    def adjective(surface):
        known = known_forms(surface)
        return tuple(tag for _, tag in known or predicted_attributes(surface) if tag.POS in {'ADJF', 'PRTF'})
    left_forms = known_forms(left)
    right_forms = known_forms(right)
    spatial = relative_role(left) or deictic_role(left)
    if (spatial or any(tag.POS == 'PRCL' for _, tag in left_forms)) and any(
            tag.POS in {'VERB', 'ADJS', 'PRED'} for _, tag in right_forms):
        return True
    if deictic_role(right) and any(tag.POS in {'VERB', 'ADJS', 'PRED'} for _, tag in left_forms):
        return True
    if spatial and any(tag.POS == 'PRCL' for _, tag in right_forms):
        return True
    if nominal(left) and any(tag.case in ('gent', 'gen2') for tag in nominal(right)):
        return True
    if ordinal_abbreviation(left, right) or left.isdecimal() and nominal(right):
        return True
    if left.casefold() in FORMS and (nominal(right) or adjective(right)):
        return True
    for subject, verb in ((left, right), (right, left)):
        if (any(lemma == 'кто' and tag.case == 'nomn' for lemma, tag in known_forms(subject))
                and any(tag.POS in ('VERB', 'ADJS', 'PRTS') for _, tag in known_forms(verb))):
            return True
        if any(a.role == 'subject' and v.role == 'predicate' and subject_agrees(a, v)
               for a in readings(subject) for v in readings(verb)):
            return True
    return any(_agree(adj, noun) for a, n in ((left, right), (right, left))
               for adj in adjective(a) for noun in nominal(n))


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

    alternatives = {}
    count = 0
    for i in range(1, len(tokens) - 1):
        if sites is not None and i not in sites:
            continue
        if tokens[i].surface != ',':
            continue
        adjacent = (tokens[i - 1].surface, tokens[i + 1].surface)
        government = None
        if not _compatible(*adjacent):
            government = _government(*adjacent)
            if not government:
                continue
        kept = (*range(i), *range(i + 1, len(tokens)))
        joined = tuple(tokens[j] for j in kept)
        for tree in parse(joined):
            left, right = i - 1, i
            if government and not _governed_dependency(tree, left, government):
                continue
            if tree[left].head == right:
                head = right
            elif tree[right].head == left:
                head = left
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
