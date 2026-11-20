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
        self.probe = Probe(question, tuple(self.options), text)


def _compatible(left, right):
    from .clause_series import ordinal_abbreviation
    from .unlisted_attributes import predicted_attributes

    def nominal(surface):
        return tuple(tag for _, tag in known_forms(surface) if tag.POS in {'NOUN', 'NPRO'})
    def adjective(surface):
        known = known_forms(surface)
        return tuple(tag for _, tag in known or predicted_attributes(surface) if tag.POS in {'ADJF', 'PRTF'})
    if nominal(left) and any(tag.case in ('gent', 'gen2') for tag in nominal(right)):
        return True
    if ordinal_abbreviation(left, right) or left.isdecimal() and nominal(right):
        return True
    if left.casefold() in FORMS and (nominal(right) or adjective(right)):
        return True
    for subject, verb in ((left, right), (right, left)):
        if any(a.role == 'subject' and v.role == 'predicate' and subject_agrees(a, v)
               for a in readings(subject) for v in readings(verb)):
            return True
    return any(_agree(adj, noun) for a, n in ((left, right), (right, left))
               for adj in adjective(a) for noun in nominal(n))


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
        if tokens[i].surface != ',' or not _compatible(tokens[i - 1].surface, tokens[i + 1].surface):
            continue
        kept = (*range(i), *range(i + 1, len(tokens)))
        joined = tuple(tokens[j] for j in kept)
        for tree in parse(joined):
            left, right = i - 1, i
            if tree[left].head == right:
                head = right
            elif tree[right].head == left:
                head = left
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
