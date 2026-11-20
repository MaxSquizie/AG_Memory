from dataclasses import replace

from .homogeneous import _restore
from .nominal_groups import _prepositions
from .morphology import PREDICATE_ROLES


def extent(tree, start, *, external_modifier=False):
    children = {}
    for i, link in enumerate(tree):
        if link.head is not None and link.role != 'punctuation':
            children.setdefault(link.head, []).append(i)
    pending = [start]
    members = set()
    while pending:
        index = pending.pop()
        if index not in members:
            members.add(index)
            for child in children.get(index, ()):
                if (external_modifier and child == start - 1 and tree[child].role == 'adverb'
                        and tree[index].role == 'governed' and tree[index].head == start):
                    continue
                pending.append(child)
    end = max(members) + 1
    if min(members) == start and all(i in members or tree[i].role == 'punctuation' for i in range(start, end)):
        return end
    return None


def _events(tokens, recover):
    commas = [i for i, token in enumerate(tokens) if token.surface == ',']
    for left, right in zip(commas, commas[1:]):
        if left and right + 1 < len(tokens) and right >= left + 3 and any(_prepositions(tokens[:right], left + 1)):
            yield (left, right), (left + 1,)
    if recover and len(commas) == 1 and 0 < commas[0] < len(tokens) - 1:
        mark, = commas
        starts = [i for i in range(mark - 1) if any(_prepositions(tokens[:mark], i))]
        if mark + 2 < len(tokens) and any(_prepositions(tokens, mark + 1)):
            starts.append(mark + 1)
        if starts:
            yield (mark,), starts


def _complete_group(tree, start, end):
    prep = tree[start]
    if prep.role != 'preposition' or prep.head is None or start <= prep.head < end:
        return False
    members = tree[start + 1:end]
    return (sum(link.role == 'governed' and link.head == start for link in members) == 1
            and all(link.head is not None and start <= link.head < end for link in members))


def trees(tokens, parse, *, recover, starts_after_comma, ends_before_comma):
    from .parser import Link

    for marks, starts in _events(tokens, recover):
        kept = tuple(i for i in range(len(tokens)) if i not in marks)
        index = {i: j for j, i in enumerate(kept)}
        for tree in parse(tuple(tokens[i] for i in kept)):
            if len(marks) == 1:
                mark, = marks
                if tokens[0].start in starts_after_comma and _complete_group(tree, 0, mark):
                    continue
                if tokens[-1].end in ends_before_comma and _complete_group(tree, mark, len(tree)):
                    continue
            for start in starts:
                first = index[start]
                prep = tree[first]
                if prep.role != 'preposition' or prep.head is None:
                    continue
                stop = extent(tree, first)
                if stop is None:
                    continue
                end = kept[stop - 1] + 1
                if any(mark not in (start - 1, end) for mark in marks):
                    continue
                heads = [j for j in range(first + 1, stop) if tree[j].role == 'governed' and tree[j].head == first]
                if len(heads) != 1:
                    continue
                links = _restore(tree, kept, len(tokens))
                for mark in marks:
                    links[mark] = Link('punctuation', ',', kept[heads[0]], 'PP.DETACHED.COMMA')
                links[start] = replace(links[start], rule='PP.DETACHED')
                yield tuple(links)
                if tree[prep.head].role in PREDICATE_ROLES:
                    links[start] = replace(links[start], scope='qualification')
                    yield tuple(links)
