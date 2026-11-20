from dataclasses import replace
from functools import cache
from importlib.resources import files

from . import clauses, contrastive_regions, quote_titles
from .morphology import NOMINAL_ROLES
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .probe import Probe
from .relative_clauses import _nominal_caption
from .rules import dictionary, known_forms
from .utterances import _map, _root


@cache
def _abbreviations():
    source = files(__package__).joinpath('lexicon/reference-abbreviations.tsv')
    expansions = {}
    for row in source.read_text(encoding='utf8').splitlines():
        prefix, lemma = row.split('\t')
        expansions.setdefault(prefix, []).append(lemma)
    return expansions


def _command(tokens, parse):
    if not tokens:
        return
    attached_dot = tokens[0].surface.endswith('.')
    dot = len(tokens) > 1 and tokens[1].surface == '.'
    positions = (0, *range(1 + int(dot), len(tokens)))
    if len(positions) < 2:
        return
    for lemma in _abbreviations().get(tokens[0].surface.rstrip('.').casefold(), ()):
        for infinitive in dictionary().parse(lemma):
            if infinitive.tag.POS != 'INFN' or infinitive.normal_form != lemma:
                continue
            form = infinitive.inflect({'impr', 'plur'})
            if not form:
                continue
            normalized = (replace(tokens[0], surface=form.word), *(tokens[i] for i in positions[1:]))
            for tree in parse(normalized):
                if tree[0].rule != 'V.IMP' or tree[0].lemma != lemma:
                    continue
                links = _map(tree, positions)
                links[0] = replace(links[0], rule='ABBR.IMP' if attached_dot or dot else 'ABBR.BARE',
                                   implicit_subject=None, morphology=replace(links[0].morphology, number=None))
                if dot:
                    links[1] = Link('punctuation', '.', 0, 'ABBR.DOT')
                yield tuple(links[i] for i in range(len(tokens)))


def _title_regions(tokens):
    spans = quote_titles.spans(tokens)
    if spans:
        first, end = spans[-1]
        if first and end == len(tokens) - 1:
            yield first, tuple(range(first + 1, end)), (first, end)
        return
    for i in range(2, len(tokens)):
        if tokens[i].surface.istitle():
            yield i, tuple(range(i, len(tokens))), ()


def _matrix(tokens, parse, budget):
    if not tokens:
        return
    for start, inside, marks in _title_regions(tokens):
        for title in _nominal_caption(tuple(tokens[i] for i in inside), budget):
            for tree in _command(tokens[:start], parse):
                host = start - 1
                if tree[host].role not in NOMINAL_ROLES:
                    continue
                child = inside[_root(title)]
                links = {**dict(enumerate(tree)), **_map(title, inside)}
                links[child] = replace(links[child], role='apposition', head=host, scope='title',
                                       rule='REF.TITLE' if marks else 'REF.BARE.TITLE')
                for mark in marks:
                    links[mark] = Link('punctuation', tokens[mark].surface, child, 'QUOTE.PUNCT')
                yield tuple(links[i] for i in range(len(tokens)))
    if not quote_titles.spans(tokens):
        yield from _command(tokens, parse)


def _clause(tokens, parse):
    if next(contrastive_regions.joins(tokens), None) is not None:
        yield from contrastive_regions.attributes(tokens, parse)
        yield from contrastive_regions.predicates(tokens, parse)
    else:
        yield from parse(tokens)


def _relative(matrix, child, marker, comma):
    outer = len(matrix)
    for host, link in enumerate(matrix):
        if link.role not in NOMINAL_ROLES | {'apposition'}:
            continue
        links = {**dict(enumerate(matrix)), **_map(child, range(marker, marker + len(child)))}
        pivot = marker + _root(child)
        links[pivot] = replace(links[pivot], role='clause_relative', head=host, rule='CL.REL')
        links[marker] = replace(links[marker], rule='CL.NOMREF', antecedent=host)
        if comma:
            links[outer] = Link('punctuation', ',', pivot, 'CL.PUNCT')
        yield tuple(links[j] for j in range(len(links))), pivot


def _assemble(tokens, parse, budget):
    q = [i for i, token in enumerate(tokens[1:], 1)
         if any(tag.POS == 'ADVB' and 'Ques' in tag for _, tag in known_forms(token.surface))]
    if not q:
        yield from _matrix(tokens, parse, budget)
        return
    marker = q[0]
    comma = tokens[marker - 1].surface == ','
    matrix = tuple(_matrix(tokens[:marker - int(comma)], parse, budget))
    if not matrix:
        return
    boundaries = [b for b in clauses._boundaries(tuple(clauses._key(t.surface) for t in tokens))
                  if b.relation == 'advcl' and b.start > marker]
    for boundary in boundaries or (None,):
        stop = boundary.start if boundary else len(tokens)
        right = tokens[marker:stop]
        children = tuple(tree for tree in _clause(right, parse) if tree[0].role == 'adverb')
        if not children:
            continue
        causes = tuple(_clause(tokens[boundary.stop:], parse)) if boundary else ()
        for tree in matrix:
            for child in children:
                for combined, pivot in _relative(tree, child, marker, comma):
                    if not boundary:
                        yield combined
                        continue
                    for dependent in causes:
                        root = boundary.stop + _root(dependent)
                        joined = dict(enumerate(combined))
                        joined.update(_map(dependent, range(boundary.stop, len(tokens))))
                        joined[boundary.marker] = Link('clause_marker', tokens[boundary.marker].surface.casefold(),
                                                       root, 'CL.MARK', scope=clauses._scope(boundary))
                        for j in range(boundary.marker + 1, boundary.stop):
                            joined[j] = Link('fixed', tokens[j].surface.casefold(), boundary.marker, 'CL.FIXED')
                        if boundary.start < boundary.marker:
                            joined[boundary.start] = Link('punctuation', ',', root, 'CL.PUNCT')
                        for parent in (pivot, _root(tree)):
                            joined[root] = replace(joined[root], role='clause_adverbial', rule='CL.ADV',
                                                   scope=clauses._scope(boundary), head=parent)
                            yield tuple(joined[j] for j in range(len(tokens)))


def trees(tokens, parse, budget):
    if not tokens or tokens[0].surface.rstrip('.').casefold() not in _abbreviations():
        return
    found = set()
    for tree in _assemble(tokens, parse, budget):
        if tree not in found:
            found.add(tree)
            if len(found) > budget:
                raise AnalysisBudgetExceeded('REFERENCE_DIRECTIVE_BUDGET')
            yield tree


def confirmation(tokens, tree, index, text):
    link = tree[index]
    if link.rule in {'ABBR.IMP', 'ABBR.BARE'}:
        end = index + 2 if index + 1 < len(tree) and tree[index + 1].rule == 'ABBR.DOT' else index + 1
        short = _span_label(tokens, index, end).replace(' .', '.')
        return Probe(f'Какое сокращение здесь означает указание «{link.lemma}»?', (short,), text)
    if link.rule == 'REF.BARE.TITLE':
        members = {index}
        for j in range(index + 1, len(tree)):
            if tree[j].head not in members or tree[j].role != 'genitive_modifier':
                break
            members.add(j)
        phrase = _span_label(tokens, index, max(members) + 1)
        return Probe('Какие слова вместе образуют название?', (phrase,), text)
