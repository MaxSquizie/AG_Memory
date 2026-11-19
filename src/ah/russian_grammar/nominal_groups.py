from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files
from itertools import product

from .prepositions import FORMS, PREFIXES
from .rules import Reading, known_forms, name_continuations, name_type, readings


POSSESSIVES = frozenset(('мой', 'наш', 'твой', 'ваш', 'свой', 'его', 'её', 'их', 'ихний'))


@cache
def _coordinators():
    table = files(__package__).joinpath('lexicon', 'nominal-connectives.tsv')
    markers = {}
    for row in table.read_text(encoding='utf-8').splitlines():
        form, relation, _ = row.split('\t')
        if relation == 'conj':
            words = tuple(form.split())
            markers.setdefault(words[0], []).append(words)
    return markers


def _markers(tokens, start):
    if start < len(tokens):
        for form in _coordinators().get(tokens[start].surface.casefold(), ()):
            stop = start + len(form)
            if tuple(token.surface.casefold() for token in tokens[start:stop]) == form:
                yield tuple(range(start, stop))


@dataclass(frozen=True)
class Group:
    start: int
    end: int
    preposition: str | None
    noun: int
    lemma: str
    case: str
    extra: tuple


def _prepositions(tokens, start):
    phrase = ''
    for i in range(start, len(tokens)):
        word = tokens[i].surface.lower()
        phrase = (phrase + ' ' + word).lstrip()
        if phrase in FORMS:
            yield i + 1, FORMS[phrase]
        elif i == start:
            for lemma, tag in known_forms(word):
                if tag.POS == 'PREP':
                    yield i + 1, lemma
        if phrase not in PREFIXES:
            break


def _agree(adj, noun):
    case = {'loc2': 'loct', 'gen2': 'gent'}.get(noun.case, noun.case)
    return (adj.case == case and adj.number == noun.number
            and (noun.number == 'plur' or not noun.gender or noun.gender == adj.gender)
            and (not adj.animacy or not noun.animacy or noun.animacy == adj.animacy))


def _members(tokens, start, prep, case=None):
    from .parser import Link

    qualifiers = []
    for i in range(start, len(tokens)):
        forms = known_forms(tokens[i].surface)
        allowed = None
        if prep:
            allowed = {(r.lemma, r.case) for r in readings(tokens[i].surface, prep) if r.role == 'governed'}
        for lemma, noun in forms:
            if noun.POS not in ('NOUN', 'NPRO'):
                continue
            if qualifiers and noun.POS == 'NPRO':
                continue
            if case is not None and noun.case != case:
                continue
            if prep is None and 'Af-p' in noun:
                continue
            if allowed is not None and (lemma, noun.case) not in allowed and not (case is not None and noun.POS == 'NPRO' and noun.person == '3per'):
                continue
            choices = [tuple(dict.fromkeys(Link(role, adj, i, 'P.POSS' if role == 'possessive' else 'A1')
                                           for role, adj, tag in variants if _agree(tag, noun)))
                       for variants in qualifiers]
            for selected in product(*choices):
                yield i, lemma, noun.case, tuple(zip(range(start, i), selected))
        options = [('possessive' if lemma in POSSESSIVES else 'attribute', lemma, tag)
                   for lemma, tag in forms if tag.POS == 'ADJF' and ('Apro' not in tag or lemma in POSSESSIVES)]
        if not options:
            break
        qualifiers.append(options)


def _names(tokens, group):
    from .parser import Link

    noun = group.noun
    for lemma, tag in known_forms(tokens[noun].surface):
        kind = name_type(tag)
        if lemma != group.lemma or tag.case != group.case or tag.number != 'sing' or not kind:
            continue
        first = Reading(lemma, 'oblique', tag.case, tag.number, tag.gender, None, tag.animacy, False, kind)
        states = [(group, (first,))]
        while states:
            current, parts = states.pop()
            index = current.end
            if index < len(tokens):
                for part in name_continuations(tokens[index].surface, parts):
                    link = Link('name_part', part.lemma, noun, 'NAME', case=part.case)
                    expanded = replace(current, end=index + 1, extra=(*current.extra, (index, link)))
                    yield expanded
                    states.append((expanded, (*parts, part)))


def _groups(tokens, start, budget, *, bare_cases=()):
    from .parser import AnalysisBudgetExceeded, Link

    found = set()
    seeds = ((start, None, case) for case in sorted(bare_cases)) if bare_cases else (
        (first, prep, None) for first, prep in _prepositions(tokens, start))
    for first, prep, required_case in seeds:
        for noun, lemma, case, modifiers in _members(tokens, first, prep, required_case):
            initial = Group(start, noun + 1, prep, noun, lemma, case, modifiers)
            pending = [initial]
            if bare_cases:
                pending.extend(_names(tokens, initial))
            while pending:
                group = pending.pop()
                if group in found:
                    continue
                found.add(group)
                if len(found) > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
                if bare_cases or any(link.role in ('nominal_conjunct', 'possessive') for _, link in group.extra):
                    yield group
                end = group.end
                if end >= len(tokens):
                    continue
                comma = tokens[end].surface == ','
                next_word = end + int(comma)
                markers = list(_markers(tokens, next_word))
                if comma:
                    markers.append(())
                for marker in markers:
                    stop = next_word + len(marker)
                    for head, child, _, attrs in _members(tokens, stop, prep, case):
                        links = list(group.extra)
                        if comma:
                            links.append((end, Link('punctuation', ',', head, 'P.COORD')))
                        for i in marker:
                            parent = head if i == marker[0] else marker[0]
                            role = 'coordinator' if i == marker[0] else 'coordinator_part'
                            links.append((i, Link(role, tokens[i].surface.casefold(), parent, 'P.COORD')))
                        links.append((head, Link('nominal_conjunct', child, noun, 'P.COORD', case)))
                        pending.append(replace(group, end=head + 1, extra=(*links, *attrs)))
                        if bare_cases:
                            item = Group(stop, head + 1, prep, head, child, case, attrs)
                            for name in _names(tokens, item):
                                pending.append(replace(group, end=name.end, extra=(*links, *name.extra)))


def _restore(tree, kept, groups):
    links = {}
    for i, link in zip(kept, tree):
        indices = {field: kept[value] for field in ('head', 'controller', 'antecedent')
                   if (value := getattr(link, field, None)) is not None}
        links[i] = replace(link, **indices)
    choices = []
    for group in groups:
        head = links[group.noun]
        if (head.role != 'governed' or head.head != group.start or head.case != group.case
                or head.lemma != group.lemma or links[group.start].lemma != group.preposition):
            return
        links.update(group.extra)
        conjuncts = [i for i, link in group.extra if link.role == 'nominal_conjunct']
        if group.end in links and links[group.end].role == 'preposition' and links[group.end].head == group.noun and conjuncts:
            choices.append((group.end, (group.noun, conjuncts[-1])))
    for targets in product(*(options for _, options in choices)):
        for (i, _), target in zip(choices, targets):
            links[i] = replace(links[i], head=target)
        yield tuple(links[i] for i in range(len(links)))


def trees(tokens, local, *, budget=256):
    from .parser import AnalysisBudgetExceeded

    yield from local(tokens)
    if not any(token.surface.casefold() in _coordinators() or token.surface == ','
               or any(lemma in POSSESSIVES and tag.POS == 'ADJF' for lemma, tag in known_forms(token.surface))
               for token in tokens):
        return
    starts = [(i, tuple(_groups(tokens, i, budget))) for i in range(len(tokens))]
    starts = [(i, groups) for i, groups in starts if groups]

    @cache
    def reduced(kept):
        result = []
        for tree in local(tuple(tokens[i] for i in kept)):
            result.append(tree)
            if len(result) > budget:
                raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
        return tuple(result)

    count = 0
    pending = [(0, ())]
    while pending:
        index, picked = pending.pop()
        for j in range(index, len(starts)):
            pos, groups = starts[j]
            if picked and picked[-1].end > pos:
                continue
            for group in groups:
                selection = (*picked, group)
                count += 1
                if count > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
                hidden = {i for block in selection for i, _ in block.extra}
                kept = tuple(i for i in range(len(tokens)) if i not in hidden)
                for tree in reduced(kept):
                    yield from _restore(tree, kept, selection)
                pending.append((j + 1, selection))
