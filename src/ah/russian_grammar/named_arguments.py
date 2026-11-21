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


@lru_cache(maxsize=1024)
def personal_accusatives(surface):
    if not surface.istitle():
        return ()
    tagged = known_forms(surface)
    if any(t.POS == 'NOUN' and t.case == 'accs' and t.animacy == 'anim' for _, t in tagged):
        return ()
    return tuple((lemma, replace(from_tag(tag), case='accs', animacy='anim'))
                 for lemma, tag in tagged if 'Geox' in tag and tag.gender == 'masc'
                 and tag.case == 'gent' and tag.number == 'sing')


def trees(tokens, *, budget):
    from .determiners import with_agreeing_determiners

    if any(opaque_cases(t.surface) or personal_accusatives(t.surface) for t in tokens):
        yield from with_agreeing_determiners(tokens, lambda part: _named_trees(part, budget), include_bare=True)


def _named_trees(tokens, budget):
    from .parser import AnalysisBudgetExceeded, Link

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
        if case == 'accs':
            for lemma, form in personal_accusatives(tokens[i].surface):
                named = Link('nominal', lemma, None, 'OPAQUE.PERSON.ACC', case, morphology=form)
                candidates.append(Phrase(i + 1, i, case, ((i, named),)))
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


def _spatial_argument(tree, root):
    from .adjuncts import SPATIAL, _lexicon

    entries, _ = _lexicon()
    for noun in tree:
        if noun.role != 'governed' or noun.head is None:
            continue
        prep = tree[noun.head]
        wh = SPATIAL.get((prep.lemma, noun.case))
        if prep.head == root and wh and ('governor', wh, prep.lemma, tree[root].lemma) in entries:
            return True
    return False


def single_finite_region(tokens):
    from .case_arguments import _clause_token
    from .quote_titles import spans

    quoted = {i for start, end in spans(tokens) for i in range(start + 1, end)}
    return sum(i not in quoted and t.surface.islower() and _clause_token(t.surface)[2]
               for i, t in enumerate(tokens)) <= 1


def missing_subjects(tokens, parse):
    from .infinitives import FRAMES
    from .morphology import PREDICATE_ROLES
    from .parser import Link
    from .utterances import _map, _root

    if not single_finite_region(tokens):
        return
    for i, token in enumerate(tokens):
        word = token.surface
        if not word.istitle() or not all(part.isalpha() for part in word.split('-')) or known_forms(word):
            continue
        cases = opaque_cases(word)
        if cases and 'nomn' not in cases:
            continue
        if not cases and any(p.tag.POS for p in dictionary().parse(word)):
            continue
        kept = (*range(i), *range(i + 1, len(tokens)))
        if not kept:
            continue
        for tree in parse(tuple(tokens[j] for j in kept)):
            root = _root(tree)
            predicate = tree[root]
            infinitives = [j for j, link in enumerate(tree) if link.role == 'infinitive']
            if infinitives:
                frame = FRAMES.get(predicate.lemma)
                if not frame or frame.control != 'subject' or any(tree[j].head != root or
                        tree[j].implicit_subject != 'unresolved' or tree[j].controller is not None
                        for j in infinitives):
                    continue
            if (predicate.rule != 'V1' or predicate.implicit_subject != 'unresolved'
                    or any(link.role == 'subject' or j != root and
                           link.role in PREDICATE_ROLES | {'converb', 'participle'}
                           for j, link in enumerate(tree))):
                continue
            form = predicate.morphology
            if not form or form.pos != 'VERB' or form.mood != 'indc' or form.person not in (None, '3per'):
                continue
            if (form.transitivity == 'tran' and not any(link.head == root and link.role == 'object' for link in tree)
                    and not _spatial_argument(tree, root)):
                continue
            if not any(lemma == predicate.lemma and tag.POS == 'VERB' and 'Impe' not in tag
                       for lemma, tag in known_forms(tokens[kept[root]].surface)):
                continue
            links = _map(tree, kept)
            links[kept[root]] = replace(links[kept[root]], implicit_subject=None)
            for j in infinitives:
                links[kept[j]] = replace(links[kept[j]], controller=i, implicit_subject=None)
            links[i] = Link('subject', word, kept[root], 'OPAQUE.SUBJECT', case='nomn')
            yield tuple(links[j] for j in range(len(tokens)))


def confirmation(tokens, tree, i, text):
    if tree[i].rule not in ('OPAQUE.PERSON.ACC', 'OPAQUE.SUBJECT'):
        return None
    from .parser import _span_label
    from .probe import Probe

    person = _span_label(tokens, i)
    head = tree[i].head
    if tree[i].rule == 'OPAQUE.SUBJECT':
        action = _span_label(tokens, head)
        return Probe(f'Каким именем или названием в тексте выражено подлежащее при «{action}»?', (person,), text)
    question = 'Какое слово здесь обозначает человека и стоит в винительном падеже?'
    if head is not None and tree[head].role == 'predicate':
        action = _span_label(tokens, head)
        question = f'Какое слово здесь называет того, на кого направлено действие «{action}»?'
    return Probe(question, (person,), text)


def coordinated_names(tokens, parse, budget):
    from .morphology import NOMINAL_ROLES, ROLE_CASE
    from .parser import AnalysisBudgetExceeded, Link

    def items(i, case):
        for noun, lemma, _, attrs in _members(tokens, i, None, case):
            head = Link('nominal_conjunct', lemma, None, 'N.COORD', case)
            links = dict(attrs) | {noun: head}
            yield noun + 1, noun, links
            after = noun + 1
            if after < len(tokens) and opaque_cases(tokens[after].surface):
                app = Link('apposition', tokens[after].surface, noun, 'OPAQUE.APPOSITION', case)
                yield after + 1, noun, links | {after: app}
        if i < len(tokens) and case in opaque_cases(tokens[i].surface):
            yield i + 1, i, {i: Link('nominal_conjunct', tokens[i].surface, None, 'OPAQUE.NAME', case)}

    commas = [i for i, token in enumerate(tokens) if i and token.surface == ',']
    if not commas or not any(opaque_cases(t.surface) for t in tokens):
        return
    for left in commas:
        for tree in parse(tokens[:left]):
            host = left - 1
            if tree[host].role not in NOMINAL_ROLES:
                continue
            case = tree[host].case or ROLE_CASE.get(tree[host].role)
            if not case:
                continue
            pending = [(left, dict(enumerate(tree)), False)]
            examined = 0
            while pending:
                stop, links, lexical_marker = pending.pop()
                examined += 1
                if examined > budget:
                    raise AnalysisBudgetExceeded('COORDINATED_NAME_BUDGET')
                if stop == len(tokens):
                    if lexical_marker and any(l.rule in ('OPAQUE.APPOSITION', 'OPAQUE.NAME') for l in links.values()):
                        yield tuple(links[i] for i in range(stop))
                    continue
                comma = tokens[stop].surface == ','
                begin = stop + int(comma)
                marks = list(_markers(tokens, begin))
                if comma:
                    marks.append(())
                for mark in marks:
                    nxt = begin + len(mark)
                    for finish, member, tail in items(nxt, case):
                        fresh = links | tail
                        fresh[member] = replace(tail[member], head=host)
                        if comma:
                            fresh[stop] = Link('punctuation', ',', member, 'P.COORD')
                        for j in mark:
                            fresh[j] = Link('coordinator' if j == mark[0] else 'coordinator_part',
                                            tokens[j].surface.casefold(), member if j == mark[0] else mark[0], 'P.COORD')
                        pending.append((finish, fresh, lexical_marker or bool(mark)))


def clauses_with_named_series(tokens, parse, budget):
    from . import clauses
    from .morphology import NOMINAL_ROLES
    from .parser import Link

    if not any(t.surface == ',' for t in tokens) or not any(opaque_cases(t.surface) for t in tokens):
        return
    if not any(next(_markers(tokens, i), ()) for i in range(len(tokens))):
        return

    def local(part):
        yield from parse(part)
        yield from coordinated_names(part, parse, budget)
        if len(part) < 2 or not opaque_cases(part[-1].surface):
            return
        for tree in parse(part[:-1]):
            if tree[-1].role in NOMINAL_ROLES and tree[-1].role != 'subject':
                yield (*tree, Link('genitive_modifier', part[-1].surface, len(tree) - 1, 'N.UNLISTED.GEN', 'gent'))

    for tree in clauses.trees(tokens, local, budget=budget):
        if not any(l.role == 'nominal_conjunct' and (l.rule == 'OPAQUE.NAME' or
                   any(a.head == i and a.rule == 'OPAQUE.APPOSITION' for a in tree)) for i, l in enumerate(tree)):
            continue
        yield tree
        for i, clause in enumerate(tree):
            if clause.role != 'clause_relative' or clause.implicit_subject != 'unresolved' or clause.head is None:
                continue
            parent = tree[clause.head].head
            if parent is None or tree[parent].role != 'predicate':
                continue
            for actor, subject in enumerate(tree):
                if subject.role != 'subject' or subject.head != parent:
                    continue
                forms = [tag for lemma, tag in known_forms(tokens[actor].surface)
                         if lemma == subject.lemma and tag.case == 'nomn']
                if not forms:
                    forms = [p.tag for p in dictionary().parse(tokens[actor].surface)
                             if p.tag.POS == 'NOUN' and p.tag.case == 'nomn']
                if any(tag.POS == 'VERB' and tag.mood == 'indc' and tag.person in (None, '3per')
                       and any(f.number == tag.number and (not tag.gender or tag.gender == f.gender) for f in forms)
                       for lemma, tag in known_forms(tokens[i].surface) if lemma == clause.lemma):
                    yield (*tree[:i], replace(clause, controller=actor, implicit_subject=None), *tree[i + 1:])
