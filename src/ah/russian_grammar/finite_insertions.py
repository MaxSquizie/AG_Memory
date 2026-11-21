from dataclasses import replace

from . import adjuncts
from .parentheses import _pairs
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .probe import Probe
from .rules import known_forms
from .utterances import _map, _root


def _finite(tokens):
    for i, token in enumerate(tokens):
        readings = {(lemma, str(tag.tense)) for lemma, tag in known_forms(token.surface)
                    if tag.POS == 'VERB' and tag.mood == 'indc'}
        if readings:
            yield i, readings


def _spans(tokens, finite, pairs):
    if pairs:
        for start, end in pairs:
            if any(start < i < end for i in finite) and any(i < start or i > end for i in finite):
                yield (*range(start), *range(end + 1, len(tokens))), range(start + 1, end), (start, end)
        return
    if len(finite) != 2 or any(not token.surface.isalpha() and '-' not in token.surface for token in tokens):
        return
    first, second = finite
    shared = {lemma for lemma, _ in finite[first]} & {lemma for lemma, _ in finite[second]}
    temporal = adjuncts._lexicon()[1]
    if not shared and not any(temporal.get(lemma) == 'когда' for token in tokens
                              for lemma, tag in known_forms(token.surface) if tag.POS == 'ADVB'):
        return
    for cut in range(first + 1, second + 1):
        yield range(cut), range(cut, len(tokens)), ()


def trees(tokens, parse, budget):
    finite = dict(_finite(tokens))
    if len(finite) < 2:
        return
    pairs = _pairs(tokens)
    if pairs:
        yield from parse(tokens)
    examined = 0
    for matrix, embedded, marks in _spans(tokens, finite, pairs):
        outer = tuple(tokens[i] for i in matrix)
        inner = tuple(tokens[i] for i in embedded)
        for main in parse(outer):
            primary = _root(main)
            host = matrix[primary]
            matrix_verb = main[primary]
            left_tenses = {t for lemma, t in finite.get(host, ()) if lemma == matrix_verb.lemma}
            if not left_tenses or not any(l.role == 'subject' and l.head == primary for l in main):
                continue
            for child in parse(inner):
                j = _root(child)
                root = embedded[j]
                if root not in finite or not any(l.role == 'subject' and l.head == j for l in child):
                    continue
                verb = child[j]
                if verb.scope not in (None, 'negated'):
                    continue
                right_tenses = {t for lemma, t in finite[root] if lemma == verb.lemma}
                if not right_tenses:
                    continue
                if not marks:
                    if not any(t != u for t in left_tenses for u in right_tenses):
                        continue
                    temporal = adjuncts._lexicon()[1]
                    if matrix_verb.lemma != verb.lemma and not any(
                            link.role == 'adverb' and temporal.get(link.lemma) == 'когда' for link in (*main, *child)):
                        continue
                links = _map(main, matrix) | _map(child, embedded)
                for k in marks:
                    links[k] = Link('punctuation', tokens[k].surface, root, 'PAREN.BOUND')
                aside = 'parenthetical_negated' if verb.scope == 'negated' else 'parenthetical'
                for scope in ((aside,) if marks else (verb.scope, aside)):
                    examined += 1
                    if examined > budget:
                        raise AnalysisBudgetExceeded('FINITE_INSERTION_BUDGET')
                    links[root] = replace(links[root], role='clause_conjunct', head=host,
                                          rule='UTT.PARATAXIS', scope=scope)
                    yield tuple(links[k] for k in range(len(tokens)))


def partitions(trees, tokens, text):
    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        if (all(l.role == 'clause_conjunct' for l in links)
                and {l.scope for l in links} in ({None, 'parenthetical'}, {'negated', 'parenthetical_negated'})):
            label = _span_label(tokens, i)
            other = 'нет такого пояснения'
            question = 'Какое действие дано как добавочное пояснение к основному сообщению?'
            answers = [label if (l.scope or '').startswith('parenthetical') else other for l in links]
            yield Probe(question, (label, other), text), answers
        if all(l.role == 'adverb' and l.head is not None and l.scope != 'coordination' for l in links):
            heads = tuple(dict.fromkeys(l.head for l in links))
            if len(heads) > 1 and all(tree[h].role in ('predicate', 'clause_conjunct') for tree in trees for h in heads):
                labels = {h: _span_label(tokens, h) for h in heads}
                question = f'К какому действию относится слово «{_span_label(tokens, i)}»?'
                yield Probe(question, tuple(labels.values()), text), [labels[l.head] for l in links]
