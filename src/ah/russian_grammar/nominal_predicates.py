from functools import cache
from importlib.resources import files
from itertools import product
from math import prod

from .case_arguments import _lexicon as government
from .morphology import from_tag
from .nominal_groups import _agree, _members, _prepositions
from .participle_connectives import markers, relations
from .parser import AnalysisBudgetExceeded, Link
from .rules import known_forms
from .short_participles import _predicative_instrumentals


@cache
def _fixed_modifiers():
    table = files(__package__).joinpath('lexicon/initial-modifiers.tsv').read_text(encoding='utf8')
    return tuple((tuple(form.split()), tuple(lemmas.split()))
                 for form, lemmas in (row.split('\t') for row in table.splitlines()))


def _prefixes(tokens, root):
    yield 0, {}
    for form, lemmas in _fixed_modifiers():
        end = len(form)
        if end >= root or tuple(t.surface.casefold() for t in tokens[:end]) != form:
            continue
        links = {0: Link('discourse_modifier', lemmas[0], root, 'F.DISCOURSE')}
        for i in range(1, end):
            links[i] = Link('fixed_part', lemmas[i], 0, 'F.DISCOURSE.PART')
        if tokens[end].surface == ',':
            links[end] = Link('punctuation', ',', 0, 'F.DISCOURSE.COMMA')
            end += 1
        yield end, links


def _additive(tokens, i):
    for marker in markers(tokens, i):
        phrase = ' '.join(tokens[j].surface for j in marker)
        meanings = relations(phrase)
        if meanings and set(meanings) <= {'addition', 'contrast'}:
            yield marker


def _series(tokens, budget):
    if len(tokens) < 3:
        return
    for subject, lemma, _, attrs in _members(tokens, 0, None, 'nomn'):
        subjects = [tag for word, tag in known_forms(tokens[subject].surface)
                    if word == lemma and tag.case == 'nomn' and tag.POS in {'NOUN', 'NPRO'}]
        for subject_tag in subjects:
            positions = []
            options = []
            separators = []
            i = subject + 1
            while i < len(tokens):
                before = i
                if positions and tokens[i].surface == ',':
                    i += 1
                marker = next(_additive(tokens, i), ()) if positions else ()
                i += len(marker)
                if i >= len(tokens):
                    break
                adjectives = [(word, tag) for word, tag in known_forms(tokens[i].surface)
                              if tag.POS in {'ADJF', 'ADJS'} and 'Apro' not in tag and tag.case in (None, 'nomn')
                              and tag.number == subject_tag.number
                              and (tag.number != 'sing' or tag.gender == subject_tag.gender)]
                if not adjectives:
                    break
                separators.append((before, i, marker))
                positions.append(i)
                options.append(adjectives)
                i += 1
            else:
                if len(positions) < 2:
                    continue
                if prod(len(choices) for choices in options) * len(positions) > budget:
                    raise AnalysisBudgetExceeded('PREDICATE_SERIES_BUDGET')
                for first, root in enumerate(positions):
                    if first and (separators[first][2] or any(t.surface == ',' for t in tokens[subject + 1:root])):
                        continue
                    for adjectives in product(*options):
                        links = {**dict(attrs), subject: Link('subject', lemma, root, 'S1', 'nomn',
                                                              morphology=from_tag(subject_tag))}
                        for j, (index, (word, tag)) in enumerate(zip(positions, adjectives)):
                            if j < first:
                                if tag.POS != 'ADJF' or not _agree(tag, subject_tag):
                                    break
                                links[index] = Link('attribute', word, subject, 'A1', 'nomn', morphology=from_tag(tag))
                            elif j == first:
                                links[index] = Link('predicate', word, None, 'V2', tag.case, morphology=from_tag(tag))
                            else:
                                links[index] = Link('clause_conjunct', word, root, 'V2.CONJ', tag.case,
                                                    controller=subject, morphology=from_tag(tag))
                            start, end, marker = separators[j]
                            for k in range(start, end):
                                role = 'clause_marker' if k in marker else 'punctuation'
                                links[k] = Link(role, tokens[k].surface.casefold(), index, 'V2.SEP')
                        else:
                            yield tuple(links[k] for k in range(len(tokens)))


def _phrases(tokens, start, stop, case, budget):
    @cache
    def members(i, prep, required):
        return tuple(_members(tokens[:stop], i, prep, required))

    pending = []
    for head, lemma, _, attrs in members(start, None, case):
        seed = Link('nominal', lemma, None, 'N.SEED', case)
        pending.append((head + 1, head, (head,), {head: seed, **dict(attrs)}))
    visited = set()
    while pending:
        i, root, path, links = pending.pop()
        key = (i, path, tuple(sorted(links.items())))
        if key in visited:
            continue
        visited.add(key)
        if len(visited) > budget:
            raise AnalysisBudgetExceeded('NOMINAL_PREDICATION_BUDGET')
        if i == stop:
            yield root, links
            continue
        comma = tokens[i].surface == ','
        j = i + int(comma)
        if j >= stop:
            continue
        markers = tuple(_additive(tokens[:stop], j))
        for depth, host in enumerate(path):
            if not comma and not markers:
                for h, lemma, c, attrs in members(i, None, 'gent'):
                    link = Link('genitive_modifier', lemma, host, 'N.GEN', c)
                    pending.append((h + 1, root, (*path[:depth + 1], h), {**links, **dict(attrs), h: link}))
                for after, prep in _prepositions(tokens[:stop], i):
                    for h, lemma, c, attrs in members(after, prep, None):
                        pp = {i: Link('preposition', prep, host, 'P2'),
                              h: Link('governed', lemma, i, 'P1', c)}
                        for k in range(i + 1, after):
                            pp[k] = Link('prep_part', tokens[k].surface.casefold(), i, 'P1')
                        pending.append((h + 1, root, (*path[:depth + 1], h), {**links, **dict(attrs), **pp}))
            for marker in markers or ((),):
                if not marker and not comma and (depth != len(path) - 1 or links[host].role != 'genitive_modifier'):
                    continue
                sibling = links[host]
                if sibling.role == 'governed':
                    continue
                anchor = sibling.head if sibling.role == 'nominal_conjunct' else host
                for h, lemma, c, attrs in members(j + len(marker), None, sibling.case):
                    group = dict(attrs)
                    if comma:
                        group[i] = Link('punctuation', ',', h, 'N.COORD')
                    for k in marker:
                        group[k] = Link('coordinator', tokens[k].surface.casefold(), h, 'N.COORD')
                    group[h] = Link('nominal_conjunct', lemma, anchor, 'N.COORD', c)
                    pending.append((h + 1, root, (*path[:depth + 1], h), {**links, **group}))


def _instrumental(tokens, budget):
    if not any(t.surface == ',' or next(_additive(tokens, i), None) for i, t in enumerate(tokens)):
        return
    for root, token in enumerate(tokens):
        verbs = [(lemma, tag) for lemma, tag in known_forms(token.surface)
                 if tag.POS == 'VERB' and tag.mood == 'indc' and tag.transitivity == 'intr'
                 and lemma in _predicative_instrumentals()]
        if not verbs or not 0 < root < len(tokens) - 1:
            continue
        for start, discourse in _prefixes(tokens, root):
            for left, right in [('ablt', 'nomn'), ('nomn', 'ablt')]:
                for lh, lhs in _phrases(tokens, start, root, left, budget):
                    for rh, rhs in _phrases(tokens, root + 1, len(tokens), right, budget):
                        subj, comp = (lh, rh) if left == 'nomn' else (rh, lh)
                        links = {**discourse, **lhs, **rhs}
                        coordinated = any(link.role == 'nominal_conjunct' and link.head == subj for link in links.values())
                        if not coordinated or not any(link.role == 'genitive_modifier' for link in links.values()):
                            continue
                        for verb, tag in verbs:
                            if tag.number != 'plur' or tag.person not in (None, '3per'):
                                continue
                            tree = {**links, root: Link('predicate', verb, None, 'V1', morphology=from_tag(tag)),
                                    subj: Link('subject', links[subj].lemma, root, 'S1', 'nomn'),
                                    comp: Link('predicative_complement', links[comp].lemma, root, 'V.XCOMP',
                                               'ablt', controller=subj)}
                            yield tuple(tree[k] for k in range(len(tokens)))
                            cases, roles = government()
                            if 'ablt' in cases.get(verb, ()):
                                role = roles.get((verb, 'ablt'), 'oblique')
                                if role != 'predicative_complement':
                                    tree[comp] = Link(role, links[comp].lemma, root, 'V.GOV', 'ablt')
                                    yield tuple(tree[k] for k in range(len(tokens)))


def trees(tokens, *, budget=256):
    yield from _series(tokens, budget)
    yield from _instrumental(tokens, budget)


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    if any(any(link.rule == 'V2.CONJ' for link in tree) for tree in trees):
        groups = [tuple(i for i, link in enumerate(tree)
                        if (link.rule == 'V2' and link.head is None) or link.rule == 'V2.CONJ')
                  for tree in trees]
        if all(groups) and len(set(groups)) > 1:
            labels = {g: ' '.join(_span_label(tokens, i) for i in g) for g in dict.fromkeys(groups)}
            yield Probe('Какие слова здесь служат сказуемыми и называют признаки подлежащего?',
                        tuple(labels.values()), text), [labels[g] for g in groups]
    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        if not any(link.rule == 'V.XCOMP' for link in links):
            continue
        if all(link.rule in {'V.XCOMP', 'V.GOV'} for link in links) and any(link.rule == 'V.GOV' for link in links):
            focus = _span_label(tokens, i)
            options = (focus, 'нет такого слова')
            question = 'Какое слово в творительном падеже называет, кем или чем выступает подлежащее?'
            if all('negated' in (tree[tree[i].head].scope or '').split('_') for tree in trees):
                question = ('Какое слово называет роль или состояние подлежащего, о котором говорится '
                            'с отрицанием? Если указан лишь предмет или способ действия, выберите '
                            '«нет такого слова».')
            yield Probe(question, options, text), [options[0] if link.rule == 'V.XCOMP' else options[1] for link in links]
    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        if {link.rule for link in links} != {'N.GEN', 'N.COORD'} or not all(
                link.role in {'genitive_modifier', 'nominal_conjunct'} for link in links):
            continue
        focus = _span_label(tokens, i)
        heads = {link.head for link in links}
        if len(heads) == 1:
            host, = heads
            start, stop = min(i, host), max(i, host) + 1
            group = _span_label(tokens, start, stop)
            governor = _span_label(tokens, host)
            question = (f'Как здесь связано «{focus}» со словом «{governor}»? '
                        f'Если оно отвечает от него на вопрос «кого?» или «чего?», выберите всё сочетание. '
                        f'Если перечислены два предмета, выберите только «{focus}».')
            yield Probe(question, (group, focus), text), [
                group if link.role == 'genitive_modifier' else focus for link in links]
            continue
        anchors = [link.head if link.role == 'nominal_conjunct' else None for link in links]
        labels = {j: _span_label(tokens, j) if j is not None else focus for j in dict.fromkeys(anchors)}
        if len(set(labels.values())) != len(labels):
            continue
        question = (f'Как употреблено слово «{focus}»? Если оно уточняет другое существительное '
                    f'и отвечает на вопрос «кого?» или «чего?», выберите «{focus}». '
                    'Если перечислены однородные члены, выберите слово, которое перечислено вместе с ним.')
        yield Probe(question, tuple(labels.values()), text), [labels[j] for j in anchors]
