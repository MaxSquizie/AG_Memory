from .homogeneous import _restore
from .nominal_groups import _agree
from .prepositions import FORMS
from .rules import known_forms


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
    def nominal(surface):
        return tuple(tag for _, tag in known_forms(surface) if tag.POS in {'NOUN', 'NPRO'})
    def adjective(surface):
        return tuple(tag for _, tag in known_forms(surface) if tag.POS in {'ADJF', 'PRTF'})
    if left.isdecimal() and nominal(right):
        return True
    if left.casefold() in FORMS and (nominal(right) or adjective(right)):
        return True
    return any(_agree(adj, noun) for a, n in ((left, right), (right, left))
               for adj in adjective(a) for noun in nominal(n))


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
