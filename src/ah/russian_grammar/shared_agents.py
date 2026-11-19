from collections import defaultdict
from dataclasses import replace

from .nominal_groups import Group
from .short_participles import instrumental_roles


def _positive_passive(link):
    form = link.morphology
    return (link.role == 'participle' and form is not None and form.pos == 'PRTF' and form.voice == 'pssv'
            and link.scope in (None, 'addition') and link.implicit_subject is None)


def _boundary(tree, low, high):
    return any(link.role.startswith('clause_') or link.role in {'participle', 'predicate'}
               for link in tree[low + 1:high])


def _additive(left, right, tree):
    markers = [link for link in tree[left + 1:right]
               if link.head == right and link.rule == 'PART.COORD' and link.scope is not None]
    if not markers or any(link.scope != 'addition' for link in markers):
        return False
    return not _boundary(tree, left, right)


def _runs(tree, groups):
    for members in groups.values():
        run = []
        for i in members:
            if run and not _additive(run[-1], i, tree):
                if len(run) > 1:
                    yield run
                run = []
            if _positive_passive(tree[i]):
                run.append(i)
            else:
                if len(run) > 1:
                    yield run
                run = []
        if len(run) > 1:
            yield run


def _extensions(tokens, tree, run, agents, occupied, from_left):
    order = run if from_left else run[::-1]
    source = order[0]
    local = agents.get(source, ())
    if len(local) != 1:
        return ()
    actor, = local
    if (from_left and actor >= source) or (not from_left and actor <= source):
        return ()
    if _boundary(tree, min(actor, source), max(actor, source)) or any(link.role == 'subject' and link.head == source for link in tree):
        return ()
    conjuncts = tuple((j, link) for j, link in enumerate(tree)
                      if link.role == 'nominal_conjunct' and link.head == actor)
    members = {j for j, _ in conjuncts}
    for i, link in enumerate(tree):
        if link.role == 'coordinator' and link.head in members:
            phrase = (link.lemma, *(part.lemma for part in tree if part.role == 'coordinator_part' and part.head == i))
            if phrase not in {('и',), ('также',), ('а', 'также')}:
                return ()
    group = Group(actor, actor + 1, None, actor, tree[actor].lemma, 'ablt', conjuncts)
    additions = []
    for member in order[1:]:
        if member in occupied or 'agent' not in instrumental_roles(tokens, group, tree[member].lemma):
            break
        additions.append((member, actor))
    return tuple(additions)


def variants(tokens, tree, *, budget):
    from .parser import AnalysisBudgetExceeded

    groups = {}
    for i, link in enumerate(tree):
        first = link.coord_head
        if first is not None and link.role == 'participle' and 0 <= first < i and tree[first].head == link.head:
            groups.setdefault(first, [first]).append(i)
    if not groups:
        yield tree
        return
    agents = defaultdict(list)
    occupied = set()
    for i, link in enumerate(tree):
        if link.role == 'agent':
            agents[link.head].append(i)
        if link.role in {'agent', 'subject'}:
            occupied.add(link.head)
    if not agents:
        yield tree
        return
    choices = [()]
    for run in _runs(tree, groups):
        for from_left in (False, True):
            additions = _extensions(tokens, tree, run, agents, occupied, from_left)
            if not additions:
                continue
            updated = []
            for selected in choices:
                updated.append(selected)
                assigned = {i for i, _ in selected}
                for length, (target, _) in enumerate(additions, 1):
                    if target in assigned:
                        break
                    updated.append(selected + additions[:length])
                    if len(updated) > budget:
                        raise AnalysisBudgetExceeded('SHARED_AGENT_BUDGET')
            if len(updated) > budget:
                raise AnalysisBudgetExceeded('SHARED_AGENT_BUDGET')
            choices = updated
    for selected in choices:
        if not selected:
            yield tree
            continue
        result = list(tree)
        for member, actor in selected:
            result[member] = replace(tree[member], shared_agent=actor)
        yield tuple(result)
