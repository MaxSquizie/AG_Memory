from dataclasses import replace
from functools import cache
from importlib.resources import files

from .infinitives import FRAMES, _with_control
from .nominal_groups import _groups
from .rules import known_forms


@cache
def _lexicon():
    directory = files(__package__).joinpath('lexicon')
    government = {}
    roles = {}
    for line in directory.joinpath('bare_government.tsv').read_text(encoding='utf-8').splitlines():
        lemma, cases = line.split('\t')
        government[lemma] = frozenset(cases.split())
    for line in directory.joinpath('bare_roles.tsv').read_text(encoding='utf-8').splitlines():
        lemma, case, role = line.split('\t')
        roles[lemma, case] = role
    return government, roles


@cache
def dative_recipients():
    table = files(__package__).joinpath('lexicon/dative-recipients.tsv')
    return frozenset(table.read_text(encoding='utf8').splitlines())


@cache
def _writing_instruments():
    table = files(__package__).joinpath('lexicon/writing_instruments.tsv')
    return frozenset(table.read_text(encoding='utf-8').splitlines())


def _slot(link):
    return link.head, link.role if link.role in ('recipient', 'object') else link.case


def _partitive(tokens, members, case):
    for i, lemma in members:
        if lemma in {'кто', 'себя'}:
            return False
        tags = [tag for word, tag in known_forms(tokens[i].surface)
                if word == lemma and tag.case == case and tag.POS in ('NOUN', 'NPRO')]
        if all(tag.person or tag.animacy == 'anim' for tag in tags):
            return False
    return True


def _pp_attachments(expanded, groups, budget):
    from .parser import AnalysisBudgetExceeded

    nearby = {g.end for g in groups if g.end < len(expanded) and expanded[g.end].role == 'preposition'}
    if not nearby:
        yield expanded
        return
    active = set()
    states = [expanded]
    for i, original in enumerate(expanded):
        if original.role != 'preposition':
            continue
        updated = []
        for tree in states:
            edge = []
            j = i - 1
            while 0 <= j < i:
                edge.append(j)
                head = tree[j].head
                if head is None:
                    break
                j = head
            if i not in nearby and not active.intersection(edge):
                updated.append(tree)
                continue
            candidates = [j for j in edge if tree[j].role in {
                'subject', 'object', 'duration', 'governed', 'experiencer', 'infinitive', 'nominal_conjunct',
                'recipient', 'beneficiary', 'oblique', 'instrument', 'stimulus', 'predicate'}]
            candidates.extend(j for j, link in enumerate(tree) if link.role == 'predicate' and j not in candidates)
            active.add(i)
            for head in candidates:
                updated.append((*tree[:i], replace(original, head=head), *tree[i + 1:]))
            if len(updated) > budget:
                raise AnalysisBudgetExceeded('CASE_ARGUMENT_BUDGET')
        states = updated
    yield from states


def _attach(tokens, tree, kept, groups, government, roles, budget):
    from .parser import AnalysisBudgetExceeded, Link
    from .short_participles import _predicative_instrumentals

    links = {}
    for i, link in zip(kept, tree):
        indices = {key: kept[j] for key in ('head', 'controller', 'antecedent')
                   if (j := getattr(link, key)) is not None}
        links[i] = replace(link, **indices)
    for i, link in links.items():
        if link.role == 'governed' and any(link.head < group.start < i for group in groups):
            return
    hosts = [(i, link.lemma) for i, link in links.items() if link.role in ('predicate', 'infinitive')]
    governors = {link.head for link in links.values() if link.rule == 'I1'}
    occupied = frozenset(_slot(link) for link in links.values()
                         if link.role in ('recipient', 'beneficiary', 'stimulus', 'instrument', 'oblique', 'experiencer', 'object'))
    states = [((), occupied)]
    for group in groups:
        choices = []
        members = [(group.noun, group.lemma),
                   *((i, link.lemma) for i, link in group.extra if link.role == 'nominal_conjunct')]
        reflexive_dative = group.case == 'datv' and any(
            lemma == group.lemma and tag.POS == 'NPRO' and 'Anph' in tag and tag.case == 'datv'
            for lemma, tag in known_forms(tokens[group.noun].surface))
        for host, verb in hosts:
            if (reflexive_dative and links[host].role == 'infinitive'
                    and links[host].controller is not None
                    and any(link.role == 'object' and link.head == host for link in links.values())
                    and group.case not in government.get(verb, ())):
                choices.append(Link('beneficiary', group.lemma, host, 'DAT.REFLEX', case=group.case))
            if host in governors:
                frame = FRAMES.get(verb)
                if frame is None or group.case not in frame.recipient_cases:
                    continue
                role = 'recipient'
            elif verb in {'оказаться', 'оказываться'} and group.case == 'ablt':
                continue
            elif group.case in government.get(verb, ()):
                role = roles.get((verb, group.case), 'oblique')
            else:
                continue
            if role == 'instrument' and any(lemma not in _writing_instruments() for _, lemma in members):
                role = 'oblique'
            if role == 'object' and group.case in ('gent', 'gen2') and not _partitive(tokens, members, group.case):
                continue
            choices.append(Link(role, group.lemma, host, 'V.GOV', case=group.case))
            if (role == 'oblique' and group.case == 'ablt' and links[host].rule == 'V1'
                    and verb in _predicative_instrumentals() and any(
                        w == verb and t.POS == 'VERB' and t.transitivity == 'intr'
                        for w, t in known_forms(tokens[host].surface))):
                subjects = [j for j, member in links.items() if member.role == 'subject' and member.head == host]
                if len(subjects) == 1:
                    choices.append(Link('predicative_complement', group.lemma, host, 'V.XCOMP', 'ablt',
                                        controller=subjects[0]))
            if (group.case == 'datv' and role == 'oblique' and verb in dative_recipients()
                    and any(part.role == 'object' and part.head == host for part in links.values())):
                choices.append(Link('recipient', group.lemma, host, 'V.GOV', case='datv'))
        following = []
        for bound, used in states:
            for link in choices:
                slot = _slot(link)
                if slot not in used:
                    following.append(((*bound, link), used | {slot}))
                    if len(following) > budget:
                        raise AnalysisBudgetExceeded('CASE_ARGUMENT_BUDGET')
        states = following
        if not states:
            return
    for bound, _ in states:
        expanded = links.copy()
        for group, link in zip(groups, bound):
            expanded[group.noun] = link
            expanded.update(group.extra)
        result = tuple(expanded[i] for i in range(len(tokens)))
        if any(link.head in governors for link in bound):
            root = next(i for i, _ in hosts if links[i].role == 'predicate')
            subject = next(i for i, link in expanded.items() if link.role == 'subject' and link.head == root)
            children = {link.head: i for i, link in expanded.items() if link.role == 'infinitive'}
            verbs = [root]
            while verbs[-1] in children:
                verbs.append(children[verbs[-1]])
            for tree in _with_control(result, verbs, subject, budget):
                yield from _pp_attachments(tree, groups, budget)
        else:
            yield from _pp_attachments(result, groups, budget)


def trees(tokens, base, *, budget=256, verb_pos=('VERB', 'INFN', 'PRTS')):
    from .parser import AnalysisBudgetExceeded

    yield from base(tokens)
    government, roles = _lexicon()
    potential = {i: {case for lemma, tag in known_forms(token.surface) if tag.POS in verb_pos
                     for case in government.get(lemma, ())} for i, token in enumerate(tokens)}
    if any(any(tag.POS == 'NPRO' and 'Anph' in tag and tag.case == 'datv' for _, tag in known_forms(t.surface))
           for t in tokens):
        for i, token in enumerate(tokens):
            if any(tag.POS == 'INFN' for _, tag in known_forms(token.surface)):
                potential[i].add('datv')
    potential = {i: cases for i, cases in potential.items() if cases}
    if not potential:
        return
    allowed = frozenset().union(*potential.values())
    spans = [group for i in range(len(tokens)) for group in _groups(tokens, i, budget, bare_cases=allowed)]
    if not spans:
        return

    @cache
    def parse(kept):
        result = []
        for tree in base(tuple(tokens[i] for i in kept)):
            result.append(tree)
            if len(result) > budget:
                raise AnalysisBudgetExceeded('CASE_ARGUMENT_BUDGET')
        return result

    pending = [(0, ())]
    count = 0
    while pending:
        start, groups = pending.pop()
        for j in range(start, len(spans)):
            group = spans[j]
            if groups and group.start < groups[-1].end:
                continue
            if sum(g.case == group.case for g in groups) >= sum(group.case in cases for cases in potential.values()):
                continue
            count += 1
            if count > budget:
                raise AnalysisBudgetExceeded('CASE_ARGUMENT_BUDGET')
            chosen = (*groups, group)
            hidden = {i for g in chosen for i in range(g.start, g.end)}
            kept = tuple(i for i in range(len(tokens)) if i not in hidden)
            for tree in parse(kept):
                yield from _attach(tokens, tree, kept, chosen, government, roles, budget)
            pending.append((j + 1, chosen))
