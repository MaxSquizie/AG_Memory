from dataclasses import replace
from html import unescape
from unicodedata import category, name

from .parser import Link, _span_label
from .probe import Probe
from .rules import known_forms, unaccented
from .utterances import _map, _root


_PAIRS = {'«': '»', '„': '“', '“': '”', '"': '"', '``': "''"}


def spans(tokens):
    pending = []
    pairs = []
    for index, token in enumerate(tokens):
        sign = unescape(token.surface)
        if pending and pending[-1][1] == sign:
            start, _ = pending.pop()
            pairs.append((start, index))
        elif sign in _PAIRS:
            pending.append((index, _PAIRS[sign]))
    return () if pending else tuple(sorted(pairs))


def _lemma(word):
    forms = [(lemma, tag) for lemma, tag in known_forms(word)
             if tag.case == 'nomn' and tag.POS in ('NOUN', 'ADJF', 'NPRO')]
    return forms[0][0] if len({lemma for lemma, _ in forms}) == 1 else word.casefold()


def _series_layouts(tokens, quoted):
    if quoted:
        if len(quoted) < 2 or quoted[-1][1] != len(tokens) - 1:
            return
        first = quoted[0][0]
        if not first or tokens[first - 1].surface != ':':
            return
        if any(right >= start or any(tokens[j].surface != ',' for j in range(right + 1, start))
               for (_, right), (start, _) in zip(quoted, quoted[1:])):
            return
        if any(start + 1 >= end for start, end in quoted):
            return
        yield first - 1, tuple((left + 1, right) for left, right in quoted), False
        return
    if not any(t.surface.isdecimal() for t in tokens):
        return
    initials = [i for i, t in enumerate(tokens) if i and t.surface.istitle()]
    for pos, i in enumerate(initials[:-1]):
        if not any(t.surface.isdecimal() for t in tokens[:i]):
            continue
        sequence = initials[pos:]
        chunks = tuple(zip(sequence, (*sequence[1:], len(tokens))))
        if any(not (tokens[j].surface.isalnum() or all(category(ch)[0] == 'S' for ch in tokens[j].surface))
               for start, stop in chunks for j in range(start, stop)):
            continue
        yield i, chunks, True


def _series(tokens, quoted, parse):
    for end, groups, inferred in _series_layouts(tokens, quoted):
        for matrix in parse(tokens[:end]):
            hosts = {link.head for link in matrix if link.role == 'numeral' and
                     link.quantity_kind == 'cardinal' and link.quantity == str(len(groups))}
            if len(hosts) != 1:
                continue
            host, = hosts
            if host is None or matrix[host].role not in {'subject', 'object', 'governed'}:
                continue
            links = dict(enumerate(matrix))
            for n, (start, stop) in enumerate(groups):
                role = 'nominal_conjunct' if n else 'apposition'
                rule = 'TITLE.MEMBER' if n else 'TITLE.SERIES'
                links[start] = Link(role, _lemma(tokens[start].surface), groups[0][0] if n else host,
                                    rule, scope='title')
                for j in range(start + 1, stop):
                    links[j] = Link('apposition' if not tokens[j].surface.isalpha() else 'name_part',
                                    tokens[j].surface.casefold(), start, 'TITLE.PART')
                if quoted:
                    for j in quoted[n]:
                        links[j] = Link('punctuation', tokens[j].surface, start, 'TITLE.QUOTE')
                    if n:
                        for j in range(quoted[n-1][1] + 1, quoted[n][0]):
                            links[j] = Link('punctuation', ',', start, 'TITLE.SEP')
            if quoted:
                links[end] = Link('punctuation', ':', host, 'TITLE.LIST')
            yield tuple(links[i] for i in range(len(tokens)))


def _latin(surface):
    return surface.isalpha() and all(name(ch, '').startswith('LATIN ') for ch in surface)


def _alias_layouts(tokens, quoted):
    if quoted:
        if len(quoted) != 2:
            return
        (left, end), (inner, closing) = quoted
        if (left > 0 and end > left + 1 and closing > inner + 1 and inner == end + 2
                and tokens[end + 1].surface == '(' and closing + 1 < len(tokens)
                and tokens[closing + 1].surface == ')'):
            yield left, (left + 1, end), (inner + 1, closing), closing + 2
        return
    from .nominal_groups import _prepositions

    for left in range(1, len(tokens)):
        if not _latin(tokens[left].surface) or _latin(tokens[left-1].surface):
            continue
        end = left + 1
        while end < len(tokens) and _latin(tokens[end].surface):
            end += 1
        if end >= len(tokens) or not tokens[end].surface.istitle():
            continue
        stops = [i for i in range(end + 1, len(tokens)) if
                 any(marker < len(tokens) and any(lemma == 'который' for lemma, _ in known_forms(tokens[marker].surface))
                     for marker, _ in _prepositions(tokens, i))]
        if not stops:
            stops = [len(tokens)]
        for stop in stops:
            yield left, (left, end), (end, stop), stop


def _calendar_base(tokens, parse):
    years = [i for i in range(1, len(tokens) - 1) if tokens[i].surface.isdecimal()
             and len(tokens[i].surface) == 4 and any(lemma == 'год' and tag.case in {'loct', 'loc2'}
                     for lemma, tag in known_forms(tokens[i + 1].surface))]
    if not years:
        yield from parse(tokens)
        return
    kept = tuple(i for i in range(len(tokens)) if i not in years)
    for tree in parse(tuple(tokens[i] for i in kept)):
        links = _map(tree, kept)
        for i in years:
            head = links[i + 1]
            if head.lemma != 'год' or head.role != 'governed' or head.case not in ('loct', 'loc2'):
                break
            links[i] = Link('numeral', tokens[i].surface, i + 1, 'CAL.YEAR', quantity=tokens[i].surface,
                            quantity_kind='ordinal')
        else:
            yield tuple(links[i] for i in range(len(tokens)))


def _matrix(tokens, parse):
    from .nominal_groups import _members

    for i in range(1, len(tokens)):
        verbs = {lemma for lemma, tag in known_forms(tokens[i].surface) if tag.POS == 'INFN' and 'tran' in tag}
        if not verbs or not any(tag.POS == 'NOUN' for _, tag in known_forms(tokens[i-1].surface)):
            continue
        for noun, lemma, case, attrs in _members(tokens, i + 1, None, 'accs'):
            if noun + 1 != len(tokens):
                continue
            for base in _calendar_base(tokens[:i], parse):
                if base[-1].role not in {'governed', 'object', 'subject', 'genitive_modifier'}:
                    continue
                for verb in sorted(verbs):
                    links = dict(enumerate(base))
                    links[i] = Link('infinitive', verb, i-1, 'INF.NOUN', scope='embedded')
                    links[noun] = Link('object', lemma, i, 'O1', case=case)
                    links.update(attrs)
                    yield tuple(links[j] for j in range(len(tokens)))
    yield from _calendar_base(tokens, parse)


def _aliases(tokens, quoted, parse):
    for left, foreign, native, stop in _alias_layouts(tokens, quoted):
        if not all(_latin(tokens[i].surface) for i in range(*foreign)):
            continue
        kept = (*range(left), *range(stop, len(tokens)))
        if not any(tag.POS == 'NOUN' for _, tag in known_forms(tokens[left - 1].surface)):
            continue
        for translation in parse(tokens[slice(*native)]):
            pivot = _root(translation)
            for matrix in _matrix(tuple(tokens[i] for i in kept), parse):
                links = _map(matrix, kept)
                if links[left - 1].role not in {'subject', 'object', 'governed', 'genitive_modifier'}:
                    continue
                start = foreign[0]
                links[start] = Link('apposition', tokens[start].surface.casefold(), left - 1, 'TITLE.FOREIGN', scope='title')
                for j in range(start + 1, foreign[1]):
                    links[j] = Link('name_part', tokens[j].surface.casefold(), start, 'TITLE.PART')
                positions = tuple(range(*native))
                links.update(_map(translation, positions))
                native_head = positions[pivot]
                links[native_head] = replace(links[native_head], role='apposition', head=start,
                                             rule='TITLE.ALIAS', scope=('title_' + links[native_head].scope
                                                                       if links[native_head].scope else 'title'))
                for j in range(left, stop):
                    if j not in links:
                        host = start if j < foreign[1] + 1 else native_head
                        links[j] = Link('punctuation', tokens[j].surface, host, 'TITLE.QUOTE')
                yield tuple(links[j] for j in range(len(tokens)))


def _listed_mentions(tokens, budget):
    from .nominal_groups import _markers
    from .participle_connectives import relations

    if not any(token.surface == ',' for token in tokens):
        return
    groups = []
    separators = {}
    start = i = 0
    final_marker = False
    while i < len(tokens):
        word = unaccented(tokens[i].surface)
        if word.isalpha() and word.istitle():
            i += 1
            continue
        if i == start or final_marker:
            return
        groups.append((start, i))
        if word == ',':
            separators[i] = Link('punctuation', ',', i + 1, 'TITLE.SEP')
            i += 1
        else:
            markers = [marker for marker in _markers(tokens, i) if
                       set(relations(' '.join(tokens[j].surface for j in marker))) == {'addition'}]
            if len(markers) != 1:
                return
            marker, = markers
            i = marker[-1] + 1
            for j in marker:
                separators[j] = Link('coordinator' if j == marker[0] else 'coordinator_part',
                                     tokens[j].surface.casefold(), i if j == marker[0] else marker[0], 'P.COORD')
            final_marker = True
        start = i
    if not final_marker or start == len(tokens):
        return
    groups.append((start, len(tokens)))
    links = dict(separators)
    for start, end in groups:
        lemma = tokens[start].surface
        links[start] = (Link('predicate', lemma, None, 'TITLE.MENTION.LIST', scope='heading') if start == 0 else
                        Link('nominal_conjunct', lemma, 0, 'TITLE.LIST.ITEM'))
        for j in range(start + 1, end):
            links[j] = Link('name_part', tokens[j].surface, start, 'TITLE.PART')
    from .parser import AnalysisBudgetExceeded

    variants = [(tuple(links[j] for j in range(len(tokens))), -1)]
    for n, ((left, comma), (right, end)) in enumerate(zip(groups, groups[1:])):
        if right != comma + 1 or tokens[comma].surface != ',':
            continue
        size = comma - left + end - right
        neighbors = (j for j in (n - 1, n + 2) if 0 <= j < len(groups))
        if not any(groups[j][1] - groups[j][0] == size for j in neighbors):
            continue
        joined = []
        for tree, last in variants:
            if last >= n:
                continue
            updated = list(tree)
            updated[comma] = Link('punctuation', ',', right, 'TITLE.INNER.COMMA')
            for j in range(right, end):
                updated[j] = Link('name_part', tokens[j].surface, left, 'TITLE.PART')
            joined.append((tuple(updated), n + 1))
            if len(variants) + len(joined) > budget:
                raise AnalysisBudgetExceeded('TITLE_BUDGET')
        variants.extend(joined)
    for tree, _ in variants:
        yield tree


def trees(part, parse, budget):
    from .parser import AnalysisBudgetExceeded

    yield from _listed_mentions(part, budget)
    from . import dated_headings

    quoted = spans(part)
    yield from dated_headings.trees(part, quoted, budget)
    output = set()
    for family in (_series, _aliases):
        for tree in family(part, quoted, parse):
            if tree not in output:
                output.add(tree)
                if len(output) > budget:
                    raise AnalysisBudgetExceeded('TITLE_BUDGET')
                yield tree


def title_bounds(tree, root):
    children = {}
    for i, link in enumerate(tree):
        if link.role != 'punctuation':
            children.setdefault(link.head, []).append(i)
    pending = [root]
    first = last = root
    while pending:
        i = pending.pop()
        first, last = min(first, i), max(last, i)
        pending.extend(children.get(i, ()))
    return first, last


def partitions(trees, tokens, text):
    for mark, token in enumerate(tokens):
        if token.surface != ',':
            continue
        rules = {tree[mark].rule for tree in trees}
        if rules != {'TITLE.INNER.COMMA', 'TITLE.SEP'}:
            continue
        merged = next(tree for tree in trees if tree[mark].rule == 'TITLE.INNER.COMMA')
        right = mark + 1
        left = merged[right].head
        end = right + 1
        while end < len(merged) and merged[end].rule == 'TITLE.PART' and merged[end].head == left:
            end += 1
        a = text[tokens[left].start:tokens[mark - 1].end]
        b = text[tokens[right].start:tokens[end - 1].end]
        extra = any(tree[j].rule == 'TITLE.INNER.COMMA' for tree in trees
                    for j in (left - 1, end) if 0 <= j < len(tree))
        one = f'одно название «{a} {b}»'
        two = f'слова «{a}» и «{b}» входят в разные названия' if extra else f'два названия «{a}» и «{b}»'
        phrase = text[tokens[left].start:tokens[end - 1].end]
        question = f'Как в этом перечне следует прочитать сочетание «{phrase}»?'
        yield Probe(question, (one, two), text), [one if tree[mark].rule == 'TITLE.INNER.COMMA' else two for tree in trees]
    regions = []
    for tree in trees:
        titles = {title_bounds(tree, i): i for i, link in enumerate(tree)
                  if link.role == 'apposition' and (link.scope or '').split('_', 1)[0] == 'title'}
        if not titles:
            return
        regions.append(titles)
    for bounds in sorted(set.intersection(*(set(titles) for titles in regions))):
        heads = [titles[bounds] for titles in regions]
        if len(set(heads)) < 2:
            continue
        first, last = bounds
        phrase = text[tokens[first].start:tokens[last].end]
        labels = {i: _span_label(tokens, i) for i in sorted(set(heads))}
        question = f'Какое слово в названии «{phrase}» обозначает то, о чём говорится, и уточняется остальными словами?'
        yield Probe(question, tuple(labels.values()), text), [labels[head] for head in heads]


def confirmation(tokens, tree, index, text):
    from . import dated_headings

    note = dated_headings.confirmation(tokens, tree, index, text)
    if note is not None:
        return note
    link = tree[index]
    if link.rule == 'INF.NOUN':
        target = _span_label(tokens, link.head)
        return Probe(f'Какое существительное поясняет действие «{tokens[index].surface}»?', (target,), text)
    if link.rule in ('TITLE.SERIES', 'TITLE.MENTION.LIST'):
        names = [index, *(j for j, other in enumerate(tree) if other.head == index and other.role == 'nominal_conjunct')]
        labels = []
        for name in names:
            rest = [j for j, other in enumerate(tree) if other.head == name and other.rule == 'TITLE.PART']
            if link.rule == 'TITLE.MENTION.LIST':
                labels.append(' '.join(tokens[j].surface for j in (name, *rest)))
            else:
                labels.append(_span_label(tokens, name, max([name, *rest]) + 1))
        items = ', '.join(f'«{label}»' for label in labels)
        if index > 0 and tree[index - 1].rule == 'TITLE.QUOTE':
            return Probe(f'Для какого слова {items} перечислены как названия?',
                         (_span_label(tokens, link.head),), text)
        phrase = _span_label(tokens, index, len(tree))
        return Probe(f'Образуют ли {items} перечень отдельных названий? Если да, выберите весь перечень.',
                     (phrase,), text)
    if link.rule == 'TITLE.ALIAS':
        first, last = title_bounds(tree, index)
        phrase = _span_label(tokens, first, last + 1)
        return Probe('Какие слова дают второй вариант названия?', (phrase,), text)
    return None
