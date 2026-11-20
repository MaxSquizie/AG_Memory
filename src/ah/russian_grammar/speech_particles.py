from dataclasses import replace

from .morphology import PREDICATE_ROLES
from .rules import known_forms


POLAR = {'ли', 'ль'}
DOUBT = {('едва', 'ли'), ('вряд', 'ли')}
APPROXIMATE = {('едва', 'ли', 'не'), ('чуть', 'ли', 'не')}
JUSSIVE = {'пусть', 'пускай'}


def _predicate(tree, index):
    while index is not None and tree[index].role not in PREDICATE_ROLES:
        index = tree[index].head
    return index


def _local(part, parse, pos, width, kind):
    from .parser import Link
    from .utterances import _map, _root

    kept = (*range(pos), *range(pos + width, len(part)))
    neighbor = pos - 1 if kind == 'polar' else pos + width
    if neighbor not in kept or not part[neighbor].surface.isalpha():
        return
    for tree in parse(tuple(part[j] for j in kept)):
        pivot = kept.index(neighbor)
        head = _predicate(tree, pivot)
        if head is None:
            continue
        link = tree[head]
        polar_rule = 'UTT.POLAR'
        if kind == 'polar' and head != _root(tree):
            if link.rule != 'CL.CONJ':
                continue
            anchor = link.head
            while anchor is not None and tree[anchor].rule == 'CL.CONJ':
                anchor = tree[anchor].head
            if anchor is not None and tree[anchor].role == 'clause_complement':
                polar_rule = 'CL.POLAR.MARK'
            elif not any(item.rule == 'UTT.POLAR' for item in tree):
                continue
        if kind == 'directive':
            if head != _root(tree) or not any(lemma == link.lemma and tag.POS == 'VERB'
                    and tag.person in ('1per', '3per') and tag.mood == 'indc'
                    for lemma, tag in known_forms(part[kept[head]].surface)):
                continue
        links = _map(tree, kept)
        target = kept[head]
        if kind == 'polar':
            links[pos] = Link('particle', part[pos].surface.casefold(), neighbor, polar_rule)
        else:
            if kind == 'approximate' and head != pivot:
                target = neighbor
                if tree[pivot].role == 'subject':
                    continue
            previous = links[target].scope
            scope = kind + ('_' + previous if previous else '')
            links[target] = replace(links[target], scope=scope)
            links[pos] = Link('particle', part[pos].surface.casefold(), target, 'UTT.PARTICLE')
            for j in range(pos + 1, pos + width):
                links[j] = Link('fixed', part[j].surface.casefold(), pos, 'UTT.FIXED')
        yield tuple(links[j] for j in range(len(part)))


def _embedded(part, parse, marker):
    from .parser import Link
    from .relative_clauses import INDIRECT
    from .utterances import _linked, _root

    governors = [i for i, token in enumerate(part[:marker]) if any(
        lemma in INDIRECT for lemma, _ in known_forms(token.surface))]
    if not governors:
        return
    for start in range(governors[0] + 1, marker):
        if part[start].surface == ',':
            continue
        end = start - int(part[start - 1].surface == ',')
        for left in parse(part[:end]):
            host = _root(left)
            if left[host].lemma not in INDIRECT or any(
                    l.role == 'clause_complement' and l.head == host for l in left):
                continue
            for right in parse(part[start:]):
                if right[marker - start].rule != 'UTT.POLAR':
                    continue
                scope = right[_root(right)].scope
                links, _, child = _linked(left, right, range(end), range(start, len(part)),
                                           'clause_complement', 'CL.POLAR', 'embedded' + ('_' + scope if scope else ''))
                for j, link in enumerate(right, start):
                    if link.rule == 'UTT.POLAR':
                        links[j] = replace(links[j], rule='CL.POLAR.MARK')
                if end < start:
                    links[end] = Link('punctuation', ',', child, 'CL.PUNCT')
                yield tuple(links[j] for j in range(len(part)))


def _concessive(part, parse):
    from .parser import Link
    from .participle_connectives import relations
    from .utterances import _linked

    for i in range(2, len(part) - 1):
        if 'contrast' not in relations(part[i].surface):
            continue
        end = i - int(part[i - 1].surface == ',')
        for premise in parse(part[1:end]):
            for matrix in parse(part[i + 1:]):
                links, root, child = _linked(matrix, premise, range(i + 1, len(part)), range(1, end),
                                              'clause_adverbial', 'CL.ADV', 'hypothetical')
                links[0] = Link('clause_marker', part[0].surface.casefold(), child, 'CL.MARK', scope='hypothetical')
                links[i] = Link('clause_marker', part[i].surface.casefold(), root, 'CL.CONTRAST')
                if end < i:
                    links[end] = Link('punctuation', ',', child, 'CL.PUNCT')
                yield tuple(links[j] for j in range(len(part)))


def trees(part, parse):
    words = tuple(t.surface.casefold() for t in part)
    if not words or any(t.surface in ('«', '»', '"', '„', '“', '”') for t in part):
        return
    for i, token in enumerate(part):
        if words[i:i + 3] in APPROXIMATE and part[i + 1].surface.islower():
            yield from _local(part, parse, i, 3, 'approximate')
        elif words[i:i + 2] in DOUBT and part[i + 1].surface.islower():
            yield from _local(part, parse, i, 2, 'doubt')
        elif i and words[i] in POLAR and token.surface.islower() and words[i - 1:i + 1] not in DOUBT:
            if words[i - 1] == 'то' or words[i - 1:i + 2] in APPROXIMATE:
                continue
            yield from _embedded(part, parse, i)
            yield from _local(part, parse, i, 1, 'polar')
        elif words[i] in JUSSIVE:
            yield from _local(part, parse, i, 1, 'directive')
            if i == 0:
                yield from _concessive(part, parse)


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe
    from .utterances import _root

    if not tokens or tokens[0].surface.casefold() not in JUSSIVE:
        return
    scopes = {tree[0].rule for tree in trees}
    if scopes != {'UTT.PARTICLE', 'CL.MARK'}:
        return
    labels = [_span_label(tokens, _root(tree)) for tree in trees]
    options = tuple(dict.fromkeys(labels))
    if len(options) != 2:
        return
    first = _span_label(tokens, trees[0][0].head)
    question = (f'Какое действие составляет главное сообщение? Выберите «{first}», если к нему побуждают. '
                'Если его допускают ради последующего возражения, выберите действие из второй части.')
    yield Probe(question, options, text), labels
