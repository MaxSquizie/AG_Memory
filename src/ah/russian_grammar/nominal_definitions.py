from functools import lru_cache

from .morphology import from_tag
from .nominal_groups import _agree
from .numerals import expressions
from .parser import AnalysisBudgetExceeded, Link
from .participle_forms import matching
from .predication import _bare_trees
from .rules import dictionary, known_forms, unaccented
from .short_participles import _predicative_instrumentals


@lru_cache(maxsize=2048)
def comparative_forms(surface):
    word = unaccented(surface).casefold()
    results = set()
    for parse in dictionary().parse(word):
        if not parse.is_known or parse.tag.POS != 'ADJF':
            continue
        for form in parse.lexeme:
            if (form.tag.POS != 'ADJF' or form.tag.gender != 'masc' or form.tag.case != 'nomn'
                    or not form.word.endswith('ший')):
                continue
            stem = form.word[:-2]
            if word.startswith(stem) and any(tag.POS == 'COMP' for _, tag in known_forms(stem + 'е')):
                results.add((parse.normal_form, parse.tag))
                break
    return tuple(sorted(results, key=lambda item: (item[0], str(item[1]))))


def _attributes(tokens, i, noun, host):
    negated = tokens[i].surface.casefold() == 'не'
    anchor = i + int(negated)
    if anchor + 1 >= len(tokens):
        return
    prefix = (Link('particle', 'не', anchor, 'MOD.NEG'),) if negated else ()
    scope = 'negated' if negated else None
    for lemma, tag in comparative_forms(tokens[anchor].surface):
        if not _agree(tag, noun):
            continue
        adjective = Link('attribute', lemma, host, 'CMP.ATTR', tag.case, scope=scope, morphology=from_tag(tag))
        for number in expressions(tokens, anchor + 1):
            if number.kind not in ('cardinal', 'fraction'):
                continue
            parts = number.parts_for('gent')
            if not parts:
                continue
            first, form = parts[0]
            standard = Link('comparison_standard', first, anchor, 'CMP.STD', 'gent', morphology=form,
                            quantity=number.value, quantity_kind=number.kind)
            rest = tuple(Link('numeral_part', part, anchor + 1, 'NUM.PART', morphology=morph)
                         for part, morph in parts[1:])
            yield number.end, (*prefix, adjective, standard, *rest)
    for participle in matching(tokens[anchor].surface, noun):
        if (participle.lemma not in _predicative_instrumentals() or participle.morphology.voice != 'actv'
                or participle.morphology.transitivity != 'intr'):
            continue
        for lemma, tag in known_forms(tokens[anchor + 1].surface):
            if tag.POS != 'ADJF' or tag.case != 'ablt' or tag.number != noun.number:
                continue
            if noun.number == 'sing' and tag.gender != noun.gender:
                continue
            word = Link('participle', participle.lemma, host, 'PART.ATTR', noun.case, controller=host,
                        scope=scope, morphology=participle.morphology)
            complement = Link('predicative_complement', lemma, anchor, 'V.XCOMP', 'ablt', controller=host,
                              morphology=from_tag(tag))
            yield anchor + 2, (*prefix, word, complement)


def trees(tokens, parse, budget):
    if not any(comparative_forms(t.surface) or any(tag.POS == 'PRTF' and lemma in _predicative_instrumentals()
               for lemma, tag in known_forms(t.surface)) for t in tokens):
        return
    generated = 0
    for host in range(1, len(tokens) - 2):
        nouns = [(lemma, tag) for lemma, tag in known_forms(tokens[host].surface)
                 if tag.POS == 'NOUN' and tag.case == 'nomn']
        for lemma, noun in nouns:
            pending = [(host + 1, ())]
            cores = None
            while pending:
                i, attached = pending.pop()
                if i == len(tokens):
                    if cores is None:
                        cores = tuple(t for t in _bare_trees(tokens[:host + 1])
                                      if t[host].lemma == lemma and t[host].role in ('subject', 'predicate')
                                      and any(l.rule == 'V2' for l in t))
                    for core in cores:
                        generated += 1
                        if generated > budget:
                            raise AnalysisBudgetExceeded('POSTNOMINAL_BUDGET')
                        yield (*core, *attached)
                    continue
                comma = tokens[i].surface == ','
                start = i + int(comma)
                if start >= len(tokens):
                    continue
                for end, group in _attributes(tokens, start, noun, host):
                    root = start + int(group[0].role == 'particle')
                    punct = (Link('punctuation', ',', root, 'PUNCT'),) if comma else ()
                    pending.append((end, (*attached, *punct, *group)))
                if len(pending) > budget:
                    raise AnalysisBudgetExceeded('POSTNOMINAL_BUDGET')


def partitions(analyses, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    heads = [next(i for i, link in enumerate(tree) if link.head is None) for tree in analyses]
    if len(set(heads)) < 2 or any(tree[i].rule != 'V2' for tree, i in zip(analyses, heads)):
        return
    spans = {}
    for i in dict.fromkeys(heads):
        if not all(tree[i].role in ('predicate', 'subject')
                   and any(lemma == tree[i].lemma and tag.POS == 'NOUN' and tag.case == 'nomn'
                           for lemma, tag in known_forms(tokens[i].surface)) for tree in analyses):
            return
        start = i
        while start and all(tree[start - 1].head == i and (tree[start - 1].role in ('attribute', 'possessive') or tree[start - 1].rule == 'PUNCT.INTRAGROUP')
                            for tree in analyses):
            start -= 1
        spans[i] = _span_label(tokens, start, i + 1).replace(' ,', ',')
    if len(set(spans.values())) != len(spans):
        return
    options = tuple(spans[i] for i in sorted(spans))
    yield Probe('Каким словом или сочетанием характеризуют подлежащее в этом предложении?',
                options, text), [spans[head] for head in heads]
