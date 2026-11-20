from dataclasses import replace
from functools import cache
from importlib.resources import files

from .clauses import _connectives
from .morphology import from_tag
from .prepositions import DASHES
from .rules import known_forms


_QUOTES = {'«': '»', '“': '”', '„': '“', '"': '"'}
_REFS = ('head', 'antecedent', 'controller', 'coord_head', 'shared_agent', 'shared_object', 'ellipsis_source')


@cache
def _quotation_governors():
    resource = files(__package__).joinpath("lexicon", "quotation_governors.txt")
    return frozenset(resource.read_text(encoding="utf-8").splitlines())


def _root(tree):
    return next(i for i, link in enumerate(tree) if link.head is None)


def _map(tree, positions):
    return {i: replace(link, **{key: positions[target] for key in _REFS
                                if (target := getattr(link, key)) is not None})
            for i, link in zip(positions, tree)}


def _linked(left, right, li, ri, role, rule, scope):
    links = _map(left, li)
    links.update(_map(right, ri))
    host, child = li[_root(left)], ri[_root(right)]
    links[child] = replace(links[child], role=role, rule=rule, head=host, scope=scope or links[child].scope)
    return links, host, child


def _insertions(part, parse):
    from .parser import Link

    for i, word in enumerate(part):
        before = i > 0 and part[i - 1].surface == ','
        after = i + 1 < len(part) and part[i + 1].surface == ','
        detached = (i == 0 or before) and (i == len(part) - 1 or after)
        forms = known_forms(word.surface)
        options = {(lemma, 'parenthetical') for lemma, tag in forms if 'Prnt' in tag}
        options.update((lemma, 'vocative') for lemma, tag in forms if tag.POS == 'NOUN' and
                       tag.case in ('nomn', 'voct') and (tag.animacy == 'anim' or tag.case == 'voct'))
        if not options or len(part) == 1:
            continue
        indices = tuple(j for j in range(len(part)) if j < i - before or j > i + after)
        if not indices:
            continue
        if not detached and not any(tag.mood == 'impr' or tag.person == '2per' for j in indices
                                    for _, tag in known_forms(part[j].surface)) and not any('Prnt' in t for _, t in forms):
            continue
        for tree in parse(tuple(part[j] for j in indices)):
            host = indices[_root(tree)]
            if not detached and any(link.role.startswith('clause_') for link in tree):
                continue
            for lemma, role in options:
                if role == 'vocative':
                    form = tree[_root(tree)].morphology
                    if form is None or (form.mood != 'impr' and form.person != '2per'):
                        continue
                    if not detached and any(tag.tense == 'past' for _, tag in known_forms(part[host].surface)):
                        continue
                links = _map(tree, indices)
                prefix, _, ordinal = lemma.partition('-')
                ordering = role == 'parenthetical' and prefix in ('в', 'во') and any(
                    'Anum' in tag and tag.case == 'loct' and tag.number == 'plur' for _, tag in known_forms(ordinal))
                links[i] = Link(role, lemma, host, 'UTT.PARENT' if role == 'parenthetical' else 'UTT.VOC',
                                scope='ordering' if ordering else None)
                if before:
                    links[i - 1] = Link('punctuation', ',', i, 'UTT.PUNCT')
                if after:
                    links[i + 1] = Link('punctuation', ',', i, 'UTT.PUNCT')
                yield tuple(links[j] for j in range(len(part)))
                if i == 0 and role == 'parenthetical' and 'conj' in _connectives()[0].get((lemma,), {}):
                    links[i] = Link('coordinator', lemma, host, 'UTT.COORD')
                    yield tuple(links[j] for j in range(len(part)))


def _detached_pronominal_group(part, parse):
    from .nominal_groups import _prepositions
    from .parser import Link
    from .prepositions import GOVERNMENT
    from .morphology import _common

    for noun, prep in _prepositions(part, 0):
        comma = noun + 1
        if comma + 1 >= len(part) or part[comma].surface != ',':
            continue
        readings = {}
        for lemma, tag in known_forms(part[noun].surface):
            if 'Anph' in tag and 'Subx' in tag and tag.case in GOVERNMENT.get(prep, ()):
                readings.setdefault((lemma, tag.case), []).append(from_tag(tag))
        for (lemma, case), forms in readings.items():
            positions = range(comma + 1, len(part))
            for tree in parse(part[comma + 1:]):
                host = positions[_root(tree)]
                links = _map(tree, positions)
                links[0] = Link('preposition', prep, host, 'P2')
                for j in range(1, noun):
                    links[j] = Link('prep_part', part[j].surface.casefold(), 0, 'P1')
                links[noun] = Link('governed', lemma, 0, 'P1', case, morphology=_common(forms))
                links[comma] = Link('punctuation', ',', noun, 'UTT.PUNCT')
                yield tuple(links[j] for j in range(len(part)))


def _quotations(part, parse):
    from .parser import Link

    layouts = []
    for i in range(2, len(part) - 2):
        if part[i - 1].surface == ':' and _QUOTES.get(part[i].surface) == part[-1].surface:
            layouts.append((range(i - 1), i, len(part) - 1))
    if part[0].surface in _QUOTES:
        for i in range(2, len(part) - 2):
            if part[i].surface != _QUOTES[part[0].surface]:
                continue
            dash = i + 1 + (part[i + 1].surface == ',')
            if dash + 1 < len(part) and part[dash].surface in DASHES:
                layouts.append((range(dash + 1, len(part)), 0, i))
    for matrix, opening, closing in layouts:
        mark = part[closing - 1].surface
        content = range(opening + 1, closing - (mark in ('?', '!', '.')))
        for left in parse(tuple(part[i] for i in matrix)):
            if left[_root(left)].lemma not in _quotation_governors():
                continue
            for right in parse(tuple(part[i] for i in content)):
                scope = 'quoted_question' if mark == '?' else 'quoted'
                if right[_root(right)].scope:
                    scope += '_' + right[_root(right)].scope
                links, _, child = _linked(left, right, matrix, content, 'clause_complement', 'UTT.QUOTE', scope)
                for j in range(len(part)):
                    if j not in links:
                        rule = 'UTT.QUOTE.BOUND' if j in (opening, closing) else 'UTT.QUOTE.MARK'
                        links[j] = Link('punctuation', part[j].surface, child, rule)
                yield tuple(links[j] for j in range(len(part)))


def _purposes(part, parse):
    from .parser import Link

    if part[0].surface.casefold() in ('чтобы', 'чтоб'):
        for split in range(2, len(part) - 1):
            if part[split].surface != ',':
                continue
            order = (*range(split + 1, len(part)), split, *range(split))
            if part[order[0]].surface.casefold() in ('чтобы', 'чтоб'):
                continue
            for tree in _purposes(tuple(part[j] for j in order), parse):
                mapped = _map(tree, order)
                yield tuple(mapped[j] for j in range(len(part)))
        return
    for i, token in enumerate(part):
        if token.surface.casefold() not in ('чтобы', 'чтоб') or i == 0 or i + 1 >= len(part):
            continue
        split = i - int(part[i - 1].surface == ',')
        for left in parse(part[:split]):
            host = _root(left)
            actors = [j for j, link in enumerate(left) if link.head == host and link.role == 'subject']
            if not actors and not left[host].implicit_subject:
                continue
            for k in range(i + 1, len(part)):
                for lemma, tag in known_forms(part[k].surface):
                    if tag.POS != 'INFN':
                        continue
                    dummy = tuple(replace(token, surface=w) for w in ('я', 'могу'))
                    for right in parse(dummy + part[i + 1:]):
                        pivot = k - i + 1
                        if right[pivot].role != 'infinitive' or right[pivot].head != 1 or right[pivot].lemma != lemma:
                            continue
                        if any(link.head in (0, 1) for j, link in enumerate(right) if j >= 2 and j != pivot):
                            continue
                        refs = (actors[0] if actors else host, host, *range(i + 1, len(part)))
                        links = dict(enumerate(left))
                        links.update({j: link for j, link in _map(right, refs).items() if j > i})
                        negative = (right[pivot].scope or '').endswith('_negated')
                        scope = 'purpose_negated' if negative else 'purpose'
                        links[k] = replace(links[k], role='clause_adverbial', rule='UTT.PURPOSE', head=host,
                                           controller=actors[0] if actors else None, scope=scope, morphology=from_tag(tag))
                        links[i] = Link('clause_marker', token.surface.casefold(), k, 'UTT.PURPOSE.MARK', scope='purpose')
                        if split < i:
                            links[split] = Link('punctuation', ',', k, 'UTT.PUNCT')
                        yield tuple(links[j] for j in range(len(part)))


def _parataxis(part, parse):
    from .parser import Link

    from . import explanations

    finite = [i for i, token in enumerate(part) if any(tag.POS == 'VERB' for _, tag in known_forms(token.surface))]
    if len(finite) >= 2:
        governors = explanations.content_governors()
        for start in range(finite[0] + 1, finite[-1] + 1):
            previous = part[start - 1].surface
            if not (explanations.anchor_forms(previous) or any(
                    lemma in governors and tag.POS == 'VERB' for lemma, tag in known_forms(previous))):
                continue
            initial = part[start].surface
            if not initial.isalpha() or any(tag.POS in {'CONJ', 'PRCL'} or 'Ques' in tag
                    or lemma in {'кто', 'что', 'который'} for lemma, tag in known_forms(initial)):
                continue
            for left in parse(part[:start]):
                host = _root(left)
                if left[host].lemma not in governors or (host != start - 1 and left[-1].role != 'object'):
                    continue
                for right in parse(part[start:]):
                    child = _root(right)
                    if not any(tag.POS == 'VERB' and tag.mood == 'indc' and lemma == right[child].lemma
                               for lemma, tag in known_forms(part[start + child].surface)):
                        continue
                    yield from explanations.attachments(part, left, right, start, start)
    for i in range(1, len(part) - 1):
        sign = part[i].surface
        if sign not in (':', ';', ',', '—') or not finite or not finite[0] < i < finite[-1]:
            continue
        if part[i + 1].surface in _QUOTES or any(tag.POS == 'CONJ' for _, tag in known_forms(part[i + 1].surface)):
            continue
        forms, width = _connectives()
        if any(tuple(token.surface.casefold() for token in part[i + 1:i + 1 + size]) in forms
               for size in range(2, min(width, len(part) - i - 1) + 1)):
            continue
        if sign == ',' and any(tag.POS == 'CONJ' or 'Ques' in tag or lemma in ('кто', 'что', 'который')
                               for token in (part[0], part[i + 1]) for lemma, tag in known_forms(token.surface)):
            continue
        for left in parse(part[:i]):
            for right in parse(part[i + 1:]):
                if sign in (':', '—', ',') and left[_root(left)].lemma in explanations.content_governors():
                    yield from explanations.attachments(part, left, right, i, i + 1)
                    continue
                links, host, child = _linked(left, right, range(i), range(i + 1, len(part)),
                                              'clause_conjunct', 'UTT.PARATAXIS', None)
                links[i] = Link('punctuation', sign, child, 'UTT.SEP')
                yield tuple(links[j] for j in range(len(part)))


def trees(tokens, base, *, budget):
    from .parser import AnalysisBudgetExceeded

    from . import paired_coordination, parentheses, speech_particles
    from .quote_titles import spans

    if any(_QUOTES.get(tokens[start].surface) != tokens[end].surface for start, end in spans(tokens)):
        return

    visited = 0

    @cache
    def parse(part):
        nonlocal visited
        visited += 1
        if visited > budget:
            raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
        built = {}
        if any(token.surface in ('(', ')') for token in part):
            for tree in parentheses.trees(part, parse, budget):
                built.setdefault(tree, None)
                if len(built) > budget:
                    raise AnalysisBudgetExceeded('PARENTHETICAL_BUDGET')
        elif part:
            for tree in speech_particles.trees(part, parse):
                built.setdefault(tree, None)
                if len(built) > budget:
                    raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
            if built:
                return tuple(built)
            for rule in (base, _insertions, _detached_pronominal_group, _quotations, _purposes, _parataxis):
                for tree in (rule(part) if rule is base else rule(part, parse)):
                    built.setdefault(tree, None)
                    if len(built) > budget:
                        raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
            for tree in paired_coordination.trees(part, parse, budget):
                built.setdefault(tree, None)
                if len(built) > budget:
                    raise AnalysisBudgetExceeded('COORDINATION_BUDGET')
            for tree in parentheses.nominal_modifiers(part, parse, budget):
                built.setdefault(tree, None)
                if len(built) > budget:
                    raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
        return tuple(built)

    yield from parse(tokens)


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    from . import explanations

    yield from explanations.partitions(trees, tokens, text)
    from . import speech_particles

    yield from speech_particles.partitions(trees, tokens, text)
    markers = [tree[0] for tree in trees]
    if {link.role for link in markers} == {'coordinator', 'parenthetical'}:
        label = _span_label(tokens, 0)
        other = 'оговорка рассказчика'
        question = f'Как употреблено «{label}»? Если слово связывает сообщение с предыдущим, выберите «{label}».'
        yield Probe(question, (label, other), text), [label if link.role == 'coordinator' else other for link in markers]
