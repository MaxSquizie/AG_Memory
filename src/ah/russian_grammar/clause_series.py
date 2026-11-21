from dataclasses import replace
from functools import cache
from importlib.resources import files
from itertools import product

from .clauses import Boundary, _attachments, _boundaries, _key
from .morphology import NOMINAL_ROLES, from_tag
from .nominal_groups import POSSESSIVES, _markers, _prepositions
from .parser import AnalysisBudgetExceeded, Link
from .predicative_groups import _groups, _nominals
from .prepositions import GOVERNMENT
from .numerals import roman_value
from .rules import known_forms
from .short_participles import _predicative_instrumentals
from .utterances import _map, _root


@cache
def _abbreviations():
    forms = {}
    for line in files(__package__).joinpath('lexicon/ordinal-abbreviations.tsv').read_text().splitlines():
        surface, lemma, prep, case = line.split('\t')
        forms.setdefault(surface, []).append((lemma, prep, case))
    return forms


def ordinal_abbreviation(left, right):
    return roman_value(left) is not None and right.casefold().rstrip('.') in _abbreviations()


def _dated_prefix(tokens, finite):
    for i in range(finite - 2):
        for first, prep in _prepositions(tokens, i):
            noun = first + 1
            if noun >= finite or not ordinal_abbreviation(tokens[first].surface, tokens[noun].surface):
                continue
            before = []
            for index in range(i):
                adverbs = {lemma for lemma, tag in known_forms(tokens[index].surface) if tag.POS == 'ADVB'}
                if not adverbs:
                    break
                before.append(tuple((index, Link('adverb', a, noun, 'ADV.MOD')) for a in sorted(adverbs)))
            else:
                for lemma, governor, ud_case in _abbreviations()[tokens[noun].surface.rstrip('.').casefold()]:
                    case = {'Loc': 'loct', 'Acc': 'accs', 'Gen': 'gent', 'Dat': 'datv', 'Ins': 'ablt', 'Nom': 'nomn'}.get(ud_case)
                    if prep != governor or case not in GOVERNMENT.get(prep, ()):
                        continue
                    for selected in product(*before):
                        group = {**dict(selected), i: Link('preposition', prep, finite, 'P2'),
                                 first: Link('attribute', tokens[first].surface, noun, 'NUM.ROMAN',
                                             quantity_kind='ordinal', quantity=str(roman_value(tokens[first].surface))),
                                 noun: Link('governed', lemma, i, 'UNIT.ABBR', case)}
                        for j in range(i + 1, first):
                            group[j] = Link('prep_part', tokens[j].surface.casefold(), i, 'P1')
                        end = noun + 1
                        if end < finite and tokens[end].surface == '.':
                            group[end] = Link('punctuation', '.', noun, 'ABBR.PUNCT')
                            end += 1
                        yield end, group


def _expanded_pp(tokens, start):
    for end, last, group in _groups(tokens, start):
        if end == len(tokens):
            yield group
        elif group[last].role == 'genitive_modifier':
            for marker in _markers(tokens, end):
                for noun, sibling in _nominals(tokens, marker[-1] + 1, {group[last].case}, last, 'nominal_conjunct'):
                    if noun + 1 != len(tokens):
                        continue
                    marks = {k: Link('coordinator' if k == end else 'coordinator_part',
                                     tokens[k].surface.casefold(), noun if k == end else end, 'N.COORD')
                             for k in marker}
                    yield {**group, **marks, **sibling}


def _postnominal(tokens, finite, parse):
    prefixes = [(0, {}), *_dated_prefix(tokens, finite)]
    for cut in range(finite + 1, len(tokens)):
        if not any(_prepositions(tokens, cut)):
            continue
        groups = tuple(_expanded_pp(tokens, cut))
        if not groups:
            continue
        for begin, prefix in prefixes:
            for tree in parse(tokens[begin:cut]):
                root = _root(tree) + begin
                if root != finite:
                    continue
                links = {**prefix, **_map(tree, range(begin, cut))}
                tails = [(root, links)]
                edge = cut - 1
                visited = {root}
                while edge in links and edge not in visited:
                    visited.add(edge)
                    link = links[edge]
                    if link.role in NOMINAL_ROLES or link.role in ('infinitive', 'genitive_modifier'):
                        tails.append((edge, links))
                    edge = link.head
                for j, role in enumerate(tree):
                    absolute = j + begin
                    if absolute > finite and role.case == 'ablt' and role.head == root - begin:
                        tails.append((absolute, links))
                        subjects = [h + begin for h, v in enumerate(tree) if v.head == root - begin and v.role == 'subject']
                        if tree[root - begin].lemma in _predicative_instrumentals() and len(subjects) == 1:
                            tails.append((absolute, {**links, absolute: replace(links[absolute],
                                role='predicative_complement', rule='V.XCOMP', controller=subjects[0])}))
                for host, stem in tails:
                    for group in groups:
                        merged = {**stem, **group, cut: replace(group[cut], head=host)}
                        yield tuple(merged[k] for k in range(len(tokens)))


def _omittable(tokens, root):
    for i in range(root - 1):
        a, b = tokens[i:i + 2]
        if (a.surface.istitle() and b.surface.istitle()
                and any('Name' in tag for _, tag in known_forms(a.surface))):
            yield (i + 1,), {i + 1: Link('name_part', b.surface.casefold(), i, 'OPAQUE.NAME.CONTINUATION')}
    i = root
    while i > 0 and any(tag.POS in {'ADVB', 'PRCL'} for _, tag in known_forms(tokens[i - 1].surface)):
        i -= 1
    if i < root:
        variants = []
        for j in range(i, root):
            word = tokens[j].surface
            options = {Link('adverb', lemma, root, 'B1') for lemma, tag in known_forms(word) if tag.POS == 'ADVB'}
            if any(marker == (j,) for marker in _markers(tokens, j)):
                if j > 0 and all(tag.POS == 'PRCL' for _, tag in known_forms(word)):
                    options.add(Link('particle', word.casefold(), root, 'PART.FOCUS'))
                else:
                    options.add(Link('coordinator', word.casefold(), root, 'N.COORD'))
            if not options:
                break
            variants.append(sorted(options, key=lambda link: (link.role, link.lemma)))
        else:
            for selected in product(*variants):
                yield tuple(range(i, root)), dict(zip(range(i, root), selected))


def _local(tokens, root, parse):
    seen = set()
    def add(trees):
        for tree in trees:
            if any(l.role == 'attribute' and l.lemma in POSSESSIVES for l in tree):
                continue
            if tree in seen or (tree[root].head is not None and tree[root].role != 'copula'):
                continue
            seen.add(tree)
            yield tree
    if not any(t.surface in {',', ';'} for t in tokens):
        yield from add(_postnominal(tokens, root, parse))
        if not seen:
            for begin, prefix in _dated_prefix(tokens, root):
                for tree in parse(tokens[begin:]):
                    if _root(tree) + begin == root:
                        merged = {**prefix, **_map(tree, range(begin, len(tokens)))}
                        yield from add([tuple(merged[i] for i in range(len(tokens)))])
        for removed, inserts in _omittable(tokens, root):
            kept = [j for j in range(len(tokens)) if j not in removed]
            for tree in parse(tuple(tokens[i] for i in kept)):
                links = {**_map(tree, kept), **inserts}
                if any(link.role == 'name_part' and links[link.head].role != 'subject' for link in inserts.values()):
                    continue
                yield from add([tuple(links[i] for i in range(len(tokens)))])
        if not seen:
            yield from add(parse(tokens))


def _seams(tokens, left, right, boundaries):
    marks = [b for b in boundaries if left < b.start and b.stop <= right]
    commas = [i for i in range(left + 1, right) if tokens[i].surface in {',', ';'}]
    yield from marks
    for i in commas:
        if not any(b.start == i for b in marks):
            yield Boundary(i, i + 1, i + 1, '', 'asyndetic', frozenset())
    if commas:
        return
    for i in range(left + 1, right):
        if any(tag.POS in {'NOUN', 'NPRO', 'ADJF', 'NUMR'} and tag.case == 'nomn'
               for _, tag in known_forms(tokens[i].surface)):
            yield Boundary(i, i, i, '', 'asyndetic', frozenset())


def trees(tokens, parse, budget):
    finite = [i for i, token in enumerate(tokens) if any(tag.POS == 'VERB' and tag.mood == 'indc'
                                                        for _, tag in known_forms(token.surface))]
    if len(finite) < 2:
        return
    words = tuple(_key(t.surface) for t in tokens)
    boundaries = [b for b in _boundaries(words) if b.relation in {'conj', 'advcl'}]
    seams = [tuple(_seams(tokens, left, right, boundaries)) for left, right in zip(finite, finite[1:])]
    if not all(seams):
        return
    @cache
    def leaf(start, stop, verb):
        result = []
        for tree in _local(tokens[start:stop], verb - start, parse):
            if len(result) >= budget:
                raise AnalysisBudgetExceeded('COMPOUND_CLAUSE_BUDGET')
            links = _map(tree, range(start, stop))
            result.append((tuple(links.values()), _root(tree) + start))
        return tuple(result)

    pending = [(0, 0, (), (), None)]
    explored = 0
    while pending:
        index, start, prefix, levels, before = pending.pop()
        stops = seams[index] if index < len(seams) else (None,)
        for after in stops:
            stop = after.start if after else len(tokens)
            for tree, root in leaf(start, stop, finite[index]):
                if before is None:
                    joined = ((tree, ((root, root),)),)
                else:
                    marker = before
                    if marker.relation == 'asyndetic':
                        if not any(link.role == 'subject' and link.head == root for link in tree):
                            continue
                        marker = replace(marker, relation='conj')
                    joined = _attachments(prefix, levels, marker, tree, root, words)
                for structure, domains in joined:
                    if before and before.stop - before.marker > 1:
                        links = list(structure)
                        for k in range(before.marker + 1, before.stop):
                            links[k] = Link('fixed', words[k], before.marker, 'CL.FIXED')
                        structure = tuple(links)
                    explored += 1
                    if explored > budget:
                        raise AnalysisBudgetExceeded('COMPOUND_CLAUSE_BUDGET')
                    if after is None:
                        yield structure
                    else:
                        pending.append((index + 1, after.stop, structure, domains, after))


def confirmation(tokens, tree, i, text):
    from .parser import _span_label
    from .probe import Probe

    link = tree[i]
    if link.rule == 'UNIT.ABBR':
        ordinal = next(j for j, part in enumerate(tree) if part.head == i and part.rule == 'NUM.ROMAN')
        label = _span_label(tokens, ordinal, i + 1).replace(' ,', ',')
        return Probe(f'Какое сочетание содержит сокращение слова «{link.lemma}»?', (label,), text)
    if link.rule == 'OPAQUE.NAME.CONTINUATION':
        return Probe(f'Какое слово продолжает личное имя «{_span_label(tokens, link.head)}»?',
                     (_span_label(tokens, i),), text)


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        if all(link.rule == 'ELL.COORD' for link in links) and len({l.head for l in links}) > 1:
            labels = {l.head: _span_label(tokens, l.head) for l in links}
            focus = _span_label(tokens, i)
            question = f'С каким словом из первой части сопоставлено «{focus}» в продолжении перечисления?'
            yield Probe(question, tuple(dict.fromkeys(labels.values())), text), [labels[l.head] for l in links]
        if all(l.role == 'adverb' for l in links) and {l.rule == 'CL.SHARED.ADV' for l in links} == {True, False}:
            answers = []
            for tree, link in zip(trees, links):
                if link.rule == 'CL.SHARED.ADV':
                    last = max(j for j, part in enumerate(tree[:i]) if part.role == 'clause_conjunct'
                               and part.head == link.head)
                    answers.append(_span_label(tokens, link.head, last + 1))
                else:
                    answers.append(_span_label(tokens, link.head))
            focus = _span_label(tokens, i)
            question = f'Какое действие или сочетание действий уточняет слово «{focus}»?'
            yield Probe(question, tuple(dict.fromkeys(answers)), text), answers

    fixed = {(link.head, i) for tree in trees for i, link in enumerate(tree) if link.rule == 'CL.FIXED'}
    for start in sorted({host for host, _ in fixed}):
        stop = max(i for host, i in fixed if host == start) + 1
        question = 'Какие слова в этом фрагменте вместе вводят следующую часть предложения?'
        answers = []
        for tree in trees:
            indices = [i for i in range(start, stop) if tree[i].role == 'clause_marker' or
                       tree[i].rule == 'CL.FIXED' and tree[i].head == start]
            if indices and indices != list(range(indices[0], indices[-1] + 1)):
                break
            answers.append(_span_label(tokens, indices[0], indices[-1] + 1) if indices else 'нет таких слов')
        else:
            if len(set(answers)) > 1:
                yield Probe(question, tuple(dict.fromkeys(answers)), text), answers

    for i in range(len(tokens)):
        roles = {tree[i].role for tree in trees}
        if roles == {'clause_adverbial'}:
            heads = [tree[i].head for tree in trees]
            if len(set(heads)) > 1 and all(tree[i].scope == 'cause' for tree in trees):
                options = {j: _span_label(tokens, j) for j in sorted(set(heads))}
                focus = _span_label(tokens, i)
                question = f'Какое действие объясняется причиной, названной в части со словом «{focus}»?'
                yield Probe(question, tuple(options.values()), text), [options[j] for j in heads]
        if roles == {'possessive', 'genitive_modifier'}:
            heads = [tree[i].head for tree in trees]
            if set(heads) == {i - 1, i + 1}:
                labels = {head: _span_label(tokens, min(i, head), max(i, head) + 1) for head in set(heads)}
                question = f'В какое сочетание входит слово «{_span_label(tokens, i)}»?'
                yield Probe(question, tuple(labels[h] for h in sorted(labels)), text), [labels[h] for h in heads]
        if 'copula' not in roles:
            continue
        complements = {tree[i].head for tree in trees if tree[i].role == 'copula'}
        if len(complements) != 1 or roles == {'copula'}:
            continue
        head, = complements
        if not all(tree[i].role == 'copula' or (tree[head].role == 'oblique' and tree[head].head == i)
                   for tree in trees):
            continue
        subjects = [{j for j, link in enumerate(tree) if link.role == 'subject' and
                     link.head == (head if tree[i].role == 'copula' else i)} for tree in trees]
        if len(subjects[0]) != 1 or not all(s == subjects[0] for s in subjects):
            continue
        subject, = subjects[0]
        start = head
        while start and all(tree[start - 1].role == 'attribute' and tree[start - 1].head == head for tree in trees):
            start -= 1
        phrase = _span_label(tokens, start, head + 1)
        question = f'Кем или чем здесь назван участник «{_span_label(tokens, subject)}»? Выберите сочетание из текста.'
        options = (phrase, 'нет такого сочетания')
        yield Probe(question, options, text), [options[0] if tree[i].role == 'copula' else options[1] for tree in trees]
