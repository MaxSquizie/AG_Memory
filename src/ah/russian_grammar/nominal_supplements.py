from dataclasses import replace

from .morphology import from_tag
from .nominal_groups import _agree, _markers
from .rules import known_forms
from .utterances import _map


def _titles(tokens):
    for i in range(1, len(tokens) - 2):
        name, dash, tail = (t.surface for t in tokens[i:i + 3])
        if dash not in {'--', '—', '–'} or not (name.istitle() and tail.istitle()):
            continue
        variants = [(l, t) for l, t in known_forms(name) if 'Geox' in t and t.case == 'nomn']
        for lemma, noun in variants:
            for adj, tag in known_forms(tail):
                if tag.POS == 'ADJF' and _agree(tag, noun):
                    yield i, lemma, noun, adj, tag


def _orphans(tokens):
    for i in range(1, len(tokens) - 2):
        if not any(_markers(tokens, i + 1)):
            continue
        forms = known_forms(tokens[i].surface)
        if any(tag.POS in {'NOUN', 'NPRO'} for _, tag in forms):
            continue
        if any(tag.POS in {'PRTF', 'ADJF'} and tag.case == 'gent' for _, tag in forms):
            yield i


def _restore_ellipsis(tokens, links, i):
    from .parser import Link

    cc = links.get(i + 1)
    if cc is None or cc.role != 'coordinator':
        return
    last = cc.head
    if links[last].role != 'nominal_conjunct':
        return
    first = links[last].head
    if first is None or first >= i or links[first].role not in ('subject', 'object', 'governed'):
        return
    for noun, link in links.items():
        if noun <= last or link.role != 'genitive_modifier' or link.head not in (first, last):
            continue
        if not any(l.role == 'attribute' and l.head == noun and j > last for j, l in links.items()):
            continue
        variants = [(lemma, tag) for lemma, tag in known_forms(tokens[i].surface) if tag.POS in {'PRTF', 'ADJF'}
                    and any(l == link.lemma and n.case == 'gent' and _agree(tag, n)
                            for l, n in known_forms(tokens[noun].surface))]
        for lemma, adj in variants:
            yield {**links, noun: replace(link, head=last),
                   i: Link('genitive_modifier', lemma, first, 'ELL.NOMINAL', 'gent', ellipsis_source=noun,
                           morphology=from_tag(adj))}


def trees(tokens, parse):
    from .parser import Link

    titles = tuple(_titles(tokens))
    orphans = tuple(_orphans(tokens))
    if not titles and not orphans:
        return
    title_options = titles or (None,)
    orphan_options = orphans or (None,)
    for title in title_options:
        for orphan in orphan_options:
            if title is None and orphan is None:
                continue
            hidden = {orphan} if orphan is not None else set()
            if title is not None:
                i, lemma, noun, adj, tag = title
                hidden.update(range(i, i + 3))
            kept = tuple(j for j in range(len(tokens)) if j not in hidden)
            for tree in parse(tuple(tokens[j] for j in kept)):
                links = _map(tree, kept)
                if title is not None:
                    prior = links.get(i - 1)
                    if prior is None or prior.role not in {'genitive_modifier', 'subject', 'object', 'governed'}:
                        continue
                    if not any(l == prior.lemma and t.POS == 'NOUN' for l, t in known_forms(tokens[i - 1].surface)):
                        continue
                    links[i] = Link('apposition', lemma, i - 1, 'NAME.TITLE', morphology=from_tag(noun))
                    links[i + 1] = Link('punctuation', tokens[i + 1].surface, i, 'NAME.DASH')
                    links[i + 2] = Link('apposition', adj, i, 'NAME.TITLE.PART', morphology=from_tag(tag))
                variants = (links,) if orphan is None else _restore_ellipsis(tokens, links, orphan)
                for variant in variants:
                    yield tuple(variant[j] for j in range(len(tokens)))
