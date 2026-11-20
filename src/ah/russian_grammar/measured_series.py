from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files

from .determiners import SCOPES
from .homogeneous import _restore
from .modifiers import _particles
from .morphology import Morphology, ROLE_CASE
from .nominal_groups import _agree, _markers, _members
from .numerals import Numeric, expressions
from .participle_connectives import relations
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .probe import Probe
from .quantity_groups import _surfaces
from .rules import dictionary, known_forms


@cache
def _symbols():
    rows = files(__package__).joinpath('lexicon/unit-symbols.tsv').read_text(encoding='utf8').splitlines()
    return dict(row.split('\t') for row in rows)


@dataclass(frozen=True)
class Member:
    head: int
    lemma: str
    case: str
    links: tuple
    expression: Numeric | None = None

    @property
    def measured(self):
        return self.expression is not None


@cache
def _prenominal_particles():
    data = files(__package__).joinpath('lexicon/adverbial-modifiers.tsv').read_text(encoding='utf8')
    return {row.split('\t')[1] for row in data.splitlines() if row.startswith('prenominal\t')}


def _members_with_determiners(tokens, start, case):
    yield from _members(tokens, start, None, case)
    if start >= len(tokens):
        return
    for lemma, determiner in known_forms(tokens[start].surface):
        if lemma not in SCOPES or determiner.POS != 'ADJF' or SCOPES[lemma] == 'negative':
            continue
        for noun, word, reading, attrs in _members(tokens, start + 1, None, case):
            if any(l == word and tag.POS == 'NOUN' and tag.case == reading and _agree(determiner, tag)
                   for l, tag in known_forms(tokens[noun].surface)):
                yield noun, word, reading, ((start, Link('attribute', lemma, noun, 'NP.DET', scope=SCOPES[lemma])), *attrs)


def _heads(tokens, start, focused):
    if start >= len(tokens):
        return
    if focused:
        focus = tokens[start].surface.casefold()
        if focus not in _prenominal_particles() or _particles((focus, '')):
            return
        if not any(lemma == focus and tag.POS == 'PRCL' for lemma, tag in known_forms(focus)):
            return
        if any(lemma == focus and tag.POS in ('CONJ', 'PREP') for lemma, tag in known_forms(focus)):
            return
        for case in ('nomn', 'accs'):
            for noun, lemma, _, attrs in _members_with_determiners(tokens, start + 1, case):
                particle = Link('particle', focus, noun, 'F.NP', scope='focus')
                yield Member(noun, lemma, case, ((start, particle), *attrs))
        return
    bound = {'до': 'upper_bound', 'от': 'lower_bound'}.get(tokens[start].surface.casefold())
    first = start + int(bool(bound))
    for expr in expressions(tokens, first):
        if expr.end >= len(tokens) or expr.kind not in ('cardinal', 'fraction'):
            continue
        noun = expr.end
        word = _symbols().get(tokens[noun].surface)
        if not word:
            continue
        for case in ('nomn', 'accs'):
            parts = expr.parts_for('gent' if bound else case)
            if not parts:
                continue
            numeral = Link('numeral', parts[0][0], noun, 'NUM.UNIT', morphology=parts[0][1],
                           quantity=expr.value, quantity_kind=expr.kind, quantity_modifier=bound)
            links = [(first, numeral)]
            links.extend((i, Link('numeral_part', lemma, first, 'NUM.PART', morphology=morph))
                         for i, (lemma, morph) in enumerate(parts[1:], first + 1))
            if bound:
                links.append((start, Link('quantity_modifier', tokens[start].surface.casefold(), noun, 'NUM.BOUND')))
            yield Member(noun, word, case, tuple(links), expr)


def _separators(tokens, start):
    comma = start < len(tokens) and tokens[start].surface == ','
    i = start + int(comma)
    for marker in ((), *_markers(tokens, i)):
        yield i + len(marker), comma, marker


def _separator_links(tokens, start, comma, marker, head):
    if comma:
        yield start, Link('punctuation', ',', head, 'N.SERIES.BOUND')
    scope = 'alternative' if 'alternative' in relations(' '.join(tokens[i].surface.casefold() for i in marker)) else None
    for i in marker:
        yield i, Link('coordinator' if i == marker[0] else 'coordinator_part', tokens[i].surface.casefold(),
                      head if i == marker[0] else marker[0], 'P.COORD', scope=scope if i == marker[0] else None)


def _nominal_series(tokens, first, heads, dependents, budget):
    pending = [(first.head + 1, (first.head,), None, first.links, 1)]
    examined = 0
    while pending:
        end, edge, list_head, links, size = pending.pop()
        examined += 1
        if examined > budget * 8:
            raise AnalysisBudgetExceeded('NOMINAL_SERIES_BUDGET')
        if size > 1 or first.measured:
            yield end, links
        for start, comma, marker in _separators(tokens, end):
            for member in heads(start, not first.measured):
                if member.case != first.case or member.measured != first.measured:
                    continue
                if not marker and not comma:
                    if not member.measured or len(edge) < 2:
                        continue
                    if any(link.quantity_modifier == 'upper_bound' for _, link in member.links) and any(
                            link.quantity_modifier == 'lower_bound' for _, link in links):
                        continue
                elif not member.measured and not marker:
                    continue
                conjunct = Link('nominal_conjunct', member.lemma, first.head, 'N.COORD', member.case)
                additions = ((member.head, conjunct), *_separator_links(tokens, end, comma, marker, member.head))
                pending.append((member.head + 1, (member.head,), None, (*links, *member.links, *additions), size + 1))
            for case in (('gent',) if first.measured else ('gent', 'ablt')):
                for noun, lemma, _, attrs in dependents(start, case):
                    if list_head is not None and case == 'gent' and (marker or comma or first.measured):
                        child = Link('nominal_conjunct', lemma, list_head, 'N.COORD', case)
                        extra = (*_separator_links(tokens, end, comma, marker, noun), (noun, child), *attrs)
                        pending.append((noun + 1, (*edge[:1], noun), list_head, (*links, *extra), size))
                    if marker or comma:
                        continue
                    for j, host in enumerate(edge):
                        role = 'genitive_modifier' if case == 'gent' else 'oblique'
                        child = Link(role, lemma, host, 'N.GEN' if case == 'gent' else 'N.CASE', case)
                        pending.append((noun + 1, (*edge[:j + 1], noun), noun if case == 'gent' else None,
                                        (*links, (noun, child), *attrs), size))


def _projections(member, token):
    if not member.measured:
        yield token.surface, member.lemma
        return
    for word in dictionary().parse(member.lemma):
        if word.normal_form == member.lemma and word.tag.POS == 'NOUN':
            for spelling in word.lexeme:
                if not member.expression.compatible(member.case, spelling.tag):
                    continue
                proxy = replace(token, surface=spelling.word)
                for form, subject_only in _surfaces(proxy, member.lemma, spelling.tag, member.expression, member.case):
                    yield form, form if subject_only else member.lemma
            break


def trees(tokens, parse, budget):
    symbolic = any(t.surface in _symbols() for t in tokens)
    focus_sites = {i for i, t in enumerate(tokens) if t.surface.casefold() in _prenominal_particles()}
    if not symbolic and len(focus_sites) < 2:
        return

    @cache
    def heads(start, focused):
        return tuple(dict.fromkeys(_heads(tokens, start, focused)))

    @cache
    def dependents(start, case):
        return tuple(dict.fromkeys(_members_with_determiners(tokens, start, case)))

    @cache
    def bases(kept, head, form):
        words = tuple(replace(tokens[j], surface=form) if j == head else tokens[j] for j in kept)
        return tuple(parse(words))

    anchors = {i for i, t in enumerate(tokens) if i and t.surface in _symbols()
               and any(e.end == i for e in expressions(tokens, i - 1))}
    emitted = set()
    for start in range(len(tokens)):
        for focused in (False, True):
            if not focused and not symbolic:
                continue
            if focused and (start not in focus_sites or start == max(focus_sites)):
                continue
            for first in heads(start, focused):
                for end, extras in _nominal_series(tokens, first, heads, dependents, budget):
                    if end < len(tokens) and any(tag.POS in ('NOUN', 'ADJF', 'PRCL') for _, tag in known_forms(tokens[end].surface)):
                        continue
                    kept = (*range(start), first.head, *range(end, len(tokens)))
                    if first.measured and any(i != first.head and i in anchors for i in kept):
                        continue
                    for form, proxy_lemma in dict.fromkeys(_projections(first, tokens[first.head])):
                        for tree in bases(kept, first.head, form):
                            anchor = tree[start]
                            if anchor.role not in {'subject', 'object'} or anchor.lemma != proxy_lemma:
                                continue
                            if first.case != (anchor.case or ROLE_CASE[anchor.role]):
                                continue
                            links = _restore(tree, kept, len(tokens))
                            if first.measured:
                                links[first.head] = replace(links[first.head], lemma=first.lemma, morphology=Morphology(pos='NOUN'),
                                                            case=first.case, rule='NUM.UNIT.ARG')
                            for i, link in extras:
                                links[i] = link
                            for option in _modal_scopes(links):
                                if option not in emitted:
                                    emitted.add(option)
                                    yield option


def _modal_scopes(links):
    yield tuple(links)
    for i, adverb in enumerate(links):
        if adverb.role != 'adverb' or adverb.head is None:
            continue
        verb = links[adverb.head]
        if verb.role == 'infinitive' and verb.scope == 'modal' and verb.head is not None:
            option = list(links)
            option[i] = replace(adverb, head=verb.head)
            yield tuple(option)


def partitions(analyses, tokens, text):
    if not any(link.rule == 'N.CASE' for tree in analyses for link in tree):
        return
    for i in range(len(tokens)):
        links = [tree[i] for tree in analyses]
        hosts = {link.head for link in links}
        if len(hosts) < 2 or None in hosts:
            continue
        focus = _span_label(tokens, i)
        if all(link.rule == 'N.CASE' for link in links):
            question = f'Какое слово в этом фрагменте поясняет дополнение «{focus}» в творительном падеже?'
        elif all(link.role == 'adverb' for link in links) and len(hosts) == 2:
            modal = next((j for j in hosts if analyses[0][j].scope == 'modal' and analyses[0][j].head in hosts), None)
            if modal is None:
                continue
            operator = analyses[0][modal].head
            action, relation = _span_label(tokens, modal), _span_label(tokens, operator)
            question = (f'Что уточняет «{focus}» — саму модальность («{relation}») '
                        f'или действие в её области («{action}»)?')
        else:
            continue
        labels = {j: _span_label(tokens, j) for j in sorted(hosts)}
        yield Probe(question, tuple(labels.values()), text), [labels[link.head] for link in links]


def confirmation(tokens, tree, i, text):
    if (not tokens[i].surface.isalpha() or tokens[i].surface not in _symbols()
            or not any(link.rule == 'NUM.UNIT' and link.head == i for link in tree)):
        return None
    unit = tokens[i].surface
    if known_forms(unit) or len(unit) == 1:
        focus = _span_label(tokens, i)
        return Probe(f'Какое обозначение здесь употреблено в значении «{tree[i].lemma}»?', (focus,), text)
    return None
