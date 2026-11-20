from dataclasses import dataclass, replace
from functools import cache, lru_cache

from .morphology import from_tag
from .nominal_groups import _markers, _members, _prepositions
from .prepositions import GOVERNMENT
from .rules import dictionary, known_forms


@dataclass(frozen=True)
class Phrase:
    end: int
    head: int
    case: str
    entries: tuple


@lru_cache(maxsize=1024)
def opaque_cases(surface):
    if not surface[:1].isupper() or not all(w.isalpha() for w in surface.split('-')) or known_forms(surface):
        return frozenset()
    return frozenset(p.tag.case for p in dictionary().parse(surface) if p.tag.POS == 'NOUN' and p.tag.case)


def trees(tokens, *, budget):
    from .parser import AnalysisBudgetExceeded, Link

    if not any(opaque_cases(t.surface) for t in tokens):
        return
    forms = [known_forms(t.surface) for t in tokens]
    finite = [i for i, variants in enumerate(forms) if any(t.POS == 'VERB' and t.mood == 'indc' for _, t in variants)]
    if len(finite) != 1:
        return
    root, = finite
    size = len(tokens)
    seen = set()

    @cache
    def nuclei(i, case):
        if i >= size or i == root:
            return ()
        candidates = []
        for head, lemma, _, attrs in _members(tokens, i, None, case):
            candidates.append(Phrase(head + 1, head, case, (*attrs, (head, Link('nominal', lemma, None, 'N1', case)))))
        for lemma, tag in forms[i]:
            if tag.POS == 'ADJF' and tag.case == case:
                link = Link('nominal', lemma, None, 'ADJ.SUBSTANTIVE', case, morphology=from_tag(tag))
                candidates.append(Phrase(i + 1, i, case, ((i, link),)))
        opaque = opaque_cases(tokens[i].surface)
        if case in opaque:
            l = Link('nominal', tokens[i].surface, None, 'OPAQUE.NAME', case)
            candidates.append(Phrase(i + 1, i, case, ((i, l),)))
        if opaque and i + 1 < size:
            for lemma, tag in forms[i + 1]:
                if not tokens[i + 1].surface[:1].isupper() or tag.case != case or not {'Name', 'Surn', 'Patr'} & tag.grammemes:
                    continue
                initial = Link('nominal', tokens[i].surface, None, 'OPAQUE.NAME', case)
                tail = Link('name_part', lemma, i, 'NAME', case, morphology=from_tag(tag))
                candidates.append(Phrase(i + 2, i, case, ((i, initial), (i + 1, tail))))
        return tuple(dict.fromkeys(candidates))

    def attach(group, head, role):
        return {k: replace(l, role=role, head=head) if k == group.head else l for k, l in group.entries}

    @cache
    def with_genitive(i, case):
        result = list(nuclei(i, case))
        for phrase in nuclei(i, case):
            for child in nuclei(phrase.end, 'gent'):
                links = dict(phrase.entries) | attach(child, phrase.head, 'genitive_modifier')
                result.append(replace(phrase, end=child.end, entries=tuple(links.items())))
        return tuple(result)

    @cache
    def phrases(i, case):
        result = list(with_genitive(i, case))
        for phrase in tuple(result):
            end = phrase.end
            if end < size and opaque_cases(tokens[end].surface):
                for name in nuclei(end, case):
                    links = dict(phrase.entries) | attach(name, phrase.head, 'apposition')
                    result.append(replace(phrase, end=name.end, entries=tuple(links.items())))
            if end >= size or tokens[end].surface != ',':
                continue
            for app in with_genitive(end + 1, case):
                links = dict(phrase.entries) | attach(app, phrase.head, 'apposition')
                links[end] = Link('punctuation', ',', app.head, 'APP.PUNCT')
                result.append(replace(phrase, end=app.end, entries=tuple(links.items())))
                for marker in _markers(tokens, app.end):
                    for nxt in with_genitive(marker[-1] + 1, case):
                        extended = links | attach(nxt, app.head, 'nominal_conjunct')
                        for j in marker:
                            extended[j] = Link('coordinator' if j == marker[0] else 'coordinator_part',
                                               tokens[j].surface.casefold(), nxt.head if j == marker[0] else marker[0], 'P.COORD')
                        result.append(replace(phrase, end=nxt.end, entries=tuple(extended.items())))
        return tuple(result)

    def agrees(subject, verb):
        link = dict(subject.entries)[subject.head]
        if link.rule.startswith('OPAQUE.'):
            return True
        return any(tag.case == 'nomn' and tag.number == verb.number
                   and (not verb.gender or tag.number != 'sing' or not tag.gender or tag.gender == verb.gender)
                   and (verb.person in (None, tag.person or '3per'))
                   for lemma, tag in forms[subject.head] if lemma == link.lemma)

    for verb, tag in forms[root]:
        if tag.POS != 'VERB' or tag.mood != 'indc' or tag.transitivity != 'tran':
            continue
        pending = [(0, None, None, None, {root: Link('predicate', verb, None, 'V1', morphology=from_tag(tag))})]
        attempts = 0
        while pending:
            pos, actor, obj, last, links = pending.pop()
            attempts += 1
            if attempts > budget * max(1, size):
                raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
            if pos == size:
                if actor is not None and obj is not None and any(l.rule.startswith('OPAQUE.') for l in links.values()):
                    tree = tuple(links[i] for i in range(size))
                    if tree not in seen:
                        seen.add(tree)
                        yield tree
                continue
            if pos == root:
                pending.append((pos + 1, actor, obj, None, links))
                continue
            if actor is None:
                for noun in phrases(pos, 'nomn'):
                    if agrees(noun, tag):
                        pending.append((noun.end, noun.head, obj, noun.head, links | attach(noun, root, 'subject')))
            if obj is None:
                for noun in phrases(pos, 'accs'):
                    pending.append((noun.end, actor, noun.head, noun.head, links | attach(noun, root, 'object')))
            for first, prep in _prepositions(tokens, pos):
                for case in sorted(GOVERNMENT.get(prep, ())):
                    for noun in phrases(first, case):
                        interior = attach(noun, pos, 'governed')
                        for j in range(pos + 1, first):
                            interior[j] = Link('prep_part', tokens[j].surface.casefold(), pos, 'P1')
                        for host in dict.fromkeys((root, last)):
                            if host is not None:
                                pp = {pos: Link('preposition', prep, host, 'P2')}
                                pending.append((noun.end, actor, obj, noun.head, links | pp | interior))
