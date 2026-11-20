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
        else:
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
        coordinated = {}
        for left, right in zip(groups, groups[1:]):
            if left.prep == right.prep and left.case == right.case and words[left.end:right.start] == (',',):
                coordinated[right.start] = coordinated.get(left.start, left.noun)
        commas = {g.start - 1 for g in groups if g.start in coordinated}
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
            choices = []
            for g in groups:
                for j, link in g.links:
                    restored[j] = link
                if g.start in coordinated:
                    restored[g.start - 1] = Link('punctuation', ',', g.noun, 'P.COORD')
                    restored[g.noun] = Link('nominal_conjunct', g.lemma, coordinated[g.start], 'P.COORD', g.case)
                    restored[g.start] = Link('case', g.prep, g.noun, 'P1')
                else:
                    restored[g.noun] = Link('governed', g.lemma, g.start, 'P1', g.case)
                    choices.append((g, (root, *embedded)))
            for heads in product(*(heads for _, heads in choices)):
                for (g, _), host in zip(choices, heads):
                    restored[g.start] = Link('preposition', g.prep, host, 'P2')
                produced += 1
                if produced > budget:
                    raise AnalysisBudgetExceeded('MODAL_GROUP_BUDGET')
                yield tuple(restored)
