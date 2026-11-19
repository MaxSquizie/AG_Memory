from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import combinations, product

from .nominal_groups import POSSESSIVES
from .prepositions import FORMS, GOVERNMENT, PREFIXES
from .rules import dictionary, known_forms, readings


@dataclass(frozen=True)
class CaseRecovery:
    lemma: str
    preposition: str
    original: str
    corrected: str
    case: str


@lru_cache(maxsize=2048)
def _inflections(surface, preposition):
    cases = GOVERNMENT.get(preposition)
    if not cases:
        return ()
    compatible = {(r.lemma, r.number) for r in readings(surface, preposition) if r.role == 'governed'}
    variants = {}
    for parse in dictionary().parse(surface):
        if not parse.is_known or parse.tag.POS != 'NOUN' or not parse.tag.number or 'Abbr' in parse.tag:
            continue
        if (parse.normal_form, parse.tag.number) in compatible:
            continue
        for case in sorted(cases):
            form = parse.inflect({case, parse.tag.number})
            if form is None or form.tag.case != case or form.word.casefold() == surface.casefold():
                continue
            word = form.word
            if surface.isupper():
                word = word.upper()
            elif surface.istitle():
                word = word.capitalize()
            correction = CaseRecovery(parse.normal_form, preposition, surface, word, case)
            variants[correction] = None
    return tuple(variants)


def _sites(tokens):
    options = {}
    for start in range(len(tokens)):
        phrase = ''
        for end in range(start, len(tokens) - 1):
            phrase = (phrase + ' ' + tokens[end].surface.lower()).lstrip()
            preposition = FORMS.get(phrase)
            if preposition and GOVERNMENT.get(preposition):
                for index in range(end + 1, len(tokens)):
                    surface = tokens[index].surface
                    for repair in _inflections(surface, preposition):
                        options.setdefault(index, {})[start, repair] = None
                    agrees = any(r.role == 'group_attribute' for r in readings(surface, preposition))
                    possessive = any(tag.POS == 'ADJF' and lemma in POSSESSIVES for lemma, tag in known_forms(surface))
                    if not agrees and not possessive:
                        break
            if phrase not in PREFIXES:
                break
    return options


def trees(tokens, exact, *, budget=256):
    from .parser import AnalysisBudgetExceeded

    options = _sites(tokens)
    attempts = 0
    for cost in range(1, len(options) + 1):
        found = False
        for indices in combinations(options, cost):
            for choices in product(*(options[index] for index in indices)):
                attempts += 1
                if attempts > budget:
                    raise AnalysisBudgetExceeded('RECOVERY_BUDGET')
                normalized = list(tokens)
                for index, (_, recovery) in zip(indices, choices):
                    normalized[index] = replace(tokens[index], surface=recovery.corrected)
                for tree in exact(tuple(normalized)):
                    resolved = list(tree)
                    for index, (start, recovery) in zip(indices, choices):
                        link = tree[index]
                        if (link.role != 'governed' or link.head != start or link.lemma != recovery.lemma
                                or link.case != recovery.case or tree[start].lemma != recovery.preposition):
                            break
                        resolved[index] = replace(link, recovery=recovery)
                    else:
                        found = True
                        yield tuple(resolved)
        if found:
            return
