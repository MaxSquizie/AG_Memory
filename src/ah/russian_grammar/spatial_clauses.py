from dataclasses import replace
from functools import cache

from .adjuncts import SPATIAL, _lexicon
from .morphology import NOMINAL_ROLES, PREDICATE_ROLES
from .rules import known_forms
from .spatial_prefix import deictic_role


@cache
def _place_nouns():
    entries, _ = _lexicon()
    return {lemma for kind, question, _, lemma in entries if kind == 'nominal' and question in SPATIAL.values()}


def _owner(links, i):
    while i is not None and links[i] is not None:
        if links[i].role in PREDICATE_ROLES | {'infinitive', 'participle'}:
            return i
        i = links[i].head
    return None


def nominal_anchor(link, surface):
    if link.role not in NOMINAL_ROLES | {'apposition', 'genitive_modifier'}:
        return None
    tags = [tag for lemma, tag in known_forms(surface) if lemma == link.lemma and tag.POS == 'NOUN']
    if link.lemma in _place_nouns() or any('Geox' in tag for tag in tags):
        return 'spatial'
    if any(tag.animacy == 'inan' for tag in tags):
        return 'possible'
    return None


def _nominal_sites(prefix, words):
    i = len(prefix) - 1
    while i is not None and prefix[i] is not None:
        link = prefix[i]
        if link.role in PREDICATE_ROLES:
            break
        status = nominal_anchor(link, words[i])
        if status:
            yield i, status
        i = link.head


def _readings(prefix, levels, boundary, words, tokens, chart):
    from .relative_clauses import INDIRECT

    used = {link.antecedent for link in prefix if link and link.rule == 'CL.SPATIAL.REF'}
    nominals = tuple(_nominal_sites(prefix, words))
    for level in range(len(levels) - 1, -1, -1):
        host = levels[level][1]
        governors = [host]
        i = len(prefix) - 1
        while i is not None and i != host and prefix[i] is not None:
            if prefix[i].role == 'infinitive' and _owner(prefix, prefix[i].head) == host:
                governors.append(i)
            i = prefix[i].head
        for governor in governors:
            if prefix[governor].lemma in INDIRECT and not any(
                    link and link.role == 'clause_complement' and link.head == governor for link in prefix):
                yield level, 'clause_complement', governor
            for i, link in enumerate(prefix):
                if not link or link.role != 'adverb' or not deictic_role(link.lemma) or i in used:
                    continue
                if _owner(prefix, i) != governor:
                    continue
                if chart is None or chart.permits(tokens[boundary.marker].start, tokens[i].start):
                    yield level, 'clause_relative', i
            uncertain = False
            for i, status in nominals:
                if _owner(prefix, i) == governor:
                    yield level, 'clause_relative', i
                    uncertain |= status == 'possible'
            if uncertain:
                yield level, 'clause_adverbial', governor


def bind(tree, marker, child, host, role):
    links = list(tree)
    if role == 'clause_relative':
        rule, scope, ref, antecedent = 'CL.REL', 'relative', 'CL.SPATIAL.REF', host
    elif role == 'clause_complement':
        rule, scope, ref, antecedent = 'CL.COMP', 'embedded', 'CL.SPATIAL.WH', None
    else:
        rule, scope, ref, antecedent = 'CL.ADV', 'adverbial', 'CL.SPATIAL.FREE', None
    links[marker] = replace(links[marker], role='adverb', rule=ref, head=child, antecedent=antecedent,
                            scope=None)
    links[child] = replace(links[child], role=role, rule=rule, head=host, scope=links[child].scope or scope)
    return tuple(links)


def attachments(prefix, levels, boundary, leaf, root, words, tokens, chart):
    from .clauses import _markers

    tree = prefix + _markers(boundary, root, words) + leaf
    options = list(_readings(prefix, levels, boundary, words, tokens, chart))
    if not options:
        options.append((len(levels) - 1, 'clause_adverbial', levels[-1][1]))
    for level, role, host in options:
        yield bind(tree, boundary.marker, root, host, role), levels[:level + 1] + ((root, root),)


def centered(tokens, outside, outer, host, inside, parse, chart, budget):
    from .parser import Link
    from .spatial_leaves import trees as leaves
    from .utterances import _map

    marker = inside[0]
    anchor = outside[host]
    link = outer[host]
    if link.role == 'adverb' and deictic_role(link.lemma):
        if chart is not None and not chart.permits(tokens[marker].start, tokens[anchor].start):
            return
        sites = [(anchor, 'clause_relative')]
    else:
        status = nominal_anchor(link, tokens[anchor].surface)
        if not status:
            return
        sites = [(anchor, 'clause_relative')]
        if status == 'possible' and (governor := _owner(outer, host)) is not None:
            sites.append((outside[governor], 'clause_adverbial'))
    positions = inside[1:]
    if not positions:
        return
    for child in leaves(tuple(tokens[j] for j in positions), parse, budget):
        root = next((positions[i] for i, item in enumerate(child)
                     if item.role == 'predicate' and item.head is None), None)
        if root is None:
            continue
        result = _map(outer, outside) | _map(child, positions)
        result[marker] = Link('adverb', tokens[marker].surface.casefold(), root, 'CL.SPATIAL.REF')
        for i in (marker - 1, positions[-1] + 1):
            if 0 <= i < len(tokens) and tokens[i].surface == ',' and i not in result:
                result[i] = Link('punctuation', ',', root, 'CL.PUNCT')
        assembled = tuple(result[i] for i in range(len(tokens)))
        for target, role in sites:
            yield bind(assembled, marker, root, target, role)
