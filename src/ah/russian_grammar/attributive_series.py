from dataclasses import dataclass
from functools import lru_cache
from itertools import product

from .lexical_parts import attested
from .morphology import Morphology, _common, from_tag
from .nominal_chart import agrees
from .nominal_groups import _markers
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .probe import Probe
from .rules import dictionary, known_forms
from .utterances import _map


@lru_cache(maxsize=2048)
def _marked(surface):
    return any(tag.POS == 'ADJF' and 'Abbr' in tag for _, tag in attested(surface))


@lru_cache(maxsize=2048)
def _adjective_prefix(surface):
    if (len(surface) < 2 or not surface.isalpha() or not surface.islower()
            or surface[-1] not in 'бвгджзйклмнпрстфхцчшщ'):
        return False
    for word in dictionary().dictionary.words.iterkeys(surface):
        if word != surface and any(tag.POS == 'ADJF' and 'Abbr' not in tag for _, tag in attested(word)):
            return True
    return False


@dataclass(frozen=True)
class Member:
    index: int
    dot: bool
    marked: bool
    lemma: str
    rule: str
    morphology: Morphology | None


def _member(tokens, index, noun):
    surface = tokens[index].surface
    dot = (index + 1 < len(tokens) and tokens[index + 1].surface == '.'
           and tokens[index].end == tokens[index + 1].start)
    full = known_forms(surface)
    options = {}
    if not dot:
        forms = full
        if not full and any(c in '-‐‑' for c in surface):
            forms = [(p.normal_form, p.tag) for p in dictionary().parse(surface)]
        for lemma, tag in forms:
            if tag.POS == 'ADJF' and 'Abbr' not in tag and agrees(tag, noun):
                options.setdefault(lemma, []).append(from_tag(tag))
        if options:
            return tuple(Member(index, False, False, lemma, 'A1' if full else 'ATTR.SERIES.PREDICTED',
                                _common(forms)) for lemma, forms in options.items())
    marked = _marked(surface)
    possible = dot or not any(tag.POS in ('CONJ', 'PREP', 'VERB', 'INFN') for _, tag in full)
    if marked or possible and _adjective_prefix(surface):
        return (Member(index, dot, marked, surface, 'ATTR.SERIES.ABBR', None),)
    return ()


def _regions(tokens, start, noun, noun_tag):
    slots = []
    separators = []
    cursor = start
    while cursor < noun:
        mark = ()
        comma = None
        if slots:
            if tokens[cursor].surface == ',':
                comma = cursor
                cursor += 1
            mark = next(_markers(tokens, cursor), ())
            cursor += len(mark)
            if cursor >= noun:
                return
        members = _member(tokens, cursor, noun_tag)
        if not members:
            return
        separators.append((comma, mark))
        slots.append(members)
        cursor += 1 + int(members[0].dot)
    if cursor != noun or len(slots) < 2:
        return
    strong = [slot[0].marked or slot[0].dot for slot in slots]
    if not any(strong):
        return
    if not any(comma is not None or mark for comma, mark in separators) and not (
            all(s[0].rule == 'ATTR.SERIES.ABBR' for s in slots) and any(strong)):
        return
    for members in product(*slots):
        first = members[0].index
        links = {}
        for member, (comma, mark) in zip(members, separators):
            i = member.index
            role = 'attribute' if i == first else 'attribute_conjunct'
            links[i] = Link(role, member.lemma, noun if i == first else first,
                            member.rule, morphology=member.morphology)
            if comma is not None:
                links[comma] = Link('punctuation', ',', i, 'A.COORD')
            if member.dot:
                links[i + 1] = Link('punctuation', '.', i, 'ABBR.PUNCT')
            for j in mark:
                links[j] = Link('coordinator' if j == mark[0] else 'coordinator_part',
                                tokens[j].surface.casefold(), i if j == mark[0] else mark[0], 'A.COORD')
        yield links


def trees(tokens, parse, budget):
    if not any(_marked(t.surface) or t.surface == '.' for t in tokens):
        return
    groups = {}
    for i, token in enumerate(tokens):
        for lemma, tag in known_forms(token.surface):
            if tag.POS != 'NOUN' or tag.case is None:
                continue
            for start in range(i - 2, -1, -1):
                if tokens[start].surface in {',', '.'}:
                    continue
                for links in _regions(tokens, start, i, tag):
                    key = start, i, tuple(links.items())
                    groups.setdefault(key, set()).add((lemma, str(tag.case)))
                    if len(groups) > budget:
                        raise AnalysisBudgetExceeded('ATTRIBUTE_SERIES_BUDGET')
                if not (_member(tokens, start, tag) or next(_markers(tokens, start), ())):
                    break
    if not groups:
        return
    pending = [(0, {}, {})]
    seen = set()
    while pending:
        start, inserted, requirements = pending.pop()
        if inserted:
            kept = tuple(i for i in range(len(tokens)) if i not in inserted)
            for tree in parse(tuple(tokens[i] for i in kept)):
                links = _map(tree, kept)
                if any((links[i].lemma, links[i].case or getattr(links[i].morphology, 'case', None))
                       not in valid for i, valid in requirements.items()):
                    continue
                links.update(inserted)
                result = tuple(links[i] for i in range(len(tokens)))
                if result not in seen:
                    seen.add(result)
                    if len(seen) > budget:
                        raise AnalysisBudgetExceeded('ATTRIBUTE_SERIES_BUDGET')
                    yield result
        for (first, noun, links), valid in groups.items():
            if first >= start:
                pending.append((noun + 1, {**inserted, **dict(links)}, {**requirements, noun: valid}))
                if len(pending) > budget:
                    raise AnalysisBudgetExceeded('ATTRIBUTE_SERIES_BUDGET')


def _series(tokens, tree, i, text):
    first = tree[i]
    if first.role != 'attribute':
        return None
    members = [i, *(j for j, item in enumerate(tree) if item.role == 'attribute_conjunct' and item.head == i)]
    if not any(tree[j].rule.startswith('ATTR.SERIES.') for j in members):
        return None
    last = members[-1]
    stop = last + 1 + int(last + 1 < len(tokens) and tree[last + 1].rule == 'ABBR.PUNCT')
    return first.head, text[tokens[i].start:tokens[stop - 1].end]


def _question(tokens, head):
    return f'Какие слова перечисляют однородные определения к слову «{_span_label(tokens, head)}»?'


def confirmation(tokens, tree, i, text):
    series = _series(tokens, tree, i, text)
    if series:
        head, phrase = series
        return Probe(_question(tokens, head), (phrase,), text[tokens[i].start:tokens[head].end])
    return None


def partitions(analyses, tokens, text):
    if not any(link.rule.startswith('ATTR.SERIES.') for tree in analyses for link in tree):
        return
    groups = []
    for tree in analyses:
        regions = {}
        for i, link in enumerate(tree):
            if link.role != 'attribute':
                continue
            series = _series(tokens, tree, i, text)
            if series:
                head, phrase = series
                regions[head] = (i, phrase)
        groups.append(regions)
    for head in groups[0]:
        if any(head not in group for group in groups):
            continue
        labels = [group[head][1] for group in groups]
        options = tuple(dict.fromkeys(labels))
        if len(options) > 1:
            first = min(group[head][0] for group in groups)
            yield Probe(_question(tokens, head), options, text[tokens[first].start:tokens[head].end]), labels
