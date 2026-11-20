from dataclasses import replace
from functools import cache

from .named_arguments import opaque_cases
from .nominal_groups import _members, _prepositions
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .prepositions import DASHES
from .probe import Probe
from .rules import known_forms
from .utterances import _map, _root


def trees(tokens, parse, budget):
    finite = [i for i, token in enumerate(tokens)
              if any(tag.POS == 'VERB' and tag.mood == 'indc' for _, tag in known_forms(token.surface))]
    if len(finite) != 1:
        return
    verb, = finite
    if not any(t.surface in DASHES or t.surface.istitle() for t in tokens[verb + 2:]):
        return

    @cache
    def members(start, prep, case):
        groups = list(_members(tokens, start, prep, case))
        comma = start
        while comma < len(tokens) and any(tag.POS == 'ADJF' for _, tag in known_forms(tokens[comma].surface)):
            comma += 1
        if comma > start and comma < len(tokens) and tokens[comma].surface == ',':
            kept = (*range(comma), *range(comma + 1, len(tokens)))
            for n, lemma, c, attrs in _members(tuple(tokens[j] for j in kept), start, prep, case):
                if n != comma or not any(j == comma - 1 for j, _ in attrs):
                    continue
                head = kept[n]
                links = tuple((kept[j], replace(l, head=head)) for j, l in attrs)
                groups.append((head, lemma, c, (*links, (comma, Link('punctuation', ',', head, 'PUNCT')))))
        if not groups:
            return ()
        end = max(g[0] for g in groups)
        return tuple(dict.fromkeys(g for g in groups if g[0] == end))

    @cache
    def names(index):
        if index == len(tokens) or not tokens[index].surface.istitle():
            return ()
        word = tokens[index].surface
        known = tuple(dict.fromkeys((lemma, tag.case) for lemma, tag in known_forms(word)
                                    if tag.POS == 'NOUN' and tag.case and
                                    {'Geox', 'Orgn', 'Trad', 'Name', 'Surn', 'Patr'} & tag.grammemes))
        if known:
            return known
        return ((word, None),) if opaque_cases(word) else ()

    @cache
    def nominal(start, prep, case, pp):
        groups = []
        pending = []
        for head, lemma, c, attrs in members(start, prep, case):
            links = (*attrs, (head, Link('nominal', lemma, None, 'N1', c)))
            pending.append((head + 1, head, (head,), links))
        seen = set()
        while pending:
            state = pending.pop()
            if state in seen:
                continue
            seen.add(state)
            if len(seen) > budget * max(1, len(tokens) - start):
                raise AnalysisBudgetExceeded('NOMINAL_PREDICATION_BUDGET')
            end, head, path, entries = state
            groups.append((end, head, entries))
            if end >= len(tokens):
                continue
            links = dict(entries)
            for depth, host in enumerate(path):
                governors = path[:depth + 1]
                inside_pp = not any(links[j].role == 'governed' for j in path[depth + 1:])
                for child, lemma, c, attrs in members(end, None, 'gent') if inside_pp else ():
                    link = Link('genitive_modifier', lemma, host, 'N.GEN', c)
                    pending.append((child + 1, head, (*governors, child), (*entries, *attrs, (child, link))))
                if inside_pp and not names(host) and links[host].role != 'apposition':
                    for name, c in names(end):
                        if c not in (None, 'nomn', links[host].case):
                            continue
                        link = Link('apposition', name, host, 'N.APP.NAME', c, scope='proper_name')
                        pending.append((end + 1, head, (*governors, end), (*entries, (end, link))))
                if pp:
                    for first, form in _prepositions(tokens, end):
                        for child, lemma, c, attrs in members(first, form, None):
                            parts = [(end, Link('preposition', form, host, 'P2'))]
                            parts.extend((i, Link('prep_part', tokens[i].surface.casefold(), end, 'P1'))
                                         for i in range(end + 1, first))
                            parts.append((child, Link('governed', lemma, end, 'P1', c)))
                            pending.append((child + 1, head, (*governors, child), (*entries, *attrs, *parts)))
        return tuple(dict.fromkeys(groups))

    @cache
    def definitions(start):
        variants = []
        for split, subject, left in nominal(start, None, 'nomn', False):
            if split >= len(tokens):
                continue
            dash = tokens[split].surface in DASHES
            if not dash and not any(c == 'nomn' for _, c in names(split)):
                continue
            for end, predicate, right in nominal(split + int(dash), None, 'nomn', True):
                if not dash and not any(c == 'nomn' for _, c in names(predicate)):
                    continue
                links = dict((*left, *right))
                noun = links[predicate]
                links[predicate] = replace(noun, role='clause_conjunct', head=verb, rule='V2.PARALLEL',
                                           controller=subject)
                links[subject] = replace(links[subject], role='subject', head=predicate, rule='S1')
                if dash:
                    links[split] = Link('punctuation', tokens[split].surface, predicate, 'V2.DASH')
                variants.append((end, predicate, tuple(links.items())))
        return tuple(variants)

    @cache
    def clauses(start):
        if start == len(tokens):
            return ((),)
        head = start + int(tokens[start].surface == ',')
        variants = []
        for end, predicate, entries in definitions(head):
            separator = ((start, Link('punctuation', ',', predicate, 'CL.PUNCT')),) if head != start else ()
            for rest in clauses(end):
                variants.append((*separator, *entries, *rest))
                if len(variants) > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_PREDICATION_BUDGET')
        return tuple(variants)

    def matrix(end):
        @cache
        def plans(i):
            if i == end:
                return (((), ()),)
            if i == verb:
                return tuple(((i, *rest), extra) for rest, extra in plans(i + 1))
            choices = []
            for first, form in _prepositions(tokens, i):
                for stop, head, entries in nominal(first, form, None, False):
                    if stop > end or i < verb < stop:
                        continue
                    extras = tuple((j, link) for j, link in entries if j != head)
                    for rest, extra in plans(stop):
                        choices.append(((*range(i, first), head, *rest), (*extras, *extra)))
            return tuple(choices)

        options = plans(0)
        if not options and not any(t.surface in DASHES or t.surface == ',' for t in tokens[:end]):
            if all(any(tag.POS in {'NOUN', 'NPRO', 'ADVB', 'VERB', 'ADJF'} for _, tag in known_forms(t.surface))
                   for t in tokens[:end]):
                options = [(tuple(range(end)), ())]
        for kept, extras in options:
            for clause in parse(tuple(tokens[i] for i in kept)):
                if kept[_root(clause)] != verb:
                    continue
                links = _map(clause, kept) | dict(extras)
                yield links
                prep = links[0]
                if (prep.role == 'preposition' and prep.head == verb and 0 < verb and not prep.scope
                        and any(link.role == 'genitive_modifier' for j, link in extras if j < verb)):
                    yield links | {0: replace(prep, scope='qualification')}

    seen = set()
    for start in range(verb + 1, len(tokens)):
        if start > 0 and tokens[start - 1].surface == ',':
            continue
        tails = clauses(start)
        if not tails:
            continue
        for main in matrix(start):
            for tail in tails:
                if (tokens[start].surface != ',' and not any(l.rule == 'V2.DASH' for _, l in tail)
                        and sum(l.rule == 'V2.PARALLEL' for _, l in tail) < 2):
                    continue
                result = main | dict(tail)
                tree = tuple(result[j] for j in range(len(tokens)))
                if tree not in seen:
                    seen.add(tree)
                    if len(seen) > budget:
                        raise AnalysisBudgetExceeded('NOMINAL_PREDICATION_BUDGET')
                    yield tree


def partitions(trees, tokens, text):
    if not all(any(link.rule == 'V2.PARALLEL' and link.controller is not None for link in t) for t in trees):
        return
    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        roles = {l.role for l in links}
        if roles == {'apposition', 'genitive_modifier'}:
            word = _span_label(tokens, i)
            labels = [word if link.role == 'apposition' else _span_label(tokens, link.head) for link in links]
            if len(set(labels)) > 1:
                question = (f'Как употреблено «{word}»? Если это название самого предмета, выберите '
                            f'«{word}». Если это ответ на вопрос «кого или чего?», выберите слово, '
                            'от которого задаётся вопрос.')
                yield Probe(question, tuple(dict.fromkeys(labels)), text), labels
        if len(roles) != 1 or not roles <= {'preposition', 'apposition', 'genitive_modifier'}:
            continue
        heads = [link.head for link in links]
        if None in heads or len(set(heads)) < 2:
            continue
        labels = {j: _span_label(tokens, j) for j in sorted(set(heads))}
        word = _span_label(tokens, i)
        if roles == {'apposition'}:
            question = f'Какой предмет или место здесь носит название «{word}»?'
        elif roles == {'genitive_modifier'}:
            question = f'От какого слова задаётся вопрос «кого или чего?» к слову «{word}»?'
        else:
            end = max((j for t in trees for j, link in enumerate(t) if link.head == i and link.role == 'governed'), default=i)
            phrase = _span_label(tokens, i, end + 1)
            related = {other.head for t in trees for j, other in enumerate(t[:i]) if other.role == 'preposition'
                       and any(node.role == 'governed' and node.head == j for node in t[j + 1:i])}
            for host in related.intersection(heads):
                if all(any(t[j].role == 'preposition' and t[j].head == host for j in range(host + 1, i))
                       for t in trees):
                    labels[host] = _span_label(tokens, host, i)
            question = f'Что в этом описании уточняют слова «{phrase}»?'
        yield Probe(question, tuple(labels.values()), text), [labels[j] for j in heads]


def parallel(trees):
    return bool(trees) and all(sum(l.rule == 'V2.PARALLEL' for l in tree) > 1 for tree in trees)


def confirmation(tokens, tree, i, text):
    link = tree[i]
    if link.rule != 'V2.PARALLEL' or link.controller is None:
        return None
    if any(l.rule == 'V2.DASH' and l.head == i for l in tree):
        return None
    subject = _span_label(tokens, link.controller)
    word = _span_label(tokens, i)
    return Probe(f'Какое слово служит здесь сказуемым при подлежащем «{subject}»?', (word,), text)
