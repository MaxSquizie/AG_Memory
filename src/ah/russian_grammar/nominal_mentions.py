from dataclasses import replace
from functools import lru_cache
from itertools import product
from math import prod

from .determiners import SCOPES
from .morphology import Morphology, from_tag
from .nominal_groups import POSSESSIVES, _agree
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .participle_connectives import relations
from .probe import Probe
from .rules import dictionary, known_forms
from .utterances import _map


@lru_cache(maxsize=2048)
def _noun_forms(surface):
    forms = tuple((lemma, tag) for lemma, tag in known_forms(surface) if tag.POS == 'NOUN')
    if not (surface.isupper() and surface.isalpha() and len(surface) > 1):
        return forms
    abbreviations = ((p.normal_form, p.tag) for p in dictionary().parse(surface)
                     if p.is_known and p.tag.POS == 'NOUN' and 'Abbr' in p.tag)
    return tuple(dict.fromkeys((*forms, *abbreviations)))


@lru_cache(maxsize=2048)
def _attributes(surface):
    forms = []
    for lemma, tag in known_forms(surface):
        if tag.POS == 'ADJF':
            forms.append((lemma, tag, from_tag(tag), SCOPES.get(lemma)))
        elif tag.POS == 'PRTF' and 'Adjx' in tag:
            for p in dictionary().parse(surface):
                if not p.is_known or p.tag != tag:
                    continue
                citation = p.inflect({'masc', 'sing', 'nomn'})
                if citation:
                    adj = Morphology(pos='ADJF', case=str(tag.case), gender=tag.gender, number=tag.number)
                    forms.append((citation.word, tag, adj, None))
    return tuple(dict.fromkeys(forms))


def _units(tokens, start, case, budget):
    modifiers = []
    for i in range(start, len(tokens)):
        for lemma, noun in _noun_forms(tokens[i].surface):
            if noun.case != case:
                continue
            alternatives = []
            for variants in modifiers:
                links = (Link('possessive' if word in POSSESSIVES else 'attribute', word, i,
                              'P.POSS' if word in POSSESSIVES else 'NP.DET' if scope else 'A1',
                              morphology=form, scope=scope)
                         for word, tag, form, scope in variants if _agree(tag, noun))
                alternatives.append(tuple(dict.fromkeys(links)))
            if prod(len(choices) for choices in alternatives) > budget:
                raise AnalysisBudgetExceeded('NOMINAL_MODIFIER_BUDGET')
            for selected in product(*alternatives):
                yield i, lemma, noun, dict(zip(range(start, i), selected))
        variants = _attributes(tokens[i].surface)
        if not variants:
            break
        modifiers.append(variants)


def _mentions(tokens, budget):
    if len(tokens) < 2 or any(not token.surface.isalpha() and '-' not in token.surface for token in tokens):
        return
    pending = []
    for i, lemma, tag, attrs in _units(tokens, 0, 'nomn', budget):
        pending.append((i + 1, (i,), {**attrs, i: Link('predicate', lemma, None, 'N.MENTION', 'nomn',
                                                       scope='nominal', morphology=from_tag(tag))}))
    examined = 0
    while pending:
        start, path, links = pending.pop()
        examined += 1
        if examined > budget:
            raise AnalysisBudgetExceeded('NOMINAL_MENTION_BUDGET')
        if start == len(tokens):
            yield tuple(links[i] for i in range(start))
            continue
        for i, lemma, tag, attrs in _units(tokens, start, 'gent', budget):
            for depth, head in enumerate(path):
                gen = Link('genitive_modifier', lemma, head, 'N.GEN', 'gent', morphology=from_tag(tag))
                pending.append((i + 1, (*path[:depth + 1], i), {**links, **attrs, i: gen}))


def _appositions(tokens, parse, budget):
    for pron, source in enumerate(tokens[:-1]):
        references = [(lemma, tag) for lemma, tag in known_forms(source.surface)
                      if tag.POS == 'NPRO' and tag.person and tag.case == 'nomn']
        if not references:
            continue
        opening = tokens[pron + 1].surface == ','
        start = pron + 1 + int(opening)
        particle = None
        if pron > 0:
            previous = tokens[pron - 1].surface
            if 'addition' in relations(previous) and any(t.POS == 'PRCL' for _, t in known_forms(previous)):
                particle = pron - 1
        examined = 0
        for lemma, tag in references:
            for app, app_lemma, noun, attrs in _units(tokens, start, tag.case, budget):
                if tag.number != noun.number or (tag.gender and noun.gender and tag.gender != noun.gender):
                    continue
                closing = app + 1 < len(tokens) and tokens[app + 1].surface == ','
                stop = app + 1 + int(closing)
                kept = tuple(k for k in range(len(tokens)) if k != particle and not pron < k < stop)
                for base in parse(tuple(tokens[k] for k in kept)):
                    examined += 1
                    if examined > budget:
                        raise AnalysisBudgetExceeded('PRONOUN_APPOSITION_BUDGET')
                    links = _map(base, kept)
                    host = links[pron]
                    if host.role != 'subject' or host.lemma != lemma:
                        continue
                    if particle is not None:
                        links[particle] = Link('particle', tokens[particle].surface.casefold(), pron,
                                               'PART.FOCUS', scope='focus')
                    if opening:
                        links[pron + 1] = Link('punctuation', ',', pron, 'APP.BOUND')
                    if closing:
                        links[app + 1] = Link('punctuation', ',', pron, 'APP.BOUND')
                    links.update(attrs)
                    links[app] = Link('apposition', app_lemma, pron, 'APP.PRON', str(noun.case),
                                      morphology=from_tag(noun))
                    yield tuple(links[i] for i in range(len(tokens)))


def _fragment_modifiers(tokens, index, budget):
    from .nominal_entries import Unit, _modifiers

    yield from _modifiers(tokens, index, budget)
    if index == len(tokens):
        return
    lemmas = {lemma for lemma, tag in known_forms(tokens[index].surface)
              if tag.POS == 'ADJF' and 'Subx' in tag and tag.case == 'gent'}
    for lemma in sorted(lemmas):
        yield Unit(index, index + 1, index, Link('genitive_modifier', lemma, None, 'N.GEN.SUBSTANTIVE', 'gent'), ())


def name_fragments(tokens, budget):
    from .nominal_entries import Unit, _attach, _layouts

    if len(tokens) < 2 or not tokens[0].surface.istitle():
        return
    surface = tokens[0].surface
    forms = known_forms(surface)
    proper = [lemma for lemma, tag in forms if tag.POS == 'NOUN' and tag.case == 'nomn'
              and {'Geox', 'Name', 'Surn', 'Orgn', 'Trad'} & tag.grammemes]
    convertible = any(tag.POS == 'ADJF' and tag.case == 'nomn' for _, tag in forms)
    if not proper and not convertible:
        return
    for lemma in dict.fromkeys(proper or (surface,)):
        root = Link('nominal_head', lemma, None, 'N.FRAGMENT.NAME', scope='proper_name')
        seed = Unit(0, 1, 0, root, ())
        generated = 0
        for layout in _layouts(tokens, seed, {}, budget, modifiers=_fragment_modifiers):
            if not layout or layout[0].link.role != 'genitive_modifier':
                continue
            for tree in _attach(layout, (0,), {0: root}):
                generated += 1
                if generated > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_FRAGMENT_BUDGET')
                yield tree
                for j, link in enumerate(tree):
                    if (link.role == 'preposition' and link.head == 0
                            and all(next_link.head >= j for next_link in tree[j + 1:])):
                        yield (*tree[:j], replace(link, scope='orphan'), *tree[j + 1:])


def trees(tokens, parse, budget):
    yield from _mentions(tokens, budget)
    yield from _appositions(tokens, parse, budget)


def confirmation(tokens, tree, i, text):
    if tree[i].rule == 'N.FRAGMENT.NAME':
        return Probe('Какое слово служит собственным именем в этом именном фрагменте?', (_span_label(tokens, i),), text)
    if tree[i].rule != 'APP.PRON':
        return None
    answer = _span_label(tokens, i)
    host = _span_label(tokens, tree[i].head)
    return Probe(f'Какое существительное здесь поясняет, кого или что обозначает «{host}»?',
                 (answer,), text)


def partitions(trees, tokens, text):
    if all(tree[0].rule == 'N.FRAGMENT.NAME' for tree in trees):
        for i in range(len(tokens)):
            if not all(tree[i].role == 'preposition' for tree in trees) or not any(tree[i].scope == 'orphan' for tree in trees):
                continue
            missing = 'связь с пропущенной частью'
            keys = [missing if tree[i].scope == 'orphan' else _span_label(tokens, tree[i].head) for tree in trees]
            options = tuple(dict.fromkeys(keys))
            if len(options) < 2:
                continue
            options = tuple(k for k in options if k != missing) + (missing,)
            target = next(j for j, l in enumerate(trees[0]) if l.role == 'governed' and l.head == i)
            group = _span_label(tokens, i, target + 1)
            yield Probe(f'Какое слово в этом фрагменте поясняет сочетание «{group}»? '
                        'Если то, к чему оно относится, пропущено, выберите «связь с пропущенной частью».',
                        options, text), keys
    if not all(any(link.rule in ('N.MENTION', 'N.FRAGMENT.NAME') for link in tree) for tree in trees):
        return
    for i in range(len(tokens)):
        if not all(tree[i].role == 'genitive_modifier' for tree in trees):
            continue
        heads = [tree[i].head for tree in trees]
        if len(set(heads)) < 2:
            continue
        start = i
        while start > 0 and all(tree[start - 1].head == i and tree[start - 1].role in ('attribute', 'possessive')
                                for tree in trees):
            start -= 1
        phrase = _span_label(tokens, start, i + 1)
        labels = {index: _span_label(tokens, index) for index in sorted(set(heads))}
        yield Probe(f'Какое слово уточняет группа «{phrase}» в родительном падеже?', tuple(labels.values()), text), [
            labels[head] for head in heads]
