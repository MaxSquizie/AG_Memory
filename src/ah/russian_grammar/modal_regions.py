from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from itertools import product

from .homogeneous import _restore
from .morphology import from_tag
from .nominal_groups import _agree, _prepositions
from .parser import AnalysisBudgetExceeded, Link
from .participle_connectives import markers, relations
from .prepositions import GOVERNMENT
from .rules import known_forms, readings


@cache
def _lexicon():
    phrases = []
    particles = set()
    data = files(__package__).joinpath('lexicon/adverbial-modifiers.tsv')
    for line in data.read_text(encoding='utf8').splitlines():
        kind, surface = line.split('\t')
        if kind == 'adverbial':
            phrases.append(tuple(surface.split()))
        elif kind == 'postpositive':
            particles.add(surface)
    return tuple(phrases), particles


@dataclass(frozen=True)
class Phrase:
    start: int
    end: int
    noun: int
    prep: str
    lemma: str
    case: str
    links: tuple


def _phrases(tokens, words, start, particles):
    for first, prep in _prepositions(tokens, start):
        if not GOVERNMENT.get(prep):
            continue
        qualifiers = []
        fixed = [(j, Link('prep_part', words[j], start, 'P1')) for j in range(start + 1, first)]
        for j in range(first, len(tokens)):
            forms = known_forms(words[j])
            if j > first and qualifiers and j - 1 == qualifiers[-1][0] and words[j] in particles:
                fixed.append((j, Link('particle', words[j], j - 1, 'F.NP')))
                continue
            governed = {(r.lemma, r.case) for r in readings(words[j], prep) if r.role == 'governed'}
            for lemma, noun in forms:
                if noun.POS not in {'NOUN', 'NPRO'} or (lemma, noun.case) not in governed:
                    continue
                attrs = [tuple((i, Link('attribute', adj, j, 'A1', morphology=from_tag(tag)))
                               for adj, tag in items if _agree(tag, noun)) for i, items in qualifiers]
                for chosen in product(*attrs):
                    yield Phrase(start, j + 1, j, prep, lemma, noun.case, (*fixed, *chosen))
            attributes = [(adj, tag) for adj, tag in forms if tag.POS == 'ADJF']
            if not attributes:
                break
            qualifiers.append((j, attributes))


def _boundaries(groups, words):
    boundaries = {}
    for left, right in zip(groups, groups[1:]):
        if left.prep == right.prep and left.case == right.case:
            gap = words[left.end:right.start]
            if gap in ((), (',',)):
                boundaries[right.start] = (left, bool(gap))
    return boundaries


def _groupings(boundaries, budget):
    optional = [i for i, (_, marked) in boundaries.items() if not marked]
    if 2 ** len(optional) > budget:
        raise AnalysisBudgetExceeded('MODAL_GROUP_BUDGET')
    for choices in product((False, True), repeat=len(optional)):
        included = {i for i, selected in zip(optional, choices) if selected}
        coordinated = {}
        for i, (left, marked) in boundaries.items():
            if marked or i in included:
                coordinated[i] = coordinated.get(left.start, left.noun)
        yield coordinated


def _attach_groups(groups, coordinated, restored, hosts, words):
    links = list(restored)
    free = []
    for group in groups:
        for j, link in group.links:
            links[j] = link
        if group.start in coordinated:
            marked = words[group.start - 1] == ','
            if marked:
                links[group.start - 1] = Link('punctuation', ',', group.noun, 'P.COORD')
            rule = 'P.COORD' if marked else 'P.COORD.UNMARKED'
            links[group.noun] = Link('nominal_conjunct', group.lemma, coordinated[group.start], rule, group.case)
            links[group.start] = Link('case', group.prep, group.noun, 'P1')
        else:
            links[group.noun] = Link('governed', group.lemma, group.start, 'P1', group.case)
            free.append(group)
    for heads in product(hosts, repeat=len(free)):
        for group, host in zip(free, heads):
            links[group.start] = Link('preposition', group.prep, host, 'P2')
        yield tuple(links)


def trees(tokens, kernel, budget):
    infinitives = {j for j, token in enumerate(tokens)
                   if any(tag.POS == 'INFN' for _, tag in known_forms(token.surface))}
    if not infinitives or not any(any(tag.POS in {'ADJS', 'VERB'} for _, tag in known_forms(t.surface))
                                  for t in tokens):
        return
    words = tuple(t.surface.casefold() for t in tokens)
    adverbials, particles = _lexicon()
    opening = next((span for span in markers(tokens, 0)
                    if set(relations(' '.join(words[j] for j in span))) <= {'addition', 'contrast'}
                    and relations(' '.join(words[j] for j in span))), ())
    fixed = {}
    for index in infinitives:
        for phrase in adverbials:
            start = index - len(phrase)
            if start >= 0 and words[start:index] == phrase:
                fixed[start] = Link('adverb', words[start], index, 'ADV.FIXED')
                for j in range(start + 1, index):
                    fixed[j] = Link('fixed', words[j], start, 'ADV.FIXED')
    pending = [(len(opening), (), ())]
    produced = 0
    while pending:
        i, kept, groups = pending.pop()
        if i < len(tokens):
            if i in fixed:
                pending.append((i + 1, kept, groups))
                continue
            found = tuple(dict.fromkeys(_phrases(tokens, words, i, particles)))
            if found:
                pending.extend((g.end, kept, (*groups, g)) for g in found)
            else:
                pending.append((i + 1, (*kept, i), groups))
            if len(pending) > budget:
                raise AnalysisBudgetExceeded('MODAL_GROUP_BUDGET')
            continue
        if not (groups or opening or fixed):
            continue
        boundaries = _boundaries(groups, words)
        commas = {start - 1 for start, (_, marked) in boundaries.items() if marked}
        indices = tuple(j for j in kept if j not in commas)
        for tree in kernel(tuple(tokens[j] for j in indices)):
            restored = _restore(tree, indices, len(tokens))
            root = next((j for j in indices if restored[j].role == 'predicate' and restored[j].head is None), None)
            embedded = [j for j in indices if restored[j].role == 'infinitive' and restored[j].scope == 'modal'
                        and restored[j].head == root]
            if root is None or not embedded or any(link.head not in embedded for link in fixed.values()
                                                   if link.role == 'adverb'):
                continue
            for j in opening:
                restored[j] = Link('coordinator' if j == opening[0] else 'coordinator_part',
                                   words[j], root if j == opening[0] else opening[0], 'C.OPEN')
            for j, link in fixed.items():
                restored[j] = link
            for coordinated in _groupings(boundaries, budget):
                for variant in _attach_groups(groups, coordinated, restored, (root, *embedded), words):
                    produced += 1
                    if produced > budget:
                        raise AnalysisBudgetExceeded('MODAL_GROUP_BUDGET')
                    yield variant
